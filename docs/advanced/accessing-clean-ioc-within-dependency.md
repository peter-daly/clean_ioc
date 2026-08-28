# Accessing Clean IoC inside a dependency

Prefer explicit constructor dependencies. When a component truly makes a runtime selection, inject `ResolutionContext`:

```python
import clean_ioc.component_filters as cf
from clean_ioc import ResolutionContext


class ClientSelector:
    def __init__(self, context: ResolutionContext):
        self.context = context

    def get(self, name: str) -> Client:
        return self.context.resolve(Client, filter=cf.with_name(name))
```

The selected plans were compiled during `build()`. This API does not bring back runtime graph discovery.

## Creating a nested scope

Framework infrastructure may inject `Scope` to create a nested cache boundary:

```python
from clean_ioc import Scope


class BatchRunner:
    def __init__(self, scope: Scope):
        self.scope = scope

    def run(self):
        with self.scope.new_scope() as batch_scope:
            return batch_scope.resolve(BatchHandler).run()
```

## What is intentionally unavailable

Runtime dependencies cannot register components, patch components, apply bundles, or create a `ScopeBuilder`. Composition belongs at an explicit application boundary, not inside activation.
