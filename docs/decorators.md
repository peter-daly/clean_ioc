# Decorators

Decorators add cross-cutting behavior without modifying application components.

```python
from clean_ioc import ContainerBuilder


class MessageSender:
    def send(self, message: str): ...


class EmailMessageSender(MessageSender):
    def send(self, message: str):
        return f"email:{message}"


class LoggingMessageSender(MessageSender):
    def __init__(self, child: MessageSender):
        self.child = child

    def send(self, message: str):
        print("sending")
        return self.child.send(message)


builder = ContainerBuilder()
builder.register(MessageSender, EmailMessageSender)
builder.register_decorator(MessageSender, LoggingMessageSender)
container = builder.build()
```

The decorated argument is inferred from its service annotation. Set `decorated_arg="child"` when inference is ambiguous.

## Ordering

Lower positions are applied first, nearest the core component:

```python
builder.register_decorator(Service, LoggingDecorator, position=0)
builder.register_decorator(Service, MetricsDecorator, position=10)
```

Resolution produces `MetricsDecorator(LoggingDecorator(core))`.

## Static selection

Use a component predicate with `when=`:

```python
import clean_ioc.component_filters as cf

builder.register_decorator(
    MessageSender,
    RetryDecorator,
    when=cf.has_tag("network", "remote"),
)
```

Decorator predicates can inspect generic mappings, parents, and dependency descendants. Every predicate sees the completed undecorated core subtree; dependencies introduced by decorators are excluded from that decision.

## Compiled decorator dependencies

Dependencies other than the decorated argument compile like ordinary component edges. The decorator inherits the core component's lifespan and participates in the same cleanup owner.

Decorators may be classes or typed callables. Async decorator activation is supported through `resolve_async()`.
