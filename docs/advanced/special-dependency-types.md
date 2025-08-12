# Special Dependency Types

Clean_ioc allows you to inject special dependencies into your objects that give you access to the current dependency graph being resolved. This is a powerful feature that enables you to create objects based on the parent dependency or search the current resolved objects. When using these feature it is strongly advised to make sure you do not hold reference to any of these objects after the resolving has completed, this basically means if tou use the objects in a constructor or factory make sure they aren't stored in the returned object.

## Dependency Context

The `DependencyContext` type allows you to access the the parent type of the caller via the dependency graph.
One example of where this becomes useful is when injecting something like a logger, you can get information about the loggers parent to add extra context

```python
class Client:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def do_a_thing(self):
        self.logger.info('Doing a thing')

def logger_fac(context: DependencyContext):
    module = context.parent.implementation.__module__
    return logging.getLogger(module)


container = Container()
container.register(Client)
container.register(logging.Logger, factory=logger_fac, lifespan=Lifespan.transient)
client = container.resolve(Client)
```

!!! Danger "Using DependencyContext"
    If using `DependencyContext` on your dependency you should use a lifespan of **transient**, because any other lifespan will create only use the parent of the first resolved instance. Also when using the dependency context make sure don't add it the objects state, discard if it within the factory or constructor.

## Current Graph

The `CurrentGraph` object allows you resolve from the current dependency graph being constructed. This is useful if you want to make sure that two different registered objects can be forced to be the same object, this is handy when doing interface segregation. You can use the inbuilt `use_from_current_graph` or `use_from_current_graph_async` factories to do this. These functions are defined in `clean_ioc.factories`

```python
class Sender(Protocol):
    def send(self, message): ...


class BatchSender(Protocol):
    def send_batch(self, messages): ...

class MySender(Sender, BatchSender):
    def send_batch(self, messages):
        # SEND MANY THINGS
        pass

    def send(self, message):
        # SEND SOMETHING
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

client.sender is client.batch_sender # True
```

!!! Info "Order does not matter"
    In the above scenario the order of resolving Sender and BatchSender does not matter. It will work the same regardless of which one is resolved first

!!! Danger "Using CurrentGraph"
    If using `CurrentGraph` on your dependency you should use a lifespan of **transient**, because any other lifespan will create only use the parent of the first resolved instance. Also when using the `CurrentGraph` make sure don't add it the objects state, only use within the factory or constructor of your object.
