# Lifespans

Lifespan controls instance reuse.

Clean IoC coordinates first-time `scoped` and `singleton` construction across concurrent
threads and async tasks. Callers resolving the same uncached registration wait for one
builder and receive the same cached instance. A failed build wakes all waiters and leaves
the registration retryable.

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

### Captive dependencies

A singleton must not depend directly or indirectly on a non-instance `scoped` service.
Doing so would retain request- or job-owned state for the lifetime of the application.
Clean IoC detects this during `validate()` and runtime resolution:

```text
Singleton AppService cannot depend on scoped UnitOfWork.
Path: AppService -> Repository -> UnitOfWork
```

Move the owning service to `scoped`, lengthen the dependency's ownership only when that is
semantically correct, or inject a boundary that creates a scope for each operation. Do not
silence the error by changing lifespans without checking resource ownership.
