# Generics

Clean IoC has powerful generic features that allow you to use Generics to auto register all subclases.
This allows you to use homogonous class structures that can be automatically registered within the container. Some features where this can be useful is in building event handlers or message handlers.

## Generic Subclasses

Lets start with the below.

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

To add another CommandHandler we simply just declare the Command type and Handler class

```python
class AlohaCommand:
    pass


class AlohaCommandHandler(CommandHandler[AlohaCommand]):
    def handle(self, command: AlohaCommand):
        print('ALOHA')

h1 = container.resolve(CommandHandler[HelloCommand])
h2 = container.resolve(CommandHandler[GoodbyeCommand])
h3 = container.resolve(CommandHandler[AlohaCommand])

h1.handle(HelloCommand()) # prints 'HELLO'
h2.handle(GoodbyeCommand()) # prints 'GOODBYE'
h3.handle(AlohaCommand()) # prints 'ALOHA'
```

Leveraging Clean IoC's Resolver dependency you can take it a step further and build a dispatch mechanism

```python
class CommandDispatcher:
    def __init__(self, reslover: Resolver):
        self.resolver = resolver

    def dispatch(self, command):
        command_type = type(command)
        handler = self.resolver.resolve(CommandHandler[command_type])
        handler.handle(command)

container.register(CommandDispatcher)

dispatcher = container.resolve(CommandDispatcher)

dispatcher.dispatch(HelloCommand()) # prints 'HELLO'
dispatcher.dispatch(GoodbyeCommand()) # prints 'GOODBYE'
dispatcher.dispatch(AlohaCommand()) # prints 'ALOHA'
```

## Generic Decorators

There is also a special function in Clean IoC for handling generic decorators. This allows you to decorate your generic subclasses, but also have a concrete implementation of the decorator for that concrete generic type.

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

Clean IoC will also respect generic dependencies of the generic decorator so you can have custom features per different concrete type.

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

class PrependMessageGetter(Generic[T]):
    def get_message(self):
        pass

class HelloMessageGetter(PrependMessageGetter[HelloCommand]):
    def get_message(self):
        return "A VERY HAPPY"

class GoodbyeMessageGetter(PrependMessageGetter[GoodbyeCommand]):
    def get_message(self):
        return "A VERY SAD"


class PrependMessageCommandHandlerDecorator(Generic[T]):
    def __init__(self, handler: CommandHandler[T], prepend_message_getter: PrependMessageGetter[T]):
        self.handler = handler
        self.prepend_message_getter = prepend_message_getter

    def handle(self, command: T):
        prepend_message = self.prepend_message_getter.get_message()
        print(prepend_message)
        self.handler.handle(command=command)

container = Container()
container.register_generic_subclasses(CommandHandler)
container.register_generic_subclasses(PrependMessageGetter)
container.register_generic_decorator(CommandHandler, AVeryBigCommandHandlerDecorator)
h1 = container.resolve(CommandHandler[HelloCommand])
h2 = container.resolve(CommandHandler[GoodbyeCommand])

h1.handle(HelloCommand()) # prints 'A VERY HAPPY\nHELLO'
h2.handle(GoodbyeCommand()) # prints 'A VERY SAD\nGOODBYE'
```
