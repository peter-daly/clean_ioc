# Clean IoC
A simple dependency injection library for python that requires nothing of your application code (except that you use typing).


## Basic Registering and resolving

There are 4 basic modes of registering a new set of classes

### Implementation

```python

class UserRepository(abc.ABC)
    @abc.abstractmethod
    def add(self, user):
        pass

class InMemoryUserRepository(UserRepository)

    def __init__(self):
        self.users = []

    def add(self, user):
        # This is obviously terrible, but it's for demo purposes
        self.users.append(user)

class SqlAlchemyUserRepository(UserRepository)

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

class ClientDependency
    def get_int(self):
        return 10

class Client
    def __init__(self, dep: ClientDependency)
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

class ClientDependency
    def get_int(self):
        return 10

class Client
    def __init__(self, dep: ClientDependency)
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

class ClientDependency
    def __init__(self, num):
        self.num = num

    def get_int(self):
        return self.num

class Client
    def __init__(self, dep: ClientDependency)
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

## List resolving

```python

class ClientDependency
    def __init__(self, numbers: list[int]):
        self.numbers = numbers

    def get_numbers(self):
        return self.numbers

class Client
    def __init__(self, dep: ClientDependency)
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


## Decorators

Follows a object orientated decoration pattern, rather than a decoration annotation.
The main reason for this was to allow decotation of registered instances

```python
class Client
    def __init__(self, number: int)
        self.number = number

    def get_number(self):
        return self.number


class DoubleClientDecorator(Client):
    def __init__(self, client: Client):
        self.client = client
    def get_number(self):
        return self.client.get_number() * 2

container = Container()

container.register(Client)
container.register_decorator(Client, DoubleClientDecorator)
container.register(int, instance=10)

client = container.resolve(Client)

client.get_number() # returns 20
```


Decorators are resolved in order of when first registered. So the first registered decorator is the highest in the class tree


```python
    class Concrete:
        pass

    class DecoratorOne(Concrete):
        def __init__(self, child: Concrete):
            self.child = child

    class DecoratorTwo(Concrete):
        def __init__(self, child: Concrete):
            self.child = child

    container = Container()

    container.register(Concrete)
    container.register_decorator(Concrete, DecoratorOne)
    container.register_decorator(Concrete, DecoratorTwo)

    root = container.resolve(Concrete)

    type(root) # returns DecoratorOne
    type(root.child) # returns DecoratorTwo
    type(root.child.child) # returns Concrete
```


## Subclasses registration

This feature allows registartion of all subclasses of a giveb type

```python
class Client(abc.ABC)
    @abc.abstractmethod
    def get_number(self):
        pass


class TenClient(Client)
    def get_number(self):
        return 10

class TwentyClient(Client)
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


## Lifespans
Lifespans configure how long and resolved object says alive for
There are 4 lifespan types

### transient
Always create a new instance

```python
container.register(Client, lifespan=Lifespan.transient)
```


### once_per_graph (Default behaviour)
Only create one instance throughout the resolve call

```python
container.register(Client, lifespan=Lifespan.once_per_graph)
```

### scoped
Only create a new instance through the life a scope. When not in a scope the behaviour is the same as **once_per_graph**

```python
container.register(Client, lifespan=Lifespan.scoped)
```

### singleton
Only one instance of the object is created throughout the lifespan of the container

```python
container.register(Client, lifespan=Lifespan.singleton)
```

*Note:*
When registering an instance, then the behaviour is always singleton

```python
container.register(int, instance=10)
```

## Open Generics

Registers all generic subclasses of the service type and allows you to resolve with the generic alias

```python
T = TypeVar("T")

class HelloCommand:
    pass

class GoodbyeCommand:
    pass

class CommandHandler(Generic[T]):
    def handle(self, command: T):
        pass

class HelloCommandHandler(CommandHandler[HelloCommand]):
    def handle(self, command: HelloCommand):
        print('HELLO')

class GoodbyeCommandHandler(CommandHandler[GoodbyeCommand]):
    def handle(self, command: GoodbyeCommand):
        print('GOODBYE')

container = Container()
container.register_open_generic(CommandHandler)

h1 = container.resolve(CommandHandler[HelloCommand])
h2 = container.resolve(CommandHandler[GoodbyeCommand])

h1.handle(HelloCommand()) # prints 'HELLO'
h2.handle(GoodbyeCommand()) # prints 'GOODBYE'

```

## Open Generic Decorators


Allows you to add decorators to your open generic registrations

```python
T = TypeVar("T")

class HelloCommand:
    pass

class GoodbyeCommand:
    pass

class CommandHandler(Generic[T]):
    def handle(self, command: T):
        pass

class HelloCommandHandler(CommandHandler[HelloCommand]):
    def handle(self, command: HelloCommand):
        print('HELLO')

class GoodbyeCommandHandler(CommandHandler[GoodbyeCommand]):
    def handle(self, command: GoodbyeCommand):
        print('GOODBYE')

class AVeryBigCommandHandlerDecorator(Generic[T]):
    def __init__(self, handler: CommandHandler[T]):
        self.handler = handler

    def handle(self, command: T):
        print('A VERY BIG')
        self.handler.handle(command=command)

container = Container()
container.register_open_generic(CommandHandler)
container.register_open_generic_decorator(CommandHandler, AVeryBigCommandHandlerDecorator)
h1 = container.resolve(CommandHandler[HelloCommand])
h2 = container.resolve(CommandHandler[GoodbyeCommand])

h1.handle(HelloCommand()) # prints 'A VERY BIG\nHELLO'
h2.handle(GoodbyeCommand()) # prints 'A VERY BIG\nGOODBYE'

```

## Scopes

Scopes are a way to create a sub container that will live for a certain lifespan.
Some good use cases for scope would be for the lifespan of handling a http request with a web server or a message/event if working on a message based system


```python
class Client
    def __init__(self, number: int)
        return number

    def get_number(self):
        return self.resolver.resolve(int)

container.register(int, instance=2)

container.register(Client)

client = container.resolve(Client)
client.get_number() # returns 2

with container.get_scope() as scope:
    scope.register(int, instance=10)
    scoped_client = scope.resolve(Client)
    scoped_client.get_number() # returns 10
```

## Named registartions & Registartion filters

By default the last registration is what the container will return when resolve is called as below.

```python

container = Container()
container.register(int, instance=1)
container.register(int, instance=2)
container.register(int, instance=3)

number = container.resolve(int) # returns 3

```
To be more selective of what we return we can add a name to the registration and apply a registartion filter when we resolve.

A registartion filter is simply function that receives a **Registartion** and returns a **bool**

For example if we wanted to get the int named **"One"** we do the following

```python
container = Container()
container.register(int, instance=1, name="One")
container.register(int, instance=2, name="Two")
container.register(int, instance=3, name="Three")

number = container.resolve(int, filter=lambda r: r.name == "One") # returns 1
```

Clean IOC comes with a set of in built registartion filters that can be found [here](./clean_ioc/registration_filters.py)

We can get the desired behaviour as above
```python
from clean_ioc.registartion_filters import with_name

container = Container()
container.register(int, instance=1, name="One")
container.register(int, instance=2, name="Two")
container.register(int, instance=3, name="Three")

number = container.resolve(int, filter=with_name("One")) # returns 1
```

## Dependency Settings

Dependency settings are defined at registartion and allow you to define the selection or setting dependencies


```python
class Client
    def __init__(self, number=10)
        self.number = number

    def get_number(self):
        return self.number

container = Container()

container.register(int, instance=1, name="One")
container.register(int, instance=2, name="Two")

container.register(
    Client,
    name="SetsValue",
    dependency_config={"number": DependencySettings(value=50)}
)
container.register(
    Client,
    name="UsesDefaultValue"
)
container.register(
    Client,
    name="IgnoresDefaultParameterValue",
    dependency_config={"number": DependencySettings(use_default_paramater=False)}
)
container.register(
    Client,
    name="UsesRegistartionFilter",
    dependency_config={"number": DependencySettings(use_default_paramater=False, filter=with_name("One"))}
)

client1 = container.resolve(Client, filter=with_name("SetsValue"))
client2 = container.resolve(Client, filter=with_name("UsesDefaultValue"))
client3 = container.resolve(Client, filter=with_name("IgnoresDefaultParameterValue"))
client4 = container.resolve(Client, filter=with_name("UsesRegistartionFilter"))


client1.get_number() # returns 50
client2.get_number() # returns 10
client3.get_number() # returns 2
client4.get_number() # returns 1
```

The order of a dependant value is as follows
1. Setting the dependency value explicitly
    ```python
    DependencySettings(value=50)
    ```
2. Using the default parameter value if it exisis the dependency value explicitly
    ```python
    class Client
    def __init__(self, number=10)
        self.number = number
    ```
    If you don't want to use the default parameter value you can set it to false in the dependency setting
    ```python
    DependencySettings(use_default_paramater=False)
    ```
3. Going to the container registry to find a registartion using the registration filter if, if there is a default value on the dependant paramater you must explicity set.

## Accessing the Container, Scope and Resolver within dependencies

Accessing container directly

```python
class Client
    def __init__(self, container: Container)
        self.container = container

    def get_number(self):
        return self.container.resolve(int)

container.register(int, instance=2)

container.register(Client)

client = container.resolve(Client)
client.get_number() # returns 2
```

Accessing Resolver also returns the container

```python

class Client
    def __init__(self, resolver: Resolver)
        self.resolver = resolver

    def get_number(self):
        return self.resolver.resolve(int)

container.register(int, instance=2)

container.register(Client)

client = container.resolve(Client)
client.get_number() # returns 2
```

When within a scope, Resolver returns the current scope rather than the container

```python
class Client
    def __init__(self, resolver: Resolver)
        self.resolver = resolver

    def get_number(self):
        return self.resolver.resolve(int)

container.register(int, instance=2)

container.register(Client)

client = container.resolve(Client)
client.get_number() # returns 2

with container.get_scope() as scope:
    scope.register(int, instance=10)
    scoped_client = scope.resolve(Client)
    scoped_client.get_number() # returns 10
```


## Modules (BETA feature)


A module is a just a function that accepts a container, it can be used to set up common elements on the container

```python
class ClientDependency
    def get_int(self):
        return 10

class Client
    def __init__(self, dep: ClientDependency)
        self.dep = dep

    def get_number(self):
        return self.dep.get_int()

def client_module(c: Container):
    c.register(ClientDependency)
    c.register(Client)

container.apply_module(client_module)

client = container.resolve(Client)

client.get_number() # returns 10
```



## DependencyContext (BETA feature)

You can inject a special type into your dependants that allows you to inspect the current dependency tree. For instances you can check the parent of the current class you are constructing
One example of where this becomes useful is if injecting a logger, you can get information about the loggers parent to add extra context

```python
class Logger
    def __init__(self, module):
        self.module = module

class Client
    def __init__(self, logger: Logger)
        self.logger = logger

def logger_fac(context: DependencyContext):
    module = context.parent.implementation.__module__
    return Logger(module)


container = Container()
container.register(Client)
container.register(Logger, factory=logger_fac)

client = container.resolve(Client)


```


## Pre-configurations

Pre configurations run a side-effect for a type before the type gets resolved.
This is useful if some python modules have some sort of module level functions that need to be called before the object get created

```python
import logging

class Client
    def __init__(self, logger: logging.Logger)
        self.logger = logger

    def do_a_thing(self):
        self.logger.info('Doing a thing')

def logger_fac(context: DependencyContext):
    module = context.parent.implementation.__module__
    return logging.getLogger(module)

def configuring_logging():
    logging.basicConfig()




container = Container()
container.register(Client)
container.register(logging.Logger, factory=logger_fac)
container.pre_configure(logging.Logger, configuring_logging)

client = container.resolve(Client)


```