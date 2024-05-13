# Clean IoC
A simple dependency injection library for python that requires nothing of your application code (except that you use typing).


Read the [docs](https://peter-daly.github.io/clean_ioc/) to find out more.


## Basic Registering and resolving

There are 4 basic modes of registering a new set of classes

### Implementation

```python

class UserRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, user):
        pass

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

### Concrete Class

```python

class ClientDependency:
    def get_int(self):
        return 10

class Client:
    def __init__(self, dep: ClientDependency):
        self.dep = dep

    def get_number(self):
        return self.dep.get_int()


container = Container()
container.register(ClientDependency)
container.register(Client)

client = container.resolve(Client)

client.get_number() # returns 10

```

### Factory

```python

class ClientDependency:
    def get_int(self):
        return 10

class Client:
    def __init__(self, dep: ClientDependency):
        self.dep = dep

    def get_number(self):
        return self.dep.get_int()

def client_factory(dep: ClientDependency):
    return Client(dep=dep)


container = Container()
container.register(ClientDependency)
container.register(Client, factory=client_factory)

client = container.resolve(Client)

client.get_number() # returns 10

```


### Instance

```python

class ClientDependency:
    def __init__(self, num):
        self.num = num

    def get_int(self):
        return self.num

class Client:
    def __init__(self, dep: ClientDependency):
        self.dep = dep

    def get_number(self):
        return self.dep.get_int()

client_dependency = ClientDependency(num=10)

container = Container()
container.register(ClientDependency, instance=client_dependency)
container.register(Client)

client = container.resolve(Client)

client.get_number() # returns 10

```

