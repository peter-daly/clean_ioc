# Dependency Context

You can inject a special type into your dependants that allows you to inspect the current dependency tree. For instances you can check the parent of the current class you are constructing
One example of where this becomes useful is if injecting a logger, you can get information about the loggers parent to add extra context

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

***Note*** *If using dependency context on your dependency you should use a lifespan of **transient**, because any other lifespan will create only use the parent of the first resolved instance*



```