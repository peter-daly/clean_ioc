# Inversion of control

Inversion of control separates object construction from object behavior. Application classes declare their dependencies;
an external composition root selects implementations and controls their ownership.

## Direct construction

```python
class UserService:
    def __init__(self):
        self.repository = SqlUserRepository()
```

`UserService` selects and constructs its own repository. Changing the repository or its lifespan requires changing the
service.

## Container-managed composition

```python
from clean_ioc import ContainerBuilder


class UserService:
    def __init__(self, repository: "UserRepository"):
        self.repository = repository


class UserRepository:
    pass


class SqlUserRepository(UserRepository):
    pass


builder = ContainerBuilder()
builder.register(UserRepository, SqlUserRepository)
builder.register(UserService)
container = builder.build()

service = container.resolve(UserService)
```

The application class defines the dependency contract. The builder defines the implementation mapping, and the compiled
container performs activation.

## Clean IoC boundary

Clean IoC applies inversion of control to construction, selection, lifespan caching, and cleanup. It does not control
application behavior after activation. Container access normally remains in the composition root or framework boundary;
application classes receive their collaborators through constructors.
