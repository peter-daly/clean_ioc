# Generics

Clean IoC supports open-generic registration patterns.

```python
from typing import Generic, TypeVar

from clean_ioc import Container
```

## Generic subclasses

```python
T = TypeVar("T")


class Command:
    pass


class HelloCommand(Command):
    pass


class GoodbyeCommand(Command):
    pass


class CommandHandler(Generic[T]):
    def handle(self, command: T) -> str:
        raise NotImplementedError


class HelloCommandHandler(CommandHandler[HelloCommand]):
    def handle(self, command: HelloCommand) -> str:
        return "HELLO"


class GoodbyeCommandHandler(CommandHandler[GoodbyeCommand]):
    def handle(self, command: GoodbyeCommand) -> str:
        return "GOODBYE"


container = Container()
container.register_generic_subclasses(CommandHandler)

h1 = container.resolve(CommandHandler[HelloCommand])
h2 = container.resolve(CommandHandler[GoodbyeCommand])

print(h1.handle(HelloCommand()))
print(h2.handle(GoodbyeCommand()))
```

Important: subclass modules must be imported before `register_generic_subclasses(...)` runs.

## Fallback type

```python
class DefaultCommandHandler(CommandHandler[T]):
    def handle(self, command: T) -> str:
        return "DEFAULT"


container = Container()
container.register_generic_subclasses(CommandHandler, fallback_type=DefaultCommandHandler)
```

## Generic decorators

```python
class LoggingHandlerDecorator(Generic[T]):
    def __init__(self, child: CommandHandler[T]):
        self.child = child

    def handle(self, command: T) -> str:
        print("handling", type(command).__name__)
        return self.child.handle(command)


container = Container()
container.register_generic_subclasses(CommandHandler)
container.register_generic_decorator(CommandHandler, LoggingHandlerDecorator)

handler = container.resolve(CommandHandler[HelloCommand])
print(handler.handle(HelloCommand()))
```
