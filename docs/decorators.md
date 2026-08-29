# Decorators

Decorators add cross-cutting behavior without modifying application components.

```python
from clean_ioc import ContainerBuilder, Tag


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
logging_id = builder.register_decorator(MessageSender, LoggingMessageSender)
container = builder.build()
```

The returned ID identifies the decorator definition across every compiled occurrence. The decorated argument is inferred from its service annotation. Missing, ambiguous, and invalid explicit arguments are reported during `build()`; set `decorated_arg="child"` to select one explicitly. Typed callable return annotations are also checked against the decorated service when compatibility can be determined.

## Ordering

Treat `position` as a decorator z-index: higher values are further outside and lower values are closer to the core component.

```python
TRANSACTION_POSITION = 100
RESILIENCE_POSITION = 500
OBSERVABILITY_POSITION = 1000

builder.register_decorator(Service, TransactionDecorator, position=TRANSACTION_POSITION)
builder.register_decorator(Service, RetryDecorator, position=RESILIENCE_POSITION)
builder.register_decorator(Service, MetricsDecorator, position=OBSERVABILITY_POSITION)
```

Resolution produces `MetricsDecorator(RetryDecorator(TransactionDecorator(core)))`. Equal positions retain registration order from outside to inside. Named constants let independently authored bundles agree on broad layers while still choosing local values within a layer.

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

`when=` is the only V2 decorator-selection predicate. V1's `registration_filter` and `decorator_node_filter` parameters should be combined into it during migration.

## IDs, metadata, and builder customization

Decorators may have their own names and tags for inspection and reusable bundle conventions:

```python
metrics_id = builder.register_decorator(
    Service,
    MetricsDecorator,
    name="service-metrics",
    tags=[Tag("concern", "observability")],
    position=OBSERVABILITY_POSITION,
)

builder.patch_decorator(Service, metrics_id, position=1100)
```

Use `remove_decorator(Service, metrics_id)` before build to suppress a definition. A `ScopeBuilder` may patch or remove an inherited decorator for plans it owns. Existing parent-owned singletons remain anchored to their root activation plan and are not rewired.

## Compiled decorator dependencies

Dependencies other than the decorated argument compile like ordinary component edges. The decorator inherits the core component's lifespan and participates in the same cleanup owner.

Decorators may be classes or typed callables. Async decorator activation is supported through `resolve_async()`.

## Open-generic policies

Register an open service type once:

```python
from typing import Generic, TypeVar


TCommand = TypeVar("TCommand")


class LoggingHandlerDecorator(Generic[TCommand]):
    def __init__(self, child: CommandHandler[TCommand]):
        self.child = child


builder.register_decorator(CommandHandler, LoggingHandlerDecorator)
```

The compiler specializes this definition for every closed `CommandHandler[T]` plan it encounters. This includes handlers supplied by subclass discovery, explicit closed registrations, open or closed factories, and fallback registrations. Generic callable decorators are supported by the same `register_decorator()` API.

Graph text lists decorators outside-to-inside and includes their positions. Component inspection and semantic manifests also expose decorator position, name, tags, dependencies, async requirements, and cleanup ownership.
