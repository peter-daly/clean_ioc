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
