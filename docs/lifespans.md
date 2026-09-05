# Lifespans

```python
from clean_ioc import ContainerBuilder
```

The `lifespan=` argument takes the string literals `"transient"`, `"once_per_graph"`, `"scoped"`, or `"singleton"`. The exported `Lifespan` name is a typing alias for annotating reusable composition helpers, not an enum.

## `transient`

A new value is activated for every dependency edge:

```python
builder = ContainerBuilder()
builder.register(A, lifespan="transient")
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
builder.register(A, lifespan="scoped")
container = builder.build()

with container.new_scope() as scope:
    assert scope.resolve(A) is scope.resolve(A)
```

Nested scopes inherit already-created parent scoped values.

## `singleton`

A root singleton belongs to the immutable container and is shared by every child scope:

```python
builder = ContainerBuilder()
builder.register(A, lifespan="singleton")
container = builder.build()

assert container.resolve(A) is container.new_scope().resolve(A)
```

A singleton registered on `ScopeBuilder` instead belongs to the built overlay scope and its descendants.

## Captive dependencies

`once_per_graph` is resolution-local state. A scoped or singleton component cannot retain it because the cached owner would carry that instance into later top-level resolves. `build()` rejects both direct and transitive captures:

```text
singleton -> once_per_graph                invalid
singleton -> transient -> once_per_graph   invalid
scoped -> once_per_graph                   invalid
scoped -> transient -> once_per_graph      invalid
```

A plain transient dependency remains valid beneath a scoped or singleton owner. A transient does not, however, hide an invalid lifespan deeper in its dependency tree.

The compiler also rejects a singleton plan that retains a scoped component. Shorter-lived components may depend on longer-lived components, so `once_per_graph -> scoped` and `once_per_graph -> singleton` are valid.

These checks happen before user activation and cover constructors, factories, decorators, collections, component edges
selected by argument policies, pre-configuration dependencies, and supplied scope slots. A singleton therefore cannot
capture a late-bound request value declared with `declare_scope_slot()`. Captive paths are reported with the
`captive-runtime-scope` issue code; ordinary lifespan violations retain `captive-dependency`.

`ResolutionContext` is effective `once_per_graph` state. Scoped and singleton components cannot capture it, directly
or through a transient, decorator, collection, argument policy, or pre-configuration; those failures use
`captive-resolution-context`. `Scope` is effective scoped state and cannot be captured by a singleton. A retained
resolution context also stops accepting calls when its top-level resolution finishes.

## Cleanup ownership

Ownership is compiled for every occurrence and is available from `container.graph.ownership_report()`. Generator and
context-manager cleanup follows that frozen decision:

- scoped value → scope exit;
- root singleton → container exit;
- overlay singleton → built `ScopeBuilder` scope exit.
- cleanup-bearing transient beneath a singleton → that singleton's declaring owner;
- other cleanup-bearing transient or once-per-graph value → resolving scope exit.

Closing attempts every finalizer in reverse acquisition order. If several fail, cleanup continues and the failures are
raised as an `ExceptionGroup` in finalization order. Closed scopes reject resolution, provision, and child-scope
creation with `ScopeClosedError`.
