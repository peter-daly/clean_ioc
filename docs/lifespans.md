# Lifespans

```python
from clean_ioc import ContainerBuilder, Lifespan
```

## `transient`

A new value is activated for every dependency edge:

```python
builder = ContainerBuilder()
builder.register(A, lifespan=Lifespan.transient)
container = builder.build()

assert container.resolve(A) is not container.resolve(A)
```

## `once_per_graph`

The default lifespan reuses a component within one top-level resolve and discards it afterward:

```python
class Pair:
    def __init__(self, first: A, second: A):
        self.first = first
        self.second = second


builder = ContainerBuilder()
builder.register(A)
builder.register(Pair)
container = builder.build()

pair = container.resolve(Pair)
assert pair.first is pair.second
assert container.resolve(Pair).first is not pair.first
```

## `scoped`

A scoped component is cached by a runtime scope:

```python
builder = ContainerBuilder()
builder.register(A, lifespan=Lifespan.scoped)
container = builder.build()

with container.new_scope() as scope:
    assert scope.resolve(A) is scope.resolve(A)
```

Nested scopes inherit already-created parent scoped values.

## `singleton`

A root singleton belongs to the immutable container and is shared by every child scope:

```python
builder = ContainerBuilder()
builder.register(A, lifespan=Lifespan.singleton)
container = builder.build()

assert container.resolve(A) is container.new_scope().resolve(A)
```

A singleton registered on `ScopeBuilder` instead belongs to the built overlay scope and its descendants.

## Captive dependencies

`build()` rejects a singleton plan that retains a scoped component. This check happens before user activation and applies to decorator and factory dependencies as well as constructors.

## Cleanup ownership

Scoped and singleton values may own generator/context-manager finalizers or teardown callbacks. Cleanup follows the cache owner:

- scoped value → scope exit;
- root singleton → container exit;
- overlay singleton → built `ScopeBuilder` scope exit.
