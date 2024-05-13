

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
