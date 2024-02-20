
## Generics

Registers all generic subclasses of the service type and allows you to resolve with the generic alias

```python
T = TypeVar("T")

class HelloCommand:
    pass

class GoodbyeCommand:
    pass

class CommandHandler(Generic[T]):
    def handle(self, command: T):
        pass

class HelloCommandHandler(CommandHandler[HelloCommand]):
    def handle(self, command: HelloCommand):
        print('HELLO')

class GoodbyeCommandHandler(CommandHandler[GoodbyeCommand]):
    def handle(self, command: GoodbyeCommand):
        print('GOODBYE')

container = Container()
container.register_generic_subclasses(CommandHandler)

h1 = container.resolve(CommandHandler[HelloCommand])
h2 = container.resolve(CommandHandler[GoodbyeCommand])

h1.handle(HelloCommand()) # prints 'HELLO'
h2.handle(GoodbyeCommand()) # prints 'GOODBYE'

```

## Generic Decorators


Allows you to add decorators to your generic registrations

```python
T = TypeVar("T")

class HelloCommand:
    pass

class GoodbyeCommand:
    pass

class CommandHandler(Generic[T]):
    def handle(self, command: T):
        pass

class HelloCommandHandler(CommandHandler[HelloCommand]):
    def handle(self, command: HelloCommand):
        print('HELLO')

class GoodbyeCommandHandler(CommandHandler[GoodbyeCommand]):
    def handle(self, command: GoodbyeCommand):
        print('GOODBYE')

class AVeryBigCommandHandlerDecorator(Generic[T]):
    def __init__(self, handler: CommandHandler[T]):
        self.handler = handler

    def handle(self, command: T):
        print('A VERY BIG')
        self.handler.handle(command=command)

container = Container()
container.register_generic_subclasses(CommandHandler)
container.register_generic_decorator(CommandHandler, AVeryBigCommandHandlerDecorator)
h1 = container.resolve(CommandHandler[HelloCommand])
h2 = container.resolve(CommandHandler[GoodbyeCommand])

h1.handle(HelloCommand()) # prints 'A VERY BIG\nHELLO'
h2.handle(GoodbyeCommand()) # prints 'A VERY BIG\nGOODBYE'

```