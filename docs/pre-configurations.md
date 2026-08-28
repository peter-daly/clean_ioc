# Pre-configurations

A pre-configuration runs once before an applicable component's first activation. Its own dependencies are compiled during `build()`; the configuration function itself remains runtime-only.

```python
import logging

from clean_ioc import ContainerBuilder, Lifespan


def configure_logging(logger: logging.Logger):
    logger.setLevel(logging.INFO)


builder = ContainerBuilder()
builder.register(logging.Logger, factory=logging.getLogger, lifespan=Lifespan.singleton)
builder.register(Client)
builder.pre_configure(Client, configure_logging)
container = builder.build()
```

Use `dependency_config` for argument-level selection or values. Use `when=` with a component filter to select static occurrences:

```python
import clean_ioc.component_filters as cf

builder.pre_configure(
    Client,
    configure_client,
    when=cf.has_tag("environment", "production"),
)
```

`continue_on_failure=True` logs a failed pre-configuration and allows activation to continue. The default propagates the failure.
