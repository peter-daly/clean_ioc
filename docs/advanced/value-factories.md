# Value factories

Value factories allow you to set a dependency value explicitly without the need to go go to the registry.
This can be useful when setting simple types such as a number of string.

The value factory can be set on the `dependency_config` when con configuring your container.

clean ioc comes with a set of built in value factories

- `use_default_value`: Use the default parameter value if available (Default behaviour)
- `set_value(value: Any)`: Set a constant value
- `dont_use_default_value`: Skip the default parameter

A value factory has the following signature: `Callable[[Any, DependencyContext], Any]`. When needed you can write your own custom one.

If a value factory returns an instance of `clean_ioc._empty` it will then try to resolve the dependency from the registry

## Simple example of setting a static value

```python
import clean_ioc.value_factories as vf


class Client:
    def __init__(self, number):
        self.number = number

    def get_number(self):
        return self.number

container = Container()

container.register(
    Client,
    dependency_config={"number": DependencySettings(value_factory=vf.set_value(50))}
)
client = container.resolve(Client)

client.get_number() # returns 50
```

## Dealing with default parameter values

The default behaviour of of clean_ioc is to use the default parameter value if one exists.
If you do not wish to use it you must use `dont_use_default_parameter`.

Here is an example of different uses of value factories with default parameters

```python
import clean_ioc.value_factories as vf


class Client:
    def __init__(self, number=10):
        self.number = number

    def get_number(self):
        return self.number

container = Container()

container.register(int, instance=1, name="One")
container.register(int, instance=2)

container.register(
    Client,
    name="SetsValue",
    dependency_config={"number": DependencySettings(value_factory=vf.set_value(50))}
)
container.register(
    Client,
    name="UsesDefaultValue"
)
container.register(
    Client,
    name="IgnoresDefaultParameterValue",
    dependency_config={"number": DependencySettings(value_factory=vf.dont_use_default_parameter)}
)
container.register(
    Client,
    name="UsesRegistrationFilter",
    dependency_config={"number": DependencySettings(value_factory=vf.dont_use_default_parameter, filter=with_name("One"))}
)

client1 = container.resolve(Client, filter=with_name("SetsValue"))
client2 = container.resolve(Client, filter=with_name("UsesDefaultValue"))
client3 = container.resolve(Client, filter=with_name("IgnoresDefaultParameterValue"))
client4 = container.resolve(Client, filter=with_name("UsesRegistrationFilter"))


client1.get_number() # returns 50
client2.get_number() # returns 10
client3.get_number() # returns 2
client4.get_number() # returns 1
```
