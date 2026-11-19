# Dependency injection

Dependency injection supplies an object's collaborators from outside the object. Clean IoC uses constructor and factory
annotations to compile those relationships into component edges.

## Constructor injection

```python
from clean_ioc import ContainerBuilder


class Logger:
    def info(self, message: str):
        print(message)


class UserService:
    def __init__(self, logger: Logger):
        self.logger = logger

    def run(self):
        self.logger.info("running")


builder = ContainerBuilder()
builder.register(Logger)
builder.register(UserService)
container = builder.build()

container.resolve(UserService).run()
```

During `build()`, the `logger` parameter becomes a dependency edge from `UserService` to `Logger`. Missing, ambiguous,
circular, and invalid lifespan paths are reported before either constructor runs.

## Alternate test composition

Tests can build a separate root or a compiled scope overlay with different implementation mappings:

```python
class FakeLogger(Logger):
    def __init__(self):
        self.messages: list[str] = []

    def info(self, message: str):
        self.messages.append(message)


builder = ContainerBuilder()
builder.register(Logger, FakeLogger)
builder.register(UserService)
container = builder.build()

service = container.resolve(UserService)
service.run()
assert service.logger.messages == ["running"]
```

The application class is unchanged. Only the composition root selects a different implementation.
