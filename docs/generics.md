# Generics

Clean IoC supports open-generic registration patterns such as `Handler[T]`, `Repository[T]`, and `Validator[T]`.

```python
from typing import Generic, TypeVar

from clean_ioc import Container
```

## How generic registration works

When you call `register_generic_subclasses(...)`, Clean IoC:

1. discovers non-abstract subclasses of your open generic service type
2. maps each subclass to its concrete closed generic base
3. registers each mapped pair as normal registrations

At resolve time, a closed generic request like `Handler[UserCreated]` first uses exact mapped registrations. If there is no exact match, Clean IoC can use an optional fallback open-generic registration.

Important: subclass modules must be imported before `register_generic_subclasses(...)` runs. If a subclass is never imported, it cannot be discovered.

## Register generic subclasses

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

`register_generic_subclasses(...)` accepts the same useful options as `register(...)`, including `lifespan`, `name`, `tags`, and `parent_node_filter`.

## Fallback type

Use `fallback_type` when you want unmatched generic arguments to still resolve.

```python
class DefaultCommandHandler(CommandHandler[T]):
    def handle(self, command: T) -> str:
        return "DEFAULT"


container = Container()
container.register_generic_subclasses(
    CommandHandler,
    fallback_type=DefaultCommandHandler,
)

# No specific subclass for UnknownCommand, so fallback is used
handler = container.resolve(CommandHandler[Command])
```

Fallback behavior details:

- Exact closed registrations win over fallback.
- Fallback is used only for generic argument combinations that have no specific mapped subclass.
- If no mapped subclass and no fallback exist, resolve raises `CannotResolveError`.

## Filter which subclasses are included

You can narrow discovery with `subclass_type_filter`.

```python
import clean_ioc.type_filters as tf


container = Container()
container.register_generic_subclasses(
    CommandHandler,
    subclass_type_filter=~tf.name_end_with("Experimental"),
)
```

This is useful when scanning large modules where some subclasses should not be container-registered.

## Generic decorators

Use `register_generic_decorator(...)` to decorate all discovered mapped closed generic services.

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

Decorator behavior details:

- Open-generic decorators are concretized per mapped closed service.
- Non-generic decorators are applied as-is for each mapped closed service.
- Use `decorated_arg` when the wrapped dependency parameter cannot be inferred automatically.
- Use `registration_filter`, `decorated_node_filter`, and `position` to control where and in what order decorators apply.

Note: `register_generic_decorator(...)` decorates discovered mapped closed services. If a resolve path uses only fallback for an unmatched generic combination, that unmatched fallback combination is not part of subclass mapping.

## Multi-parameter generic services

Generics with multiple type parameters are supported.

```python
TQuery = TypeVar("TQuery")
TResult = TypeVar("TResult")


class QueryHandler(Generic[TQuery, TResult]):
    def handle(self, query: TQuery) -> TResult:
        raise NotImplementedError


class GetCount:
    pass


class GetCountHandler(QueryHandler[GetCount, int]):
    def handle(self, query: GetCount) -> int:
        return 42


container = Container()
container.register_generic_subclasses(QueryHandler)

handler = container.resolve(QueryHandler[GetCount, int])
print(handler.handle(GetCount()))
```

## Protocol-based generic services

You can use generic `Protocol` service types too.

```python
from typing import Protocol

T = TypeVar("T", covariant=True)


class Serializer(Protocol[T]):
    def serialize(self, value: T) -> str:
        ...


class IntSerializer(Serializer[int]):
    def serialize(self, value: int) -> str:
        return str(value)


container = Container()
container.register_generic_subclasses(Serializer)

serializer = container.resolve(Serializer[int])
print(serializer.serialize(123))
```

## Common pitfalls

- subclasses not imported before registration
- base type is not actually open generic
- expecting fallback without setting `fallback_type`
- expecting generic decorators to apply to unmatched fallback-only combinations
