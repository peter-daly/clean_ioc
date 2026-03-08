# Special Dependency Types

Clean IoC supports special injected types for advanced graph-aware scenarios.

```python
import logging

from clean_ioc import Container, CurrentGraph, DependencyContext, Lifespan
from clean_ioc.factories import use_from_current_graph
```

## `DependencyContext`

Use `DependencyContext` to inspect the current parent/dependency information.

```python
class Client:
    def __init__(self, logger: logging.Logger):
        self.logger = logger


def logger_factory(context: DependencyContext) -> logging.Logger:
    module_name = context.parent.implementation.__module__
    return logging.getLogger(module_name)


container = Container()
container.register(Client)
container.register(logging.Logger, factory=logger_factory, lifespan=Lifespan.transient)

container.resolve(Client)
```

Use `transient` for dependencies that rely on `DependencyContext`/graph-specific state.

## `CurrentGraph`

`CurrentGraph` resolves from the current active graph.

```python
class Sender:
    pass


class BatchSender:
    pass


class MySender(Sender, BatchSender):
    pass


class Client:
    def __init__(self, sender: Sender, batch_sender: BatchSender):
        self.sender = sender
        self.batch_sender = batch_sender


container = Container()
container.register(Sender, MySender)
container.register(BatchSender, factory=use_from_current_graph(MySender))
container.register(Client)

client = container.resolve(Client)
print(client.sender is client.batch_sender)  # True
```
