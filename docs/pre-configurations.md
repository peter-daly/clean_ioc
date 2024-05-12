# Pre-configurations

Pre-configurations allow the container or scope to execute a side effect function the first time an instance is resolved.

An example where this might be usefule is if you want to inject loggers as a dependency into you components, the first time a logger is resoled then the pre-configuration can configure the logger.

Pre-configuration functions can also have dependencies from the container.


```python
import logging

class Client:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def do_a_thing(self):
        self.logger.info('Doing a thing')

def logger_fac(context: DependencyContext):
    module = context.parent.implementation.__module__
    return logging.getLogger(module)

def configure_logging():
    logging.basicConfig()


container = Container()
container.register(Client)
container.register(logging.Logger, factory=logger_fac, lifespan=Lifespan.transient)
container.pre_configure(logging.Logger, configure_logging)

client = container.resolve(Client)

```