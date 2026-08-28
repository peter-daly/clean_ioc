# Component filtering

Clean IoC 2 uses one immutable `Component` model and one filter vocabulary everywhere.

```python
import clean_ioc.component_filters as cf
from clean_ioc import Component, ContainerBuilder, DependencySettings, Lifespan, Tag
```

A component occurrence exposes:

- stable registration `id` and occurrence-specific `occurrence_id`;
- `service_type`, `implementation`, and normalized `implementation_type`;
- `lifespan`, `name`, `tags`, `kind`, and incoming `argument`;
- `generic_mapping`;
- read-only `parent`, `dependencies`, `decorators`, `decorated`, and `pre_configurations`;
- static descendant queries.

It deliberately has no runtime `instance` or `instance_type`. Composition, dependency, decorator, and pre-configuration filters are evaluated at build time and their decisions are frozen. A filter passed directly to `resolve(...)` selects among the already-compiled roots at runtime; it cannot alter their dependency plans.

## Root selection

```python
builder = ContainerBuilder()
builder.register(str, instance="development", name="dev")
builder.register(str, instance="production", tags=[Tag("env", "prod")])
container = builder.build()

assert container.resolve(str, filter=cf.with_name("dev")) == "development"
assert container.resolve(str, filter=cf.has_tag("env", "prod")) == "production"
```

The default filter selects unnamed components.

## Dependency selection

```python
class Client:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint


builder = ContainerBuilder()
builder.register(str, instance="https://api.example", name="api")
builder.register(
    Client,
    dependency_config={
        "endpoint": DependencySettings(filter=cf.with_name("api")),
    },
)
container = builder.build()
```

Collections use the same predicate and an optional component-list modifier.

## Contextual registration with `when=`

`when` decides whether a registered component is eligible for one static occurrence. Parent-aware rules are explicit:

```python
class SqlConnection:
    pass


class DocumentConnection:
    pass


builder.register(
    Connection,
    SqlConnection,
    when=cf.parent(cf.has_tag("database", "sql")),
)
builder.register(
    Connection,
    DocumentConnection,
    when=cf.parent(cf.has_tag("database", "document")),
)
```

The compiler builds occurrence-specific plans, so the same registration can make different decisions under different generic parents.

## Decorator selection sees the undecorated core

```python
builder.register_decorator(
    Handler,
    TransactionDecorator,
    when=cf.has_descendant(cf.service_type_is(SqlConnection)),
)
```

All decorator predicates are evaluated against the completed undecorated component subtree. Dependencies introduced by one decorator cannot accidentally cause another decorator to become eligible.

The same `when=` argument is available on `pre_configure(...)`.

## Composing filters

Built-in predicates are composable through `funcie`:

```python
production_stripe = cf.has_tag("env", "prod") & cf.with_name("stripe")
not_singleton = ~cf.has_lifespan(Lifespan.singleton)
```

Useful helpers include:

- `with_name`, `with_id`, `name_starts_with`, `name_ends_with`;
- `implementation_is`, `implementation_matches_type_filter`;
- `service_type_is`;
- `has_tag`, `has_generic_arg`;
- `has_lifespan`, `has_lifespan_in`;
- `parent`, `has_descendant`.

Use `create_filter(callable)` for a custom composable predicate.

## Component IDs and patching

Builder queries use component terminology:

```python
component_id = builder.get_component_id(Service, filter=cf.with_name("primary"))
component_ids = builder.get_component_ids(Service)
exists = builder.has_component(Service)

if component_id is not None:
    builder.patch_component(Service, component_id, lifespan=Lifespan.singleton)
```

Queries and patches must happen before a successful `build()`.
