# Lifespans

Lifespans configure how long and resolved object says alive for
There are 4 lifespan types

## transient

Always create a new instance when a registration is matched.

```python
container.register(Client, lifespan=Lifespan.transient)
```

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

container.register(A, lifespan=Lifespan.transient)
container.register(B)
container.register(C)
container.register(D)

d = container.resolve(D)

d.b.a == d.c.a # FALSE

```

## once_per_graph (Default behaviour)

Only create a new instance once during a resolve call.

```python
container.register(Client, lifespan=Lifespan.once_per_graph)
```

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

container.register(A, lifespan=Lifespan.once_per_graph)
container.register(B)
container.register(C)
container.register(D)

d = container.resolve(D)
a = container.resolve(A)

d.b.a == d.c.a # TRUE
d.b.a == a # FALSE
```

## singleton

Only one instance of the object is created throughout the lifetime of the the container

```python
container.register(Client, lifespan=Lifespan.singleton)
```

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

container.register(A, lifespan=Lifespan.singleton)
container.register(B)
container.register(C)
container.register(D)

d = container.resolve(D)
a = container.resolve(A)

d.b.a == d.c.a # TRUE
d.b.a == a # TRUE
```

## scoped

Only create a new instance throughout the lifetime a [scope](./scopes.md). When an object is resolved outside of a scope then the behaviour is the same as **singleton**.

```python
container.register(Client, lifespan=Lifespan.scoped)
```

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

container.register(A, lifespan=Lifespan.scoped)
container.register(B)
container.register(C)
container.register(D)

with container.new_scope() as scope:
    d = container.resolve(D)
    a = container.resolve(A)
    d.b.a == d.c.a # TRUE
    d.b.a == a # TRUE
```
