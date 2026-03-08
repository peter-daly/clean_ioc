# Decorators

`register_decorator` wraps resolved service instances.

```python
from typing import Protocol

from clean_ioc import Container
```

## Clean IoC decorators vs Python `@decorator`

Clean IoC decorators and Python decorators solve different problems:

- Clean IoC decorators are runtime, instance-level wrappers applied during dependency resolution.
- Python `@decorator` functions/classes are definition-time wrappers applied when a function/class is declared.

### Clean IoC decorators (`register_decorator`)

- Applied by the container after a service is constructed.
- Can use dependency injection for decorator dependencies.
- Can be filtered by registration, node context, and ordering (`position`).
- Great for DI-driven cross-cutting concerns in object graphs.

### Python decorators (`@my_decorator`)

- Applied directly to functions/classes in source code.
- Do not require a DI container.
- Great for local behavior changes such as caching, retries, timing, auth checks, and function instrumentation.

Both are valid and can be used together.

For example, you can decorate a method with `@retry(...)` and still register a Clean IoC decorator around the service instance that owns that method.

## Basic decorator

```python
class MessageSender(Protocol):
    def send(self, message: str) -> None:
        ...


class EmailMessageSender:
    def send(self, message: str) -> None:
        print(f"EMAIL: {message}")


class LoggingMessageSender:
    def __init__(self, child: MessageSender):
        self.child = child

    def send(self, message: str) -> None:
        print("before")
        self.child.send(message)
        print("after")


container = Container()
container.register(MessageSender, EmailMessageSender)
container.register_decorator(MessageSender, LoggingMessageSender)

sender = container.resolve(MessageSender)
sender.send("hello")
```

## Ordering

Lower `position` runs first. Highest position becomes outermost wrapper.

```python
class A(Protocol):
    def run(self) -> None:
        ...


class BaseA:
    def run(self) -> None:
        print("base")


class D1:
    def __init__(self, child: A):
        self.child = child

    def run(self) -> None:
        print("d1")
        self.child.run()


class D2:
    def __init__(self, child: A):
        self.child = child

    def run(self) -> None:
        print("d2")
        self.child.run()


container = Container()
container.register(A, BaseA)
container.register_decorator(A, D1, position=0)
container.register_decorator(A, D2, position=10)

root = container.resolve(A)
root.run()
# d2
# d1
# base
```

## Explicit `decorated_arg`

If auto-detection cannot find the decorated parameter, set it explicitly.

```python
class SenderDecorator:
    def __init__(self, wrapped: MessageSender):
        self.wrapped = wrapped

    def send(self, message: str) -> None:
        self.wrapped.send(message)


container = Container()
container.register(MessageSender, EmailMessageSender)
container.register_decorator(MessageSender, SenderDecorator, decorated_arg="wrapped")
```

## Function decorators

Decorator callables are supported as well.

```python
def decorate_sender(child: MessageSender):
    class Decorated:
        def send(self, message: str) -> None:
            print("function decorator")
            child.send(message)

    return Decorated()


container = Container()
container.register(MessageSender, EmailMessageSender)
container.register_decorator(MessageSender, decorate_sender, decorated_arg="child")

container.resolve(MessageSender).send("hello")
```
