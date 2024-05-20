
```python
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
    dependency_config={"number": DependencySettings(value_factory=set_value(50))}
)
container.register(
    Client,
    name="UsesDefaultValue"
)
container.register(
    Client,
    name="IgnoresDefaultParameterValue",
    dependency_config={"number": DependencySettings(value_factory=dont_use_default_parameter)}
)
container.register(
    Client,
    name="UsesRegistrationFilter",
    dependency_config={"number": DependencySettings(value_factory=dont_use_default_parameter, filter=with_name("One"))}
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

## Accessing the Container, Scope and Resolver within dependencies

Accessing container directly

```python
class Client:
    def __init__(self, container: Container):
        self.container = container

    def get_number(self):
        return self.container.resolve(int)

container.register(int, instance=2)

container.register(Client)

client = container.resolve(Client)
client.get_number() # returns 2
```

Accessing Resolver also returns the container

```python

class Client:
    def __init__(self, resolver: Resolver):
        self.resolver = resolver

    def get_number(self):
        return self.resolver.resolve(int)

container.register(int, instance=2)

container.register(Client)

client = container.resolve(Client)
client.get_number() # returns 2
```

When within a scope, Resolver returns the current scope rather than the container

```python
class Client:
    def __init__(self, resolver: Resolver):
        self.resolver = resolver

    def get_number(self):
        return self.resolver.resolve(int)

container.register(int, instance=2)

container.register(Client)

client = container.resolve(Client)
client.get_number() # returns 2

with container.get_scope() as scope:
    scope.register(int, instance=10)
    scoped_client = scope.resolve(Client)
    scoped_client.get_number() # returns 10
```

Scopes can also be used as an async context manager

```python
class Client:
    async def get_number(self):
        return 10

container.register(Client)

async with container.get_scope() as scope:
    scoped_client = scope.resolve(Client)
    await scoped_client.get_number() # returns 10
```


The order of a dependant value is as follows
1. Setting the dependency value_factory to an explicit value
    ```python
    DependencySettings(value_factory=set_value(50))
    ```
    If the falue is a default parameter then the default value factory will use that default parameter value
    ```python
    class Client:
        def __init__(self, number=10):
            self.number = number
    ```
    If you don't want to use the default parameter value you can change the value_factory to pybass it
    ```python
        DependencySettings(value_factory=dont_use_default_parameter)
    ```
2. Going to the container registry to find a registration using the registration filter if, if there is a default value on the dependant paramater you must explicity set.
