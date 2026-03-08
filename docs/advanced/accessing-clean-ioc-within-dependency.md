# Accessing Container, Scope, and Resolver Inside Dependencies

You can inject `Container`, `Scope`, and `Resolver` directly.

```python
from clean_ioc import Container, Resolver, Scope
```

## Accessing `Container`

```python
class Client:
    def __init__(self, container: Container):
        self.container = container

    def get_number(self) -> int:
        return self.container.resolve(int)


container = Container()
container.register(int, instance=2)
container.register(Client)

client = container.resolve(Client)
print(client.get_number())  # 2
```

## Accessing `Resolver`

```python
class Client:
    def __init__(self, resolver: Resolver):
        self.resolver = resolver

    def get_number(self) -> int:
        return self.resolver.resolve(int)


container = Container()
container.register(int, instance=2)
container.register(Client)

print(container.resolve(Client).get_number())  # 2
```

## `Resolver` inside a scope

When resolved inside a scope, `Resolver` resolves against that scope.

```python
container = Container()
container.register(int, instance=2)
container.register(Client)

with container.new_scope() as scope:
    scope.register(int, instance=10)
    scoped_client = scope.resolve(Client)
    print(scoped_client.get_number())  # 10
```

## Accessing `Scope`

```python
class ScopeAwareClient:
    def __init__(self, scope: Scope):
        self.scope = scope


container = Container()
container.register(ScopeAwareClient)

with container.new_scope() as scope:
    client = scope.resolve(ScopeAwareClient)
    print(client.scope is scope)  # True
```
