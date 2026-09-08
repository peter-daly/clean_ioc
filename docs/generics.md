# Generics

Clean IoC discovers concrete implementations of an open generic service and compiles each closed occurrence.

```python
from typing import Generic, TypeVar

from clean_ioc import ContainerBuilder


TCommand = TypeVar("TCommand")


class CommandHandler(Generic[TCommand]):
    pass


class CreateOrder:
    pass


class CreateOrderHandler(CommandHandler[CreateOrder]):
    pass


builder = ContainerBuilder()
builder.register_generic_subclasses(CommandHandler)
container = builder.build()

handler = container.resolve(CommandHandler[CreateOrder])
```

`register_generic_subclasses(...)` records a discovery rule and returns `None`. `build()` takes the live subclass snapshot, creates the closed registrations, validates them, and freezes them into the runtime plan. Open generic registrations act as reusable activation templates; only closed occurrences are runtime roots.

This means a class created after the rule is declared but before `build()` is included:

```python
import types

builder.register_generic_subclasses(CommandHandler)

DynamicHandler = types.new_class(
    "DynamicHandler",
    (CommandHandler[CreateOrder],),
)

container = builder.build()
```

Use `types.new_class()` for a dynamic parameterized base. A direct `type(..., (CommandHandler[CreateOrder],), ...)` call does not resolve generic MRO entries. Candidate modules must be imported and dynamic class objects must still be alive when `build()` starts.

Classes created after a successful build do not alter the immutable container. A failed build leaves the builder reusable and the next build rescans its own discovery rules.

## Closed generic constructors

Register closed classes directly, or provide a closed service and implementation pair:

```python
from typing import Generic, TypeVar, final

from clean_ioc import ContainerBuilder

Item = TypeVar("Item")
Value = TypeVar("Value")


class Repository(Generic[Value]):
    pass


class Service(Generic[Item]):
    pass


@final
class Consumer(Service[Value], Generic[Value]):
    def __init__(self, repository: Repository[Value], repositories: list[Repository[Value]]):
        self.repository = repository
        self.repositories = repositories


builder = ContainerBuilder()
builder.register(Repository[str], lifespan="singleton")
builder.register(Consumer[str])
builder.register(Service[int], Consumer[int])
builder.register(Repository[int], lifespan="singleton")

with builder.build() as container:
    consumer = container.resolve(Consumer[str])
    assert type(consumer) is Consumer
    assert consumer.repository is container.resolve(Repository[str])
    assert consumer.repositories == [consumer.repository]
    assert type(container.resolve(Service[int])) is Consumer
```

Python 3.12+ class type-parameter syntax works too, for example `class Consumer[T]: ...`.
Constructor annotations are specialised using the **implementation's** closed bindings,
including inherited constructors, reordered parameters, and nested collections. Service and
implementation parameters need not have matching names. Ordinary dependencies keep their annotations.
The original class is constructed, including classes marked `@final`; no implementation subclass
is generated. Retention of an instance's `__orig_class__` is not guaranteed.

`Consumer[str]` and `Consumer[int]` remain distinct service keys, with their usual names,
tags, filters, lifespans, and scope boundaries. Argument overrides, `select(...)`, `inject()`,
Python defaults, and `derive(...)` use the specialised plan. `ParameterContext.annotation`
is specialised before the policy runs. Unknown argument names are checked against the real
constructor, including whether it accepts `**kwargs`; patching arguments uses the same rules.

Missing required dependencies fail during `build()` with the closed dependency, constructor
argument, and owning component in the diagnostic. Register the missing dependency and retry
the same builder. Unresolved required TypeVars also fail, including inside collections, rather
than producing an empty collection. Explicit values and defaults may satisfy an argument without
requiring a concrete dependency binding. Constructors are never invoked during build, and
both sync and async resolution execute the already compiled plan.

### Component mapping policy

For `register(Service[str], Consumer[str])`, component metadata retains
`service_type == Service[str]`, `implementation == Consumer[str]`,
`implementation_type is Consumer`, and `activation == ComponentActivation.constructor`.
For compatibility, `component.generic_mapping`, `generic_arg(...)`, and `has_generic_arg(...)`
continue to use the **service** mapping: `Item -> str` in this example. They do not merge in
`Value -> str` from the implementation. Constructor substitution is independent of this policy.
Where needed, inspect implementation bindings with
`typetoolbox.generics.GenericTypeMap(component.implementation)`. This applies to both build-time
filters and the frozen graph. An implementation registered under its own service key naturally
exposes its own service mapping.

Typetoolbox maps variables by name; distinct same-named TypeVars within one hierarchy can
collide and are not supported by this feature. Its mapping may omit direct bindings for
traditional inherited generics without an explicit `Generic[...]` base; constructor injection
also uses the closed alias's direct parameters, but the public service mapping is unchanged.
This feature does not add ParamSpec/TypeVarTuple support, implicit registration of missing
closed dependencies, or implicit closing of bare generic registrations from parameter defaults.

## Generic factories

A closed factory registration specializes TypeVars in every nested dependency annotation during `build()`:

```python
TCommand = TypeVar("TCommand")


class HandlerConfig(Generic[TCommand]):
    pass


def create_handler(config: HandlerConfig[TCommand]) -> CommandHandler[TCommand]:
    return ConfiguredCommandHandler(config)


builder.register(HandlerConfig[CreateOrder], CreateOrderConfig)
builder.register(CommandHandler[CreateOrder], factory=create_handler)
```

The registered service and factory result annotation normally provide the mapping. This also works when the result is a bare TypeVar, and for nested collection, union, generator, and context-manager annotations. The compiler rewrites only the dependency plan: it keeps the original sync, async, generator, or context-manager callable and never invokes it during `build()`.

An open registration is a reusable factory template:

```python
builder.register(CommandHandler, factory=create_handler)
builder.register(PlaceOrder)  # depends on CommandHandler[CreateOrder]
```

Each closed dependency occurrence gets its own component identity and lifespan cache. Exact closed registrations take precedence over the template. The immutable container does not compile an unseen type during `resolve()`, so a type that must be resolved directly remains an explicit closed registration:

```python
builder.register(CommandHandler[CreateOrder], factory=create_handler)
```

Use `generic_arg(...)` when a constructor or factory needs one of its owning component's concrete generic bindings as a
value:

```python
from clean_ioc import generic_arg


class HandlerMetadata(Generic[TCommand]):
    def __init__(self, command_type: type):
        self.command_type = command_type


builder.register(
    HandlerMetadata[CreateOrder],
    arguments={"command_type": generic_arg(TCommand)},
)
```

The `TypeVar` form is preferred. String keys are also supported when composition is reflection-driven. The binding is
looked up and frozen during `build()` rather than rediscovered during factory activation.

If a factory TypeVar is not expressed by its registered service or result, provide another generic class or alias as the mapping source:

```python
builder.register(
    Connection,
    factory=create_connection,
    factory_specialization=MyEngine,
)
```

`factory_specialization` is valid only with `factory=`. Build fails with `ContainerBuildError` when ordinary TypeVars remain unresolved or inferred sources conflict. ParamSpec and TypeVarTuple specialization are not supported. TypeVar lookup follows typetoolbox's name-based mapping model, so avoid distinct same-named TypeVars in one factory signature.

## Filtering discovered subclasses

`subclass_type_filter` uses predicates from `clean_ioc.type_filters`:

```python
import clean_ioc.type_filters as tf

builder.register_generic_subclasses(
    CommandHandler,
    subclass_type_filter=~tf.name_end_with("Decorator"),
)
```

Type filters remain separate from component filters because they answer a discovery question about Python classes, not a selection question about compiled occurrences.

## Fallback implementation

```python
builder.register_generic_subclasses(
    Serializer,
    fallback_type=JsonSerializer,
)
```

When no exact closed implementation exists, the compiler specializes the open fallback edge for the requested occurrence.

## Generic decorators

```python
TCommand = TypeVar("TCommand")


class LoggingHandlerDecorator(CommandHandler[TCommand], Generic[TCommand]):
    def __init__(self, child: CommandHandler[TCommand]):
        self.child = child


builder.register_decorator(CommandHandler, LoggingHandlerDecorator)
```

Concrete decorator classes are memoized process-wide, avoiding repeated dynamic class creation across container builds.

An open decorator definition is specialized from the closed component plans encountered by the compiler. It therefore applies to subclass-discovered handlers, explicit closed registrations, generic factories, and fallback registrations. It does not depend on Python's live subclass set; use `register_decorator()` for both open and closed service types.

## Occurrence-specific context

The same registered component may appear under different closed generic parents. Clean IoC creates a distinct
`Component.occurrence_id` for each use, so parent filters and derived argument policies see the correct generic mapping:

```python
from clean_ioc import ParameterContext, derive


def command_name(context: ParameterContext):
    parent = context.component.parent
    if parent is None:
        return context.default
    command_type = parent.generic_mapping[TCommand]
    return command_type.__name__


builder.register(Service, arguments={"command_name": derive(command_name)})
```

Runtime caching still uses the stable component ID, preserving lifespan semantics across occurrences within one resolve.
