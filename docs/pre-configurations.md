# Pre-Configurations

Pre-configurations run setup logic before matching services are built.

```python
import logging

from clean_ioc import Container, DependencyContext, Lifespan
```

## Basic example

```python
class Client:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def do_work(self):
        self.logger.info("doing work")


def logger_factory(context: DependencyContext) -> logging.Logger:
    module = context.parent.implementation.__module__
    return logging.getLogger(module)


def configure_logging():
    logging.basicConfig(level=logging.INFO)


container = Container()
container.register(logging.Logger, factory=logger_factory, lifespan=Lifespan.transient)
container.register(Client)
container.pre_configure(logging.Logger, configure_logging)

client = container.resolve(Client)
client.do_work()
```

## Notes

- Pre-configurations run once per registered pre-configuration object.
- They can receive injected dependencies just like factories/constructors.
- Use `continue_on_failure=True` if setup errors should not stop resolution.

```python
def flaky_setup():
    raise RuntimeError("optional setup failed")


container = Container()
container.register(int, instance=1)
container.pre_configure(int, flaky_setup, continue_on_failure=True)

print(container.resolve(int))  # 1
```
