# Generics

Clean IoC discovers concrete implementations of an open generic service and compiles each closed occurrence.

```python
from typing import Generic, TypeVar

from clean_ioc import ContainerBuilder


TCommand = TypeVar("TCommand")


class CommandHandler(Generic[TCommand]):
    pass


class CreateOrder:
    pass


class CreateOrderHandler(CommandHandler[CreateOrder]):
    pass


builder = ContainerBuilder()
builder.register_generic_subclasses(CommandHandler)
container = builder.build()

handler = container.resolve(CommandHandler[CreateOrder])
```

Discovery happens during composition. Open generic registrations act as reusable activation templates; only closed occurrences are runtime roots.

## Filtering discovered subclasses

`subclass_type_filter` uses predicates from `clean_ioc.type_filters`:

```python
import clean_ioc.type_filters as tf

builder.register_generic_subclasses(
    CommandHandler,
    subclass_type_filter=~tf.name_end_with("Decorator"),
)
```

Type filters remain separate from component filters because they answer a discovery question about Python classes, not a selection question about compiled occurrences.

## Fallback implementation

```python
builder.register_generic_subclasses(
    Serializer,
    fallback_type=JsonSerializer,
)
```

When no exact closed implementation exists, the compiler specializes the open fallback edge for the requested occurrence.

## Generic decorators

```python
TCommand = TypeVar("TCommand")


class LoggingHandlerDecorator(CommandHandler[TCommand], Generic[TCommand]):
    def __init__(self, child: CommandHandler[TCommand]):
        self.child = child


builder.register_generic_decorator(CommandHandler, LoggingHandlerDecorator)
```

Concrete decorator classes are memoized process-wide, avoiding repeated dynamic class creation across container builds.

## Occurrence-specific context

The same registered component may appear under different closed generic parents. Clean IoC creates a distinct `Component.occurrence_id` for each use, so parent filters and value providers see the correct generic mapping:

```python
def provider(default, context):
    command_type = context.parent.generic_mapping[TCommand]
    return command_type.__name__
```

Runtime caching still uses the stable component ID, preserving lifespan semantics across occurrences within one resolve.
