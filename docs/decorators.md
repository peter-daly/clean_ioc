# Decorators

Clean IoC allows you to add extra functionality to dependencies via decoration.
It achieves this with what would look traditionally like an Object Orientated decorator pattern. This is very different to traditional python decorator functions.

!!! question "Why use a different decorator pattern?. This looks like Java"

    Python class decorators either mutate or wrap the decorated class in order to add new dependencies to the decorators it would have to dynamically change the the classes __init__ function, but since we can define a separate  Service Type from the Implementation Type changing the `__init__` method just becomes messy.
    In Clean IoC we decorate the instance rather than the class itself, this has the following advantages.

    1. It allows the decorators to have their own dependencies that are registered within the container.
    2. It allows you to focus on decorating the abstract type rather then the implementation type.
    3. When we just register an instances, it can also be decorated.
    4. Allows us to selectively apply decorators.

!!! question "Are you suggesting that python should change how it traditionally does decoration for cross cutting concerns?"

    Nope. When adding cross cutting concerns to classes and functions in python, traditional python decorators work fantastically. It's also not a case of one or the other. For example if you want to register `dataclasses` and also add decorators instance of those classes you can absolutely do that.

```python
class MessageSender(Protocol):
    def send(self, message: str):
        ...

class EmailMessageSender(MessageSender):
    def send(self, message: str):
        ## DO EMAIL STUFF
        ...

class LoggingMessageSender(MessageSender):
    def __init__(self, sender: MessageSender):
        self.sender = sender
        def send(self, message: str):
            logger.info("SENDING MESSAGE")
            self.sender.send(message)
            logger.info("MESSAGE SENT")

container = Container()

container.register(MessageSender, EmailMessageSender)
container.register_decorator(MessageSender, LoggingMessageSender)

sender = container.resolve(MessageSender)

sender.send("HELLO") # logs while sending
```

## Decorator ordering

By default decorators are resolved in order of when first registered. So the first registered decorator is the highest the object tree.

```python
    class Abstract:
        pass

    class Concrete:
        pass

    class DecoratorOne(Abstract):
        def __init__(self, child: Abstract):
            self.child = child

    class DecoratorTwo(Abstract):
        def __init__(self, child: Abstract):
            self.child = child

    container = Container()

    container.register(Abstract, Concrete)
    container.register_decorator(Abstract, DecoratorOne)
    container.register_decorator(Abstract, DecoratorTwo)

    root = container.resolve(Abstract)

    type(root) # returns DecoratorOne
    type(root.child) # returns DecoratorTwo
    type(root.child.child) # returns Concrete
```

However if you want more control over the ordering you can also set the `position` arg when registering the decorator.
The `position` arg is an integer.

!!! info
    The higher the `position` number the higher the position in the tree.
    By default `position` is 0.

```python

    class Abstract:
        pass

    class Concrete:
        pass

    class DecoratorHigh(Abstract):
        def __init__(self, child: Abstract):
            self.child = child

    class DecoratorMid(Abstract):
        def __init__(self, child: Abstract):
            self.child = child

    class DecoratorLow(Abstract):
        def __init__(self, child: Abstract):
            self.child = child

    container = Container()

    container.register(Abstract, Concrete)
    container.register_decorator(Abstract, DecoratorMid)
    container.register_decorator(Abstract, DecoratorLow, position=-10)
    container.register_decorator(Abstract, DecoratorHigh, position=10)

    root = container.resolve(Abstract)

    type(root) # returns DecoratorHigh
    type(root.child) # returns DecoratorMid
    type(root.child.child) # returns DecoratorLow
    type(root.child.child.child) # returns Concrete
```

## Manually setting decorated arg

Clean IoC will try to work out the decorated arg in the decorator based on the arg type annotations.
If for any reason that doesn't work you can fallback to setting it explicitly

Taking our previous message sending example.

```python
class MessageSender(Protocol):
    def send(self, message: str):
        ...

class EmailMessageSender(MessageSender):
    def send(self, message: str):
        ## DO EMAIL STUFF
        ...

class LoggingMessageSender(MessageSender):
    def __init__(self, sender: MessageSender):
        self.sender = sender
        def send(self, message: str):
            logger.info("SENDING MESSAGE")
            self.sender.send(message)
            logger.info("MESSAGE SENT")

container = Container()

container.register(MessageSender, EmailMessageSender)
container.register_decorator(MessageSender, LoggingMessageSender, decorated_arg="sender")

sender = container.resolve(MessageSender)

sender.send("HELLO") # logs while sending
```

## Using functions and generators as decorators

You can also use functions and generators (sync and async) as decorators.
These can be useful if you want to wrap the use of the object in a context manager for any reason.

```python
class MessageSender(Protocol):
    def send(self, message: str):
        ...

class EmailMessageSender(MessageSender):
    def send(self, message: str):
        ## DO EMAIL STUFF
        ...

def use_sender_within_some_context_manager(sender: MessageSender):
    with my_context_manager():
        yield sender

container = Container()

container.register(MessageSender, EmailMessageSender)
container.register_decorator(MessageSender, use_sender_within_some_context_manager, decorated_arg="sender")

sender = container.resolve(MessageSender) # sender is now within a context manager
```
