# Clean IoC

Clean IoC is a dependency injection container for Python that keeps application code framework-agnostic.

It focuses on:

- constructor/factory injection using type hints
- explicit registration and resolution
- lifecycle control with `transient`, `once_per_graph`, `scoped`, `singleton`
- filtering, decorators, and generic registration helpers

## Install

```bash
pip install clean_ioc
```

FastAPI integration:

```bash
pip install "clean_ioc[fastapi]"
```

## Quick Start

```python
from clean_ioc import Container


class UserRepository:
    def get_user(self, user_id: str) -> dict:
        return {"id": user_id, "name": "Ada"}


class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def get_user(self, user_id: str) -> dict:
        return self.repo.get_user(user_id)


container = Container()
container.register(UserRepository)
container.register(UserService)

service = container.resolve(UserService)
print(service.get_user("123"))
```

## Core Concepts

1. Register dependencies on `Container`/`Scope`.
2. Resolve by type.
3. Let the container recursively resolve child dependencies.
4. Control reuse with lifespans.

## Next Steps

- [Simple Uses](./simple-uses.md)
- [Factories](./factories.md)
- [Lifespans](./lifespans.md)
- [Scopes](./scopes.md)
- [Decorators](./decorators.md)
- [Generics](./generics.md)
