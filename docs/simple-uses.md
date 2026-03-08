# Simple Uses

This page shows the most common registration and resolution patterns.

```python
from clean_ioc import Container
```

## 1. Register implementation

```python
from typing import Protocol


class UserRepository(Protocol):
    def get_user(self, user_id: str) -> dict:
        ...


class InMemoryUserRepository(UserRepository):
    def get_user(self, user_id: str) -> dict:
        return {"id": user_id, "name": "InMemory"}


container = Container()
container.register(UserRepository, InMemoryUserRepository)

repo = container.resolve(UserRepository)
print(type(repo).__name__)  # InMemoryUserRepository
```

## 2. Register concrete class

```python
class RandomNumberProvider:
    def get(self) -> int:
        return 10


class Client:
    def __init__(self, provider: RandomNumberProvider):
        self.provider = provider

    def number(self) -> int:
        return self.provider.get()


container = Container()
container.register(RandomNumberProvider)
container.register(Client)

client = container.resolve(Client)
print(client.number())  # 10
```

## 3. Register factory

```python
class AppConfig:
    def __init__(self, env: str):
        self.env = env


def create_config() -> AppConfig:
    return AppConfig(env="prod")


container = Container()
container.register(AppConfig, factory=create_config)

config = container.resolve(AppConfig)
print(config.env)  # prod
```

## 4. Register instance

```python
settings = {"region": "us-east-1"}

container = Container()
container.register(dict, instance=settings)

resolved = container.resolve(dict)
print(resolved is settings)  # True
```

## Collection resolving

When multiple registrations exist for the same service type, resolve `list[T]`, `tuple[T]`, or `set[T]`.

```python
container = Container()
container.register(int, instance=1)
container.register(int, instance=2)
container.register(int, instance=3)

numbers = container.resolve(list[int])
print(numbers)  # [3, 2, 1]
```

## Async resolving

Use `resolve_async` when your graph includes async factories/generators.

```python
import asyncio

from clean_ioc import Container


class TokenClient:
    def __init__(self, token: str):
        self.token = token


async def token_factory() -> str:
    return "secret-token"


async def main():
    container = Container()
    container.register(str, factory=token_factory)
    container.register(TokenClient)

    client = await container.resolve_async(TokenClient)
    print(client.token)


asyncio.run(main())
```
