# Clean IoC 1.x to 2.0 upgrade guide

This is an agent-oriented playbook for migrating applications, integrations, bundles, and tests from Clean IoC 1.x to 2.0. Version 2 has one public model: compose with a builder, call `build()`, then resolve from the immutable runtime.

V2 changes the container lifecycle: composition is mutable, but a runtime is immutable and fully compiled before application code starts.

Clean IoC 2 does not ship the V1 container as a parallel public API. `clean_ioc.core`, registration filters, node filters, runtime dependency graphs, and compatibility method aliases are removed. Do not import private modules such as `clean_ioc._legacy`; they are temporary implementation details and may disappear without notice.

## The essential conversion

V1 combines registration and resolution in one object:

```python
from clean_ioc import Container, Lifespan

container = Container()
container.register(Repository, SqlRepository, lifespan=Lifespan.scoped)
container.register(Service)

service = container.resolve(Service)
```

V2 builds an immutable runtime explicitly:

```python
from clean_ioc import ContainerBuilder

builder = ContainerBuilder()
builder.register(Repository, SqlRepository, lifespan="scoped")
builder.register(Service)

container = builder.build()
service = container.resolve(Service)
```

Apply all registrations, decorators, pre-configurations, discovery rules, patches, slots, bundles, and entry-point markers to the builder before `build()`.

## API mapping

| V1 | V2 | Migration note |
| --- | --- | --- |
| `Container()` | `ContainerBuilder()` then `.build()` | Do not construct V2 `Container` directly. |
| `container.register(...)` | `builder.register(...)` | The registration signature is largely preserved. |
| `dependency_config={...}` | `arguments={...}` | Values, selection, and derivation are explicit V2 policies. |
| `Lifespan.scoped` and other enum members | `"scoped"` and other string literals | V2 accepts `"transient"`, `"once_per_graph"`, `"scoped"`, and `"singleton"`. |
| `container.patch_registration(...)` | `builder.patch_component(...)` | Patch only before a successful build. |
| `container.pre_configure(...)` | `builder.pre_configure(...)` | It returns a stable definition ID; filters are component filters and run at build. |
| pre-configuration `registration_filter=` | `when=` | V2 uses one component filter. |
| `container.register_decorator(...)` | `builder.register_decorator(...)` | Selection is evaluated against immutable component occurrences. |
| decorator `registration_filter=` / `decorator_node_filter=` | `when=` | Combine both predicates into one component filter. |
| `container.apply_bundle(bundle)` | `builder.apply_bundle(bundle)` | Type bundles against `ComponentBuilder`. |
| `container.expect_to_be_scoped(T)` | `builder.declare_scope_slot(T)` | Declare every late-bound slot before build. |
| `container.has_registration(...)` | `builder.has_component(...)` | This previews compiled components. |
| `get_registration_id(s)` | `get_component_id(s)` | IDs identify registrations; compiled occurrences also have `occurrence_id`. |
| `container.validate(...)` | `builder.build()` / `BuildReport` | Validation is mandatory and covers every visible root. |
| `container.explain(T)` | `container.graph` | Mark an entry point to focus renderers on a public root. |
| `resolve_dependency_graph(...)` | `container.graph` / `Component` | V2 exposes a static compiled graph, not a graph containing runtime instances. |
| `resolve_from_registration_id(...)` | `resolve(T, filter=cf.with_id(id))` | Use `clean_ioc.component_filters`. |
| mutable `scope.register(...)` | scope slot or `new_scope_builder()` | Choose based on whether the change is a value or composition. |
| `force_run_pre_configuration(T)` | resolve an applicable compiled root | Build never invokes user pre-configuration code. |
| `call()` / `call_async()` | no direct equivalent | Register a service/factory before build or invoke explicitly with resolved dependencies. |
| `scoped_teardown=callback` | generator or context-manager factory | Keep acquisition and release in the same factory. |

## Removed imports and their replacements

The following removals are deliberate. Do not preserve them with local aliases or imports from private modules.

| Removed V1 import/API | V2 replacement |
| --- | --- |
| `clean_ioc.core.Container` | `from clean_ioc import ContainerBuilder`; call `builder.build()` |
| `clean_ioc.core.Scope` | `from clean_ioc import Scope` for runtime typing; create it from `container.new_scope()` |
| `clean_ioc.core.Lifespan` | String literals accepted by `lifespan=`; `clean_ioc.Lifespan` is annotation-only |
| `clean_ioc.registration_filters` | `clean_ioc.component_filters` |
| `clean_ioc.node_filters` | `clean_ioc.component_filters` |
| `clean_ioc.list_reduction_filters` | no direct equivalent | Filter a collection with `select(...)`; register an explicit collection factory when ordering or reduction is domain behavior. |
| `DependencySettings(filter=f)` | `select(f)` |
| `DependencySettings(value_factory=f)` | `derive(f)` | The function now runs during build, not activation. |
| `EMPTY` from a value factory | `INJECT` from `derive(...)` |
| `RemoveDependencySetting` | `REMOVE` |
| `clean_ioc.diagnostics` | `BuildReport`, `CompiledGraph`, manifests, and the `clean-ioc` CLI |
| `clean_ioc.factories.use_registered` | `clean_ioc.factories.use_component` |
| `clean_ioc.factories.use_from_current_graph` | `use_component` or an explicit `ResolutionContext` dependency |
| `add_container_to_app` and `add_*_to_scope` | `configure_fastapi(builder)` plus `install_fastapi(app, container)` |
| `register_generic_decorator(...)` | `register_decorator(...)`, which handles open and closed generic services |

The package root is the authoritative public import surface. Submodules documented by the V2 guide—such as
`component_filters`, `type_filters`, `factories`, and `ext.fastapi`—are also public. `clean_ioc.configuration` and
`clean_ioc.value_factories` are removed. An underscore-prefixed module is never a migration target.

`resolve()` and `resolve_async()` remain runtime APIs. Use `resolve_async()` whenever the compiled path contains async factories, generators, context managers, or cleanup.

## Pass composition inputs explicitly

When V1 composition captured environment or mode variables in value factories or filters, pass those inputs explicitly
to the V2 build instead:

```python
def timeout(context: ParameterContext) -> int:
    return 30 if context.build_args["environment"] == "production" else 5


builder.register(Client, arguments={"timeout": derive(timeout)})
builder.register(
    Publisher,
    LivePublisher,
    when=cf.build_arg_is("mode", "live"),
)
container = builder.build(
    build_args={"environment": "production", "mode": "live"},
)
```

Build arguments influence compilation only and are not injected implicitly at runtime. Their shallow-copied mapping is
immutable, although contained values remain user-owned. Scope overlays inherit and may override keys; ordinary scopes
reuse the same arguments. Use a fresh root build when a key must be absent. Supply `build_args=` to preview queries when
their result depends on these inputs. To pass one input to a constructor or factory, configure the parameter explicitly
with `arguments={"environment": build_arg("environment")}`; the selected value is frozen during build. An explicit
`default=` handles an absent input.

Use `inject()` when a V1 dependency setting overrode a Python default with normal unnamed injection. Use
`generic_arg(T)` when a contextual V1 value factory only projected a binding from the owning component's generic map.

## Replace dependency settings with argument policies

V2 removes the mutable `DependencySettings` object. Constructor, factory, decorator, and pre-configuration overrides
all use `arguments=`:

```python
# V1
container.register(
    Client,
    dependency_config={
        "endpoint": DependencySettings(filter=rf.with_name("api")),
        "timeout": 5.0,
    },
)

# V2
builder.register(
    Client,
    arguments={
        "endpoint": select(cf.with_name("api")),
        "timeout": 5.0,
    },
)
```

With no entry, a Python default is used when present; otherwise Clean IoC injects the unnamed component. A plain entry
is the exact compiled value, including when it is callable. `select(filter)` explicitly injects a filtered component
and ignores a Python default.

Migrate a contextual value factory to a synchronous `derive(...)` policy:

```python
# V1: called during activation
def isolation_level(default, context):
    return getattr(context.parent.implementation, "isolation_level", default)

# V2: called during build for each static occurrence
def isolation_level(context: ParameterContext):
    parent = context.component.parent
    return getattr(parent.implementation, "isolation_level", context.default)

builder.register(
    TransactionManager,
    arguments={"isolation_level": derive(isolation_level)},
)
```

A derived policy returns a concrete value or `INJECT`. The latter compiles the normal component/scope-slot edge and
therefore preserves complete lifespan, cycle, missing-component, and async validation. Derived policies must be pure,
synchronous composition code: use a registered factory for runtime work or a declared scope slot for boundary data.

Unknown `arguments` keys fail build unless the target accepts `**kwargs`. To remove an inherited override while
patching, pass `arguments={"name": REMOVE}`.

## Composition and runtime must be separated

The most common migration error is retaining a runtime object where code still expects a registrator.

### Before build

Allowed on `ContainerBuilder` and `ScopeBuilder`:

- register and patch components;
- register decorators and pre-configurations;
- queue subclass/generic discovery;
- declare scope slots;
- apply bundles;
- mark entry points;
- inspect/preview component IDs.

### After build

Allowed on `Container` and `Scope`:

- resolve compiled roots;
- create ordinary scopes;
- provide declared slot values before resolution;
- create a `ScopeBuilder` for explicit child composition;
- inspect the build report and compiled graph;
- enter/exit sync or async ownership boundaries.

Do not add builder methods to a runtime to ease a migration. Move registration into the composition root instead.

## Filters now use `Component`

V1 registration and node filters operated on different models and sometimes on partially or fully resolved object graphs. V2 uses one immutable `Component` model for root registration, dependency, decorator, pre-configuration, and contextual selection.

Change imports:

```python
# V1
import clean_ioc.node_filters as nf
import clean_ioc.registration_filters as rf

# V2
import clean_ioc.component_filters as cf
```

Common mappings:

| V1 filter | V2 component filter |
| --- | --- |
| `rf.all_registrations` / `nf.yes` | `cf.all_components` |
| `rf.with_name(name)` / `nf.registration_name_is(name)` | `cf.with_name(name)` |
| `rf.with_id(id)` | `cf.with_id(id)` |
| `rf.with_implementation(T)` | `cf.implementation_is(T)` |
| `nf.implementation_type_is(T)` | `cf.implementation_type_is(T)` |
| `rf.with_implementation_matching_filter(f)` | `cf.implementation_matches_type_filter(f)` |
| `rf.has_generic_args_matching((key, value))` | `cf.has_generic_arg(key, value)` |
| `rf.has_tag(...)` / `nf.has_registration_tag(...)` | `cf.has_tag(...)` |
| `rf.has_lifespan(...)` | `cf.has_lifespan(...)` |
| `nf.service_type_is(T)` | `cf.service_type_is(T)` |
| `nf.jump_parent(f)` | `cf.parent(f)` |
| `nf.has_dependant_service_type(T)` | `cf.has_descendant(cf.service_type_is(T))` |
| `nf.has_dependant_implementation_type(T)` | `cf.has_descendant(cf.implementation_type_is(T))` |

There is no direct replacement for filters based on resolved instance type. User instances do not exist during build. Express the condition using service/implementation metadata, tags, names, generic bindings, or an explicit registration.

For predicates without a named replacement, use `cf.create_filter(lambda component: ...)`. `Component` exposes service
type, raw and normalized implementation, lifespan, name, tags, parent, dependencies, decorators, pre-configurations,
generic mapping, kind, activation, async and cleanup requirements, and decorator position.

Filter timing changes matter:

- `when=` on registration, decorator, and pre-configuration APIs is evaluated during build and frozen.
- `select(filter)` receives compiled components during build.
- collection selection preserves normal candidate order; V2 has no implicit collection reducer.
- a filter passed to `resolve()` only selects among already-compiled root plans.
- descendant filters see static dependency, decorator, and pre-configuration occurrences.

Do not port a V1 filter that depended on activation order or runtime instance state verbatim.

Replace contextual parent-node filters with component composition where possible:

```python
# V1
container.register(
    Gateway,
    WebGateway,
    parent_node_filter=nf.has_registration_tag("channel", "web"),
)

# V2
builder.register(
    Gateway,
    WebGateway,
    when=cf.parent(cf.has_tag("channel", "web")),
)
```

V2 decorator APIs use only `when=`. Combine V1's `registration_filter` and `decorator_node_filter` predicates into one component predicate. Decorator applicability is evaluated against the completed undecorated core subtree, so one decorator's dependencies cannot make another decorator eligible.

`register_decorator()` now returns a stable decorator-definition ID. Use it with `patch_decorator()` or `remove_decorator()` before build. Higher `position` values are outside lower values; equal positions retain registration order outside-to-inside.

Replace `register_generic_decorator(Service, Decorator)` with `register_decorator(Service, Decorator)`. Open decorator definitions are specialized from actual closed plans, including factory and fallback registrations, rather than only from discovered subclasses.

## Pre-configurations are compiled singleton initializers

V2 uses one `when=` predicate in place of the V1 pre-configuration `registration_filter=` argument:

```python
# V1
container.pre_configure(
    Client,
    configure_client,
    registration_filter=rf.with_name("external"),
)

# V2
builder.pre_configure(
    Client,
    configure_client,
    when=cf.with_name("external"),
)
```

The function remains lazy, but its signature and complete dependency path are compiled and validated during `build()`. A pre-configuration is effectively singleton-owned regardless of the triggering component's lifespan, so its path cannot contain scoped or `once_per_graph` state. Plain transient and singleton dependencies remain valid when their descendants are valid.

Passing several service types now creates one shared initializer. It runs once before the first applicable activation, in declaration order, and concurrent triggers share one in-flight attempt. In an overlay, inherited initializers run before those declared on the `ScopeBuilder`. Closed generic targets match exact compiled specializations; open generic targets match their specializations.

By default, a failure propagates and a later resolution may retry. With `continue_on_failure=True`, a failure inside the configuration function is logged and treated as a completed optional attempt, so it does not fail and log on every resolution. Dependency-resolution failures still propagate. Generator or context-manager cleanup belongs to the builder layer that declared the initializer, including when an inherited initializer is first triggered from an overlay.

An inherited initializer retains its frozen parent dependency plan, just like an inherited root singleton; an overlay cannot rewire it by overriding a dependency. If a parent definition had no applicable component and therefore no compiled plan, it cannot become newly applicable in an overlay. Register that initializer on the `ScopeBuilder` instead.

## Scopes, request values, and overrides

V1 scopes could accept registrations after creation. V2 ordinary scopes are runtime cache/value boundaries and never compile.

### Late request or framework value

Declare the hole before build, then provide the value before the scope's first resolve:

```python
builder = ContainerBuilder()
builder.declare_scope_slot(RequestContext)
builder.register(RequestHandler)
container = builder.build()

with container.new_scope() as scope:
    scope.provide(RequestContext, current_request)
    handler = scope.resolve(RequestHandler)
```

Only declared `(type, name)` slots may be provided. Duplicate provisions fail, and provisions lock once resolution starts. Nested ordinary scopes inherit provided values and may override them before their own first resolve.

### Child registration or decorator override

Use an explicit overlay build:

```python
test_builder = container.new_scope_builder()
test_builder.register(PaymentGateway, FakePaymentGateway)

with test_builder.build() as test_scope:
    service = test_scope.resolve(Checkout)
```

A built overlay starts a fresh scoped cache boundary. New overlay singletons belong to the overlay scope. Inherited root singletons remain anchored to their root activation plan and cannot be rewired by overlay dependencies or decorators.

Use an ordinary scope for the same composition and new request/unit-of-work state. Use a `ScopeBuilder` only when composition actually changes.

## Lifespan migration

V2 replaces the `Lifespan` enum with string literals. Remove the enum import and pass one of `"transient"`, `"once_per_graph"`, `"scoped"`, or `"singleton"`. The default remains `"once_per_graph"`.

```python
# V1
builder.register(Service, lifespan=Lifespan.singleton)

# V2
builder.register(Service, lifespan="singleton")
```

Compiled `Component.lifespan` values and graph manifests use the same strings. Invalid runtime strings raise `ValueError` during composition.

V2 also validates captive lifespans for all visible roots during build, so V1 code that silently promoted default dependencies beneath cached services may now fail.

Invalid paths include:

```text
singleton -> scoped
singleton -> once_per_graph
singleton -> transient -> once_per_graph
scoped -> once_per_graph
scoped -> transient -> once_per_graph
```

Valid examples include:

```text
singleton/scoped -> plain transient
transient -> once_per_graph
once_per_graph -> scoped/singleton
```

When `build()` reports `captive-dependency`:

1. Read the complete issue path from the cached owner to the offending dependency.
2. Decide the dependency's real ownership; do not merely hide it behind a transient wrapper.
3. Promote it to `scoped` or `singleton`, or shorten the consumer's lifespan.
4. Apply the same reasoning to factories, decorators, collections, provider fallbacks, and pre-configurations.

Example:

```python
# Invalid: Repository defaults to once_per_graph beneath a scoped UnitOfWork.
builder.register(Repository, SqlRepository)
builder.register(UnitOfWork, lifespan="scoped")

# Valid when both belong to the request/unit of work.
builder.register(Repository, SqlRepository, lifespan="scoped")
builder.register(UnitOfWork, lifespan="scoped")
```

V2 removes the `scoped_teardown` registration argument. Move acquisition and release into one generator or context-manager factory:

```python
# V1
container.register(
    Connection,
    factory=Connection.open,
    lifespan=Lifespan.scoped,
    scoped_teardown=Connection.close,
)

# V2
def connection_factory():
    connection = Connection.open()
    try:
        yield connection
    finally:
        connection.close()


builder.register(
    Connection,
    factory=connection_factory,
    lifespan="scoped",
)
```

Use `@contextmanager` or `@asynccontextmanager` when that makes the factory contract clearer. Always exit the owning container or scope, using async context management for async cleanup. If V1 registered a prebuilt instance with `scoped_teardown`, replace it with a factory so creation and cleanup have an explicit owner.

## Discovery and generics

V1 subclass and generic discovery happened when `register_subclasses()` or related methods were called. V2 queues rules and takes one live class snapshot during `build()`.

Migration requirements:

- import modules containing candidate subclasses before `build()`;
- retain dynamically created class objects until build because Python subclass tracking uses weak references;
- do not expect discovery methods to return registration IDs—they return `None` in V2;
- use `subclass_type_filter` from `clean_ioc.type_filters`, while component `when=` controls occurrence selection;
- remember that a successful build freezes the discovery snapshot; later subclasses do not join the runtime.

Open generic registrations are activation templates, not directly resolvable roots. Closed occurrences are compiled when encountered as dependencies. Explicitly register a closed service when callers must resolve it as a root.

Generic factory annotations are now specialized at build. Ensure factory parameters and return values preserve the relevant `TypeVar` relationships:

```python
T = TypeVar("T")

def create_product(dependency: Dependency[T]) -> Product[T]:
    return Product(dependency)

builder.register(Product, factory=create_product)
```

Use `factory_specialization=SomeClosedGeneric` only when the requested service and return annotation cannot reveal every binding. Unresolved/conflicting `TypeVar` values fail build. `ParamSpec` and `TypeVarTuple` are unsupported.

## Diagnostics and failure handling

V1 often discovered missing, circular, or captive dependencies during `resolve()`, unless code called `validate()` explicitly. V2 makes the successful build the validity boundary.

```python
from clean_ioc import ContainerBuildError

try:
    container = builder.build()
except ContainerBuildError as error:
    for issue in error.report.errors:
        print(issue.code, issue.path, issue.message)
```

Independent root failures are aggregated. Fix all reported paths, then call `build()` again on the same failed builder. After a successful build the builder is intentionally closed.

For inspection after success:

```python
print(container.build_report.to_text())
print(container.graph.to_text())
print(container.graph.to_mermaid())
manifest = container.graph.manifest()
```

Use `builder.mark_entrypoint(ApplicationRoot)` to focus the default graph view and enable `unreachable-component` warnings. All roots remain compiled and resolvable. JSON manifests are deterministic and redact configured/default values.

Do not replace `resolve_dependency_graph()` with runtime bookkeeping. If V1 code inspects nodes or instances after resolution, migrate it to static `Component`/`CompiledGraph` metadata or explicit application instrumentation.

## Injected container services

V1 code may inject `Registrator`, `Resolver`, `ScopeCreator`, `CurrentGraph`, or the mutable container itself.

- Remove injected `Registrator`; V2 runtimes are immutable. Move registration to a builder.
- Replace request/framework registration with declared slots and `provide()`.
- Replace intentional child composition with an injected/configured `ScopeBuilder` at the composition boundary, not in ordinary services.
- Prefer explicit constructor dependencies over an injected resolver.
- If dynamic selection among compiled roots is unavoidable, inject public `ResolutionContext`.
- Inject public `Scope` only when the service genuinely owns creation of nested runtime scopes.

`ResolutionContext` can only select already-compiled roots and preserves `once_per_graph` identity. It is not a mutation or compilation API.

## FastAPI migration

Build the immutable container, then install it on the application:

```python
builder = ContainerBuilder()
builder.register(Repository, lifespan="scoped")
builder.register(Service)
container = builder.build()

app = FastAPI()
install_fastapi(app, container)
```

The V2 extension requires FastAPI 0.121 or newer. It owns the root container for the application lifespan and creates one ordinary child scope for each complete HTTP request or WebSocket connection. `Resolve(Service)` still resolves a route dependency, but its filter is now a component filter. Every `Resolve` selection is checked against the compiled container during FastAPI startup.

If application components consume `Request`, `WebSocket`, `RequestHeaderReader`, or `ResponseHeaderWriter`, call `configure_fastapi(builder)` before `build()`. The middleware provides those late boundary values automatically; remove V1 global `Depends(add_*_to_scope)` configuration. The old lifespan and individual provision helpers are not part of V2.

For test overrides, compile a `ScopeBuilder` overlay and pass that built scope to `install_fastapi` on a test application instance. Use the configured slots instead when only request data changes.

## Bundles and reusable integrations

V1 bundles often accepted `Container` and registered directly. V2 bundles should accept the structural protocol:

```python
from clean_ioc import ComponentBuilder

def add_persistence(builder: ComponentBuilder) -> None:
    builder.register(Database, lifespan="singleton")
    builder.register(Repository, SqlRepository, lifespan="scoped")
```

This works with both `ContainerBuilder` and `ScopeBuilder`. A bundle is composition-only and must not resolve services or retain the builder for later mutation.

If an integration needs a late external value, expose a helper that declares its slots on `ComponentBuilder` and a runtime helper that provides those values on `Scope`.

## Common migration failures

| Symptom | Cause | Fix |
| --- | --- | --- |
| V2 `Container` cannot be constructed | Runtime construction is internal | Create `ContainerBuilder`, compose, then `build()`. |
| `Container`/`Scope` has no `register` | Runtime is immutable | Move composition earlier, declare a slot, or build an overlay. |
| `BuilderAlreadyBuiltError` | Mutation or second build after success | Create a new builder; do not reuse a successful one. |
| `ContainerBuildError: missing-component` | V2 compiled a root V1 had never exercised | Register the dependency or remove the invalid visible root. |
| `captive-dependency` mentioning `once-per-graph` | Cached owner retained default graph-local state | Promote the dependency or shorten the owner. |
| `missing-entrypoint` | Marker filter selected no root | Register/fix the root or correct its component filter. |
| `unreachable-component` under `--strict` | Registration is outside all marked entry-point trees | Mark the real entry point, remove the registration, or explicitly ignore the warning. |
| Old filter raises an attribute error during build | It expects `Registration`, `Node`, or an instance | Rewrite it against public `Component`. |
| Dynamic subclass is missing | It was created/imported after build or garbage-collected | Import/create and retain it before build. |
| Open generic cannot be resolved as a root | Open registrations are templates | Register the required closed root explicitly. |
| Generic factory has unresolved `TypeVar` | Binding is absent from service/return annotations | Correct annotations or provide `factory_specialization`. |
| Sync resolution says async is required | Compiled path contains async activation/cleanup | Use `resolve_async()` and async context ownership. |
| Overlay unexpectedly reuses a root singleton | Root singleton plans are anchored by design | Register an overlay-owned replacement singleton if different wiring is required. |

## Agent migration workflow

1. Search for legacy construction and imports:

   ```bash
   rg -n "Container\(|\.register\(|\.patch_registration\(|registration_filters|node_filters|resolve_dependency_graph|\.validate\(|\.explain\(" .
   rg -n "clean_ioc\.(core|registration_filters|node_filters|diagnostics)|use_registered|use_from_current_graph" .
   ```

2. Convert each composition root to `ContainerBuilder -> build -> Container`. Do not scatter builders through application services.
3. Move all mutations before build. Classify later mutations as root composition, scope slots, or explicit scope overlays.
4. Rewrite filters against `Component` and remove runtime-instance predicates.
5. Run the smallest affected tests. Fix every build report path, especially default `once_per_graph` dependencies beneath scoped/singleton owners.
6. Import all discovery candidates before build and make generic roots/factory bindings explicit.
7. Update integrations and bundles to accept `ComponentBuilder`; update runtime code to accept immutable `Scope`/`Container` only where necessary.
8. Add regression tests that prove build-time failure or frozen runtime behavior rather than expecting a resolve-time error.
9. Run the full repository checks:

   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run ty check .
   uv run pytest .
   uv run pre-commit run --all-files
   uv build
   ```

Do not consider a migration complete merely because imports type-check. It is complete when composition builds successfully, runtime objects are immutable, request values use declared slots, ownership/cleanup is explicit, filters use static components, and tests no longer depend on V1's runtime graph construction.
