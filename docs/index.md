# Clean IoC
A simple unintrusive dependency injection library for python that requires nothing of your application code (except that you use typing).

## What is Clean IoC?

Clean IoC is a dependency injection library written in python that enables dependency injection in your python applications. Clean IoC is ***unintrusive***, meaning that it avoids you needing any of the following to make your code work with it.
 - Weird global state
 - Any base clases
 - Any framework decorators

The avoidance of of any IoC concerns from you application code allows your code to remain ***clean***.


Since Clean IoC keeps your code clean from the library itself, to use it you can simply just create a container and register your dependencies.

```python

class UserRepository(Protocol):
    def add(self, user):
        ...

class InMemoryUserRepository(UserRepository):

    def __init__(self):
        self.users = []

    def add(self, user):
        # This is obviously terrible, but it's for demo purposes
        self.users.append(user)

class SqlAlchemyUserRepository(UserRepository):

    def __init__(self):
        # Do some db stuff here
        pass

    def add(self, user):
        # Do some db stuff here
        pass

container = Container()
container.register(UserRepository, InMemoryUserRepository)


repository = container.resolve(UserRepository) # This will return an InMemoryUserRepository

```

You can see more basic registration [here](./simple-uses.md).