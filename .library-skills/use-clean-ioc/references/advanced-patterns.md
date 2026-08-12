# Advanced Clean IoC Patterns

Use this reference only when the task requires behavior beyond direct registration, resolution, lifespans, and scopes.

## Contents

- [Factories and cleanup](#factories-and-cleanup)
- [Dependency settings](#dependency-settings)
- [Registration and node filtering](#registration-and-node-filtering)
- [Decorators](#decorators)
- [Bundles and pre-configuration](#bundles-and-pre-configuration)
- [Subclass and generic discovery](#subclass-and-generic-discovery)
- [Graph-aware injected types](#graph-aware-injected-types)
- [Factory helpers](#factory-helpers)
- [Value factories](#value-factories)

## Factories and cleanup

Type-annotate factory parameters so Clean IoC can inject them:

```python
def client_factory(settings: Settings, transport: Transport) -> Client:
    return Client(settings, transport)


container.register(Client, factory=client_factory)
```

Use `resolve_async(...)` when a factory is async. Use a generator, `@contextmanager`, async generator, or `@asynccontextmanager` to colocate acquisition and cleanup. Match the context type to the execution path and always exit the owning scope or container.

Cleanup ownership follows lifespan:

- `scoped` finalizers run when the owning scope exits;
- `singleton` finalizers run when the root container exits;
- resources resolved without exiting their owner do not flush automatically.

## Dependency settings

Inline a fixed constructor or factory argument directly in a registration's `dependency_config`:

```python
container.register(
    Client,
    dependency_config={"x": 12345},
)
```

Use the exact parameter name as the key. A non-`DependencySettings` entry is converted internally to `DependencySettings(value_factory=constant(value))`, so it supplies that object unchanged and overrides any declared parameter default.

Use an explicit `DependencySettings` when a parameter needs resolution behavior rather than a fixed value:

```python
from clean_ioc import Container, DependencySettings
from clean_ioc.registration_filters import with_name

container.register(str, instance="postgresql://prod", name="database_url")
container.register(
    Database,
    dependency_config={
        "url": DependencySettings(filter=with_name("database_url")),
    },
)
```

Each setting can define:

- `filter`: select registrations for that parameter;
- `value_factory`: supply or alter a parameter value;
- `list_modifier`: reorder or reduce registrations before resolving a collection.

Apply the configuration to the registration whose constructor/factory owns that parameter.

## Registration and node filtering

Use registration filters for top-down selection. Public helpers live in `clean_ioc.registration_filters`, including `with_name`, `with_id`, `has_tag`, `with_implementation`, and lifespan/name predicates. These predicates support composition where provided by `funcie`:

```python
from clean_ioc.registration_filters import has_tag, with_name

production = has_tag("environment", "production")
primary_or_fallback = with_name("primary") | with_name("fallback")
```

Pass filters to `resolve(...)`, `resolve_async(...)`, `Resolve(...)`, factory helpers, or `DependencySettings` according to where selection belongs.

Use `parent_node_filter` for bottom-up selection, where a child registration decides whether it applies to its current parent:

```python
import clean_ioc.node_filters as nf

container.register(
    Gateway,
    InternalGateway,
    parent_node_filter=nf.implementation_type_is(InternalService),
)
```

Use node filtering only when parent context genuinely changes the implementation. Prefer named/tagged top-down configuration for simpler cases.

Use `DependencySettings(list_modifier=...)` when collection order or reduction is domain-specific. Keep modifiers deterministic and return a list of registrations.

## Decorators

Register Clean IoC decorators to wrap resolved service instances and inject additional decorator dependencies:

```python
class LoggingHandler:
    def __init__(self, child: Handler, logger: Logger):
        self.child = child
        self.logger = logger


container.register(Handler, ConcreteHandler)
container.register_decorator(Handler, LoggingHandler)
```

Set `decorated_arg` when the wrapped parameter cannot be inferred from its annotation. Apply `registration_filter` to choose registrations and `decorator_node_filter` to choose graph positions.

For multiple decorators, lower `position` values are applied first and higher values become outer wrappers. Test the resulting chain order explicitly.

Function, generator, and async generator decorators are supported. Use the same sync/async ownership rules as factories.

## Bundles and pre-configuration

Use a bundle to group related registrations:

```python
def application_bundle(container: Container) -> None:
    container.register(Repository, SqlRepository)
    container.register(Service)


container.apply_bundle(application_bundle)
```

Use classes from `clean_ioc.bundles` when bundle execution must be restricted to once per class or instance.

When application setup must customize part of a reusable bundle, retain the ID returned by `register(...)` and patch that registration before resolving it:

```python
from clean_ioc import Tag

registration_id = container.register(
    Client,
    dependency_config={"endpoint": "https://default.example"},
    tags=[Tag("source", "bundle")],
)

container.patch_registration(
    Client,
    registration_id,
    dependency_config={"endpoint": "https://application.example"},
    tags=[Tag("source", "application")],
)
```

Patches shallow-merge dependency settings and merge tags by tag name. They may also replace the lifespan. Use `RemoveDependencySetting` to remove a dependency override. Patch only the registry that owns the ID and always patch before first resolution; late patches raise `RuntimeError`.

Use `pre_configure(...)` for setup that must run before matching services are first built:

```python
container.pre_configure(Logger, configure_logging)
```

Pre-configuration functions can receive injected dependencies. Use `registration_filter` to limit applicability. Set `continue_on_failure=True` only when setup failure is intentionally optional.

## Subclass and generic discovery

Use `register_subclasses(Base)` to register imported, concrete subclasses as implementations of `Base`. Apply `subclass_type_filter` to narrow discovery.

Use `register_generic_subclasses(OpenGeneric)` for closed generic mappings:

```python
container.register_generic_subclasses(Handler)
handler = container.resolve(Handler[CreateUser])
```

Import every module defining candidate subclasses before registration. Discovery cannot find classes that Python has not imported.

Use `fallback_type=` for generic combinations with no exact discovered implementation. Exact closed mappings take precedence. Without a mapping or fallback, resolution raises `CannotResolveError`.

Register generic decorators after subclass discovery:

```python
container.register_generic_subclasses(Handler)
container.register_generic_decorator(Handler, LoggingHandlerDecorator)
```

Do not assume a generic decorator applies to unmatched fallback-only combinations; they are not part of the discovered closed mapping.

## Graph-aware injected types

Inject these public types only for cases that cannot remain ordinary constructor injection:

- `Resolver`: resolve dynamically against the current container or scope;
- `CurrentGraph`: find an instance already created within the active graph;
- `DependencyContext`: inspect the current parent/dependency node;
- `Container`, `Scope`, or `Registrator`: access their active registered instances directly.

Use `Lifespan.transient` for dependencies whose factories derive values from `DependencyContext`, because graph context can vary between injection sites.

Avoid turning graph-aware types into a service locator throughout application code. Confine dynamic resolution to composition boundaries and factories.

## Factory helpers

Import reusable factory builders from `clean_ioc.factories`:

- `use_registered(...)` / `use_registered_async(...)`: expose another registered service, optionally with a filter;
- `use_from_current_graph(...)` / `use_from_current_graph_async(...)`: reuse an object already created in the active graph through another service type;
- `create_type_mapping(...)` / `create_type_mapping_async(...)`: resolve all matching services and key them into a dictionary.

Example:

```python
from clean_ioc.factories import use_registered

container.register(ConcreteSender)
container.register(Sender, factory=use_registered(ConcreteSender))
```

Choose the async helper when the delegated resolution graph is asynchronous.

## Value factories

Prefer an inline `dependency_config` value for a fixed override:

```python
container.register(Client, dependency_config={"timeout": 5.0})
```

Import value factories as a module when the behavior itself must be represented explicitly:

```python
import clean_ioc.value_factories as vf
from clean_ioc import DependencySettings

container.register(
    Client,
    dependency_config={
        "timeout": DependencySettings(value_factory=vf.set_value(5.0)),
    },
)
```

Use:

- `vf.set_value(value)` to construct an explicit constant value factory;
- `vf.use_default_value` to force the callable's declared default;
- `vf.dont_use_default_value` to ignore the default and resolve the parameter from registrations.

Prefer inline values for ordinary fixed overrides, a custom value factory for context-sensitive parameter overrides, and a registration factory for object construction. Do not mix those responsibilities.
