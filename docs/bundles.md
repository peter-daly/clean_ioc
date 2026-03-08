# Bundles

Bundles group related registrations.

A bundle is any callable with signature `Callable[[Container], None]`.

```python
from dataclasses import dataclass

from clean_ioc import Container
from clean_ioc.bundles import OnlyRunOncePerClassBundle
```

## Function bundle

```python
class ClientDependency:
    def get_int(self) -> int:
        return 10


class Client:
    def __init__(self, dep: ClientDependency):
        self.dep = dep

    def get_number(self) -> int:
        return self.dep.get_int()


def client_bundle(c: Container):
    c.register(ClientDependency)
    c.register(Client)


container = Container()
container.apply_bundle(client_bundle)

client = container.resolve(Client)
print(client.get_number())
```

## Class-based bundle

```python
@dataclass
class ClientConfig:
    base_url: str


class ApiClient:
    def __init__(self, config: ClientConfig):
        self.base_url = config.base_url


class ApiBundle(OnlyRunOncePerClassBundle):
    def __init__(self, config: ClientConfig):
        self.config = config

    def apply(self, c: Container):
        c.register(ClientConfig, instance=self.config)
        c.register(ApiClient)


container = Container()
cfg = ClientConfig(base_url="https://example.com")

container.apply_bundle(ApiBundle(cfg))
container.apply_bundle(ApiBundle(cfg))  # ignored by OnlyRunOncePerClassBundle

client = container.resolve(ApiClient)
print(client.base_url)
```
