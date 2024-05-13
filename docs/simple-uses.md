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


## Subclasses registration

This feature allows registration of all subclasses of a giveb type

```python
class Client(abc.ABC):
    @abc.abstractmethod
    def get_number(self):
        pass


class TenClient(Client):
    def get_number(self):
        return 10

class TwentyClient(Client):
    def get_number(self):
        return 20

container = Container()

container.register_subclasses(Client)

ten_client = container.resolve(TenClient)
ten_client.get_number() # returns 10

twenty_client = container.resolve(TwentyClient)
twenty_client.get_number() # returns 20

# Resolve all subsclasses of Client
client = container.resolve(list[Client]) ## [TwentyClient(), TenClient()]
```



## Collection resolving

If you have multiple dependencues you can simply define a dependency as a list[T] and you can return all of the instances.

```python

class ClientDependency:
    def __init__(self, numbers: list[int]):
        self.numbers = numbers

    def get_numbers(self):
        return self.numbers

class Client:
    def __init__(self, dep: ClientDependency):
        self.dep = dep

    def get_numbers(self):
        return self.dep.get_numbers()

container = Container()
container.register(ClientDependency)
container.register(Client)
container.register(int, instance=1)
container.register(int, instance=2)
container.register(int, instance=3)

client = container.resolve(Client)

client.get_numbers() # returns [3, 2, 1]
```

