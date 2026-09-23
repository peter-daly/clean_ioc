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

`register_generic_subclasses(...)` records a discovery rule and returns `None`. Module names declared with `ensure_import_modules=` are imported during `build()`, before any subclass rule takes its live snapshot. Pass one module name or an iterable of names. Imports declared by any rule happen before all discovery, so rule order cannot make a class disappear. The option only ensures imports; it does not filter discovery by module.

```python
builder.register_generic_subclasses(
    CommandHandler,
    ensure_import_modules=(
        "my_app.create_order",
        "my_app.cancel_order",
    ),
)
```

Named packages do not import their children by default. Set `include_children=True` to recursively import every discoverable child module:

```python
builder.register_generic_subclasses(
    CommandHandler,
    ensure_import_modules="my_app.command_handlers",
    include_children=True,
)
container = builder.build()

assert "my_app.command_handlers.create_order" in container.ensured_import_modules
```

`container.ensured_import_modules` returns the concrete module names ensured by the compiled plan, including recursively imported children. Built overlay scopes expose the combined modules from their inherited and local plans.

The build then creates the closed registrations, validates them, and freezes them into the runtime plan. Open generic registrations act as reusable activation templates; only closed occurrences are runtime roots. `register_subclasses(...)` supports the same `ensure_import_modules=` declaration for non-generic bases.

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

Use `types.new_class()` for a dynamic parameterized base. A direct `type(..., (CommandHandler[CreateOrder],), ...)` call does not resolve generic MRO entries. Candidate modules not named by `ensure_import_modules=` must already be imported, and dynamic class objects must still be alive when `build()` starts.

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

## Structural registration patterns

Use `register_pattern()` when the factory depends on the structure inside a service's type arguments:

```python
from dataclasses import dataclass
from typing import Generic, TypeVar

from clean_ioc import ContainerBuilder

T = TypeVar("T")


class Serializer(Generic[T]):
    def serialize(self, value: T) -> str:
        raise NotImplementedError


@dataclass
class Order:
    reference: str


class OrderSerializer(Serializer[Order]):
    def serialize(self, value: Order) -> str:
        return value.reference


class ListSerializer(Serializer[list[T]]):
    def __init__(self, item_serializer: Serializer[T]):
        self.item_serializer = item_serializer

    def serialize(self, value: list[T]) -> str:
        return "[" + ", ".join(self.item_serializer.serialize(item) for item in value) + "]"


def make_list_serializer(item_serializer: Serializer[T]) -> Serializer[list[T]]:
    return ListSerializer(item_serializer)


class ExportOrders:
    def __init__(self, serializer: Serializer[list[Order]]):
        self.serializer = serializer


builder = ContainerBuilder()
builder.register(Serializer[Order], OrderSerializer)
builder.register_pattern(Serializer[list[T]], factory=make_list_serializer)
builder.register(ExportOrders)

with builder.build() as container:
    exporter = container.resolve(ExportOrders)
    assert exporter.serializer.serialize([Order("A"), Order("B")]) == "[A, B]"
```

The same template handles finite nesting, such as `Serializer[list[list[Order]]]`. A dictionary template declared as
`Serializer[dict[str, T]]` accepts only string keys. Concrete positions match exactly by canonical origin and ordered
arguments; they do not use subclass dispatch. Repeated variables, as in `Serializer[tuple[T, T]]`, must bind equally.
Transparent native and backported type aliases normalize before matching; `NewType` remains nominal.

The signature is `register_pattern(service_type, *, factory, lifespan="per_resolution", name=None, arguments=None,
tags=None, when=all_components) -> str`. Container builders, scope builders, and bundles using `ComponentBuilder`
support it. The returned ID identifies the template; each closed specialization receives its own stable component ID.
The original factory stays unchanged. Ordinary argument policies, decorators, providers, provider maps,
pre-configuration, lifespans, and cleanup ownership apply to each compiled specialization.

### Supported structures and factory bindings

Patterns require a parameterized class containing at least one ordinary `TypeVar`. Terminal positions accept classes,
nominal `NewType`s, and variables; nested aliases use class origins. Matching supports fixed-length tuples but excludes
unions, `Any`, `Literal`, `Annotated`, callables, ellipsis tuples, bare generics, `ParamSpec`, and `TypeVarTuple`.
These restrictions also apply to closed expressions bound to a variable. A bare generic is never closed from defaults.
Synthetic collection and provider requests cannot be the outer pattern; register their element or target service
pattern instead. Repeated bindings compare canonical structure, including equivalent `typing.List`/`list` spellings.

Bounds and constraints must be ordinary unparameterized classes. Variable bindings use subclass checks against those
classes (the origin for a parameterized binding); constraints accept any listed class or its subclasses, preserving
the actual bound type. Parameterized bounds, forward bounds, and protocol bounds, including runtime-checkable protocols,
are rejected. Concrete pattern positions still use exact matching.

Factory variables must be the same `TypeVar` objects bound by the pattern. A result annotation, when supplied, must
substitute to the closed service; generator and context-manager annotations use the yielded type. Unknown variables,
conflicting results, and distinct same-named variables produce `pattern-incompatible-binding`. Factory defaults do not
invent missing pattern bindings. Public `component.generic_mapping` remains the service mapping: for
`Serializer[list[Order]]`, the service parameter maps to `list[Order]`, while the factory's pattern variable maps to
`Order`. Typetoolbox's existing name-based metadata limitations remain; these two mappings are not merged.

### Selection and visibility

Selection first chooses a definition tier: exact closed registrations, then matching structural patterns, then existing
open-generic fallbacks. A pattern is more specific if every expression it accepts is accepted by the other pattern and
the reverse does not hold. Nested concrete structure, repeated-variable equality, and narrower bound/constraint domains
participate in this relation. For example, `Serializer[list[T]]` beats `Serializer[U]`; `Serializer[tuple[T, T]]` beats
`Serializer[tuple[T, U]]`. `Serializer[tuple[int, T]]` and `Serializer[tuple[U, str]]` are incomparable for
`Serializer[tuple[int, str]]` and fail with `pattern-ambiguous` regardless of declaration order.

Equivalent patterns retain all registrations, in ordinary newest-first order, with overlays ahead of parent layers.
Visibility is applied before tier and specificity selection. Existing `when` conditions and caller/name filters run
after that selection; rejecting the chosen tier does not create a fallback. Consequently an exact named registration
can prevent an unnamed or differently named pattern from being selected. Collections and provider maps retain the
eligible registrations in the winning equivalent-pattern group.

A Boundary may expose or use an explicitly closed request, such as `Expose(Serializer[list[Order]])`, or publish a
selected template family with an open declaration. A `BoundaryAlias` may map that family onto a different public generic
service. Each encountered closed public request maps back to the source expression, then compiles and specializes with
the template's definition-site visibility before the public identity is projected. Templates still enumerate no roots:
only closed requests discovered during compilation become resolvable. Private specializations remain private. An
inherited singleton keeps its parent's frozen plan; an overlay cannot introduce a previously uncompiled parent singleton
specialization. Source and public alias declarations must contain the same number of generic variables, so an alias
cannot turn a closed source such as `Internal[int]` into an unconstrained public family such as `Public[T]`.

Distinct variables are paired one-to-one in first-appearance order, not by variable name. Repeated occurrences of one
variable count once. A closed public request must bind every public variable, and applying those bindings to the paired
source variables must leave a closed source request; otherwise the build fails with `boundary-alias-incompatible`.
Concrete structure remains part of each declaration, so an alias can deliberately map
`InternalSerializer[list[T]]` to `PublicSerializer[T]`, but it cannot invent a source binding that the public request
does not provide. Bounds, constraints, and repeated-variable equality still apply during matching and specialization.

### Frozen requests and diagnostics

Templates alone enumerate no roots. A closed pattern request encountered in a public compiled dependency, provider,
or provider-map target is also compiled as a public root with ordinary root filtering. Explicit closed Boundary
exposures are roots too. Private dependency requests do not become public. `mark_entrypoint()` can focus an already
compiled pattern request, but does not introduce a new request or grant runtime access. Unseen closed keys cannot be
resolved, and runtime resolution, provider calls, and map lookups never perform matching.

Ordinary cycles report `circular-dependency`. Growing specializations report `pattern-non-terminating-expansion`:
the compiler rejects a non-shrinking request after 16 active specializations of the same template or 32 across all
templates. This is a bounded
guard, not a general termination proof; unusually deep finite growing constructions must use explicit registrations.
Shrinking list nesting works normally. Invalid declarations use `pattern-invalid`; unsupported forms use
`pattern-unsupported-form`. Errors include the closed request and compilation path. Failed builders remain repairable.
Graph explanations identify winning, mismatched, shadowed, and less-specific templates without activating factories.
Template origins stay out of semantic fingerprints, and programs without patterns retain their existing manifests.

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

## Modern type aliases

Native Python `type` statements and `typing_extensions.TypeAliasType` are transparent wherever a service type or
dependency annotation is accepted. The alias and its expanded target select the same compiled component, cache, and
cleanup owner, including aliases nested in generics, collections, unions, and typed providers:

```python
from typing import Generic, TypeVar
from typing_extensions import TypeAliasType


T = TypeVar("T")


class Repository(Generic[T]):
    pass


Repo = TypeAliasType("Repo", Repository[T], type_params=(T,))

builder.register(Repo[Order], lifespan="singleton")
container = builder.build()
assert container.resolve(Repo[Order]) is container.resolve(Repository[Order])
```

Alias parameters are bound before generic specialization, so nested aliases and reordered parameters retain their
declared meaning. Open aliases expose only the template behavior already supported by their canonical generic target;
`ParamSpec` and `TypeVarTuple` alias expansion is not supported. Alias forward references are evaluated from their
defining module during preview/build and may be repaired before retrying a failed builder.

`NewType` is different: it remains a nominal service key and never falls back to its supertype. Register a `NewType`
with an explicit `instance=`, `factory=`, or `implementation_type`; a bare declaration is not treated as a constructor.
