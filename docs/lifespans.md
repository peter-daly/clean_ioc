# Lifespans

Lifespan controls instance reuse.

```python
from clean_ioc import Container, Lifespan
```

## `transient`

Always create a new instance.

```python
class A:
    pass


container = Container()
container.register(A, lifespan=Lifespan.transient)

a1 = container.resolve(A)
a2 = container.resolve(A)
print(a1 is a2)  # False
```

## `once_per_graph` (default)

Reuse within one resolve graph, but not across separate resolve calls.

```python
class A:
    pass


class B:
    def __init__(self, a: A):
        self.a = a


class C:
    def __init__(self, a: A):
        self.a = a


class D:
    def __init__(self, b: B, c: C):
        self.b = b
        self.c = c


container = Container()
container.register(A, lifespan=Lifespan.once_per_graph)
container.register(B)
container.register(C)
container.register(D)

first = container.resolve(D)
second = container.resolve(D)

print(first.b.a is first.c.a)   # True (same graph)
print(first.b.a is second.b.a)  # False (different graph)
```

## `scoped`

Reuse within the current scope.

```python
class A:
    pass


container = Container()
container.register(A, lifespan=Lifespan.scoped)

with container.new_scope() as s1:
    a1 = s1.resolve(A)
    a2 = s1.resolve(A)
    print(a1 is a2)  # True

with container.new_scope() as s2:
    a3 = s2.resolve(A)
    print(a1 is a3)  # False
```

## `singleton`

Reuse for the container/root-scope lifetime.

```python
class A:
    pass


container = Container()
container.register(A, lifespan=Lifespan.singleton)

a1 = container.resolve(A)
with container.new_scope() as scope:
    a2 = scope.resolve(A)

print(a1 is a2)  # True
```
