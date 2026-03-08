# Value Factories

Value factories let you override dependency values without resolving from the registry.

```python
from clean_ioc import Container, DependencySettings
from clean_ioc.registration_filters import with_name
import clean_ioc.value_factories as vf
```

## Set a static value

```python
class Client:
    def __init__(self, number: int):
        self.number = number


container = Container()
container.register(
    Client,
    dependency_config={"number": DependencySettings(value_factory=vf.set_value(50))},
)

client = container.resolve(Client)
print(client.number)  # 50
```

## Default values vs registry values

```python
class Client:
    def __init__(self, number: int = 10):
        self.number = number


container = Container()
container.register(int, instance=1, name="one")
container.register(int, instance=2)

container.register(
    Client,
    name="uses_default",
    dependency_config={"number": DependencySettings(value_factory=vf.use_default_value)},
)

container.register(
    Client,
    name="ignore_default",
    dependency_config={"number": DependencySettings(value_factory=vf.dont_use_default_value)},
)

container.register(
    Client,
    name="ignore_default_filtered",
    dependency_config={
        "number": DependencySettings(
            value_factory=vf.dont_use_default_value,
            filter=with_name("one"),
        )
    },
)

print(container.resolve(Client, filter=with_name("uses_default")).number)          # 10
print(container.resolve(Client, filter=with_name("ignore_default")).number)        # 2
print(container.resolve(Client, filter=with_name("ignore_default_filtered")).number)  # 1
```
