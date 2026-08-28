# Parameter value providers

`DependencySettings.value_factory` can supply a constructor/factory parameter at activation time.

```python
from clean_ioc import ContainerBuilder, DependencyContext, DependencySettings, EMPTY


def isolation_level(default, context: DependencyContext):
    message_type = context.parent.generic_mapping["TMessage"]
    return getattr(message_type, "isolation_level", default)


builder = ContainerBuilder()
builder.register(
    TransactionManager,
    dependency_config={
        "isolation_level": DependencySettings(value_factory=isolation_level),
    },
)
container = builder.build()
```

The provider does not run during `build()`. The compiler freezes its static `DependencyContext` and compiles a normal fallback edge. At activation:

1. the provider receives the parameter's default value and static context;
2. any result other than `EMPTY` is used;
3. `EMPTY` executes the precompiled fallback component edge.

The context exposes the current component, its static parent, service, implementation, and decorated occurrence. It never exposes runtime instances.

## Built-in providers

```python
from clean_ioc.value_factories import dont_use_default_value, set_value, use_default_value
```

- `use_default_value` always uses the Python default;
- `dont_use_default_value` returns `EMPTY`, forcing the compiled component fallback;
- `set_value(value)` always supplies one explicit value.

Constant `dependency_config` values are shorthand for `set_value(...)`:

```python
builder.register(Client, dependency_config={"timeout": 5.0})
```

Use a declared scope slot instead when the value belongs to a request or framework boundary and should be shared by multiple components.
