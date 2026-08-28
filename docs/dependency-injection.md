# Dependency Injection (DI)

Dependency Injection is a concrete IoC technique: dependencies are provided from outside the object, typically by a container.

## Constructor injection with Clean IoC

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

## Benefits

- lower coupling
- easier testing via swapped registrations
- clear dependency graph
- lifecycle management through lifespans/scopes

## In tests

```python
from clean_ioc import ContainerBuilder


class Logger:
    def info(self, message: str):
        pass


class FakeLogger(Logger):
    def __init__(self):
        self.messages = []

    def info(self, message: str):
        self.messages.append(message)


class Service:
    def __init__(self, logger: Logger):
        self.logger = logger

    def run(self):
        self.logger.info("ok")


builder = ContainerBuilder()
builder.register(Logger, FakeLogger)
builder.register(Service)
container = builder.build()

service = container.resolve(Service)
service.run()
assert service.logger.messages == ["ok"]
```
