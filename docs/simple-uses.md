# Simple uses

All composition happens on `ContainerBuilder`; all resolution happens after `build()`.

```python
from clean_ioc import ContainerBuilder
```

## Implementation mapping

```python
builder = ContainerBuilder()
builder.register(UserRepository, InMemoryUserRepository)
builder.register(UserService)
container = builder.build()

service = container.resolve(UserService)
```

## Concrete component

```python
builder = ContainerBuilder()
builder.register(RandomNumberProvider)
container = builder.build()
```

## Factory

```python
def create_config() -> AppConfig:
    return AppConfig(environment="production")


builder = ContainerBuilder()
builder.register(AppConfig, factory=create_config)
container = builder.build()
```

Factory parameters are dependency-injected from the same compiled plan. Async functions, generators, async generators, and context-manager functions are supported.

## Existing instance

```python
settings = AppConfig(environment="test")

builder = ContainerBuilder()
builder.register(AppConfig, instance=settings)
container = builder.build()

assert container.resolve(AppConfig) is settings
```

## Multiple components and collections

```python
builder = ContainerBuilder()
builder.register(Plugin, FirstPlugin)
builder.register(Plugin, SecondPlugin)
container = builder.build()

plugins = container.resolve(list[Plugin])
```

Collections preserve component order and use the same filter vocabulary as individual dependencies.

## Named components

```python
import clean_ioc.component_filters as cf

builder = ContainerBuilder()
builder.register(int, instance=1)
builder.register(int, instance=2, name="two")
container = builder.build()

assert container.resolve(int) == 1
assert container.resolve(int, filter=cf.with_name("two")) == 2
```

## Build does not activate user code

```python
calls = 0


def token_factory() -> str:
    global calls
    calls += 1
    return "token"


builder = ContainerBuilder()
builder.register(str, factory=token_factory)
container = builder.build()
assert calls == 0

container.resolve(str)
assert calls == 1
```
