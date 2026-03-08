# Inversion of Control (IoC)

Inversion of Control means object creation/wiring is delegated to a coordinator (a container) instead of being hardcoded inside business classes.

## Without IoC

```python
class UserService:
    def __init__(self):
        self.repo = SqlUserRepository()  # hardcoded dependency
```

## With IoC

```python
from clean_ioc import Container


class UserService:
    def __init__(self, repo: "UserRepository"):
        self.repo = repo


class UserRepository:
    pass


class SqlUserRepository(UserRepository):
    pass


container = Container()
container.register(UserRepository, SqlUserRepository)
container.register(UserService)

service = container.resolve(UserService)
```

## Why this matters in Clean IoC

- Dependencies are explicit in type hints.
- Wiring logic lives in container setup, not business classes.
- Swapping implementations is a registration change, not a code rewrite.
