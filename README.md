# Clean IoC
A simple dependency injection library for python that requires nothing of your application code (except that you use typing).


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

## List resolving

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


## Decorators

Follows a object orientated decoration pattern, rather than a decoration annotation.
The main reason for this was to allow decotation of registered instances

```python
class Client:
    def __init__(self, number: int):
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
Only create a new instance through the lifetime a [scope](#scopes). When not in a scope the behaviour is the same as **once_per_graph**.

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
Scopes are a machanism where you guarantee that dependency can be temporarily a singleton within the scope. You can also register dependencies that that are only available withon the scope.
Some good use cases for scope lifetimes are:
 - http request in a web server
 - message/event if working on a message based system
For instance you could keep an single database connection open for the entire lifetime of the http request

```python
class DbConnection:
    def run_sql(self, statement):
        # Done some sql Stuff
        pass

container.register(DbConnection, lifespan=Lifespan.scoped)

with container.get_scope() as scope:
    db_conn = scope.resolve(DbConnection)
    db_conn.run_sql("UPDATE table SET column = 1")
```

Scopes can also be use with asyncio

```python
class AsyncDbConnection:
    async def run_sql(self, statement):
        # Done some sql Stuff
        pass

container.register(AsyncDbConnection, lifespan=Lifespan.scoped)

async with container.get_scope() as scope:
    db_conn = scope.resolve(AsyncDbConnection)
    await db_conn.run_sql("UPDATE table SET column = 1")
```


### Scoped Teardowns
When you are finished with some dependenies within a scope you might want to perform some teardown action before you exit the scope. For example if we want to close our db connection.

```python
class AsyncDbConnection:
    async def run_sql(self, statement):
        # Done some sql Stuff
        pass
    async def close(self):
        # Close the connection
        pass

async def close_connection(conn: AsyncDbConnection):
    await conn.close()

container.register(DbConnection, lifespan=Lifespan.scoped, scoped_teardown=close_connection)

async with container.get_scope() as scope:
    db_conn = scope.resolve(AsyncDbConnection)
    await db_conn.run_sql("UPDATE table SET column = 1")

# close connection is run when we exit the scope
```

***Note***: *When using the scope as an async context manager you need both sync and async teardowns are run, when a scope is used as a normal sync context manager async teardowns are ignored*


## Named registrations & Registration filters

By default the last unnamed registration is what the container will return when resolve is called as below.

```python

container = Container()
container.register(int, instance=1)
container.register(int, instance=2)
container.register(int, instance=3)

number = container.resolve(int) # returns 3

```
To be more selective of what we return we can add a name to the registration and apply a registration filter when we resolve.

A registration filter is simply function that receives a **Registration** and returns a **bool**

For example if we wanted to get the int named **"One"** we do the following

```python
container = Container()
container.register(int, instance=1, name="One")
container.register(int, instance=2, name="Two")
container.register(int, instance=3, name="Three")

number = container.resolve(int, filter=lambda r: r.name == "One") # returns 1
```

Clean IOC comes with a set of in built registration filters that can be found [here](./clean_ioc/registration_filters.py)

We can get the desired behaviour as above
```python
from clean_ioc.registration_filters import with_name

container = Container()
container.register(int, instance=1, name="One")
container.register(int, instance=2, name="Two")
container.register(int, instance=3, name="Three")

number = container.resolve(int, filter=with_name("One")) # returns 1
```

## Dependency Settings

Dependency settings are defined at registration and allow you to define the selection or setting dependencies


```python
class Client:
    def __init__(self, number=10):
        self.number = number

    def get_number(self):
        return self.number

container = Container()

container.register(int, instance=1, name="One")
container.register(int, instance=2)

container.register(
    Client,
    name="SetsValue",
    dependency_config={"number": DependencySettings(value_factory=set_value(50))}
)
container.register(
    Client,
    name="UsesDefaultValue"
)
container.register(
    Client,
    name="IgnoresDefaultParameterValue",
    dependency_config={"number": DependencySettings(value_factory=dont_use_default_parameter)}
)
container.register(
    Client,
    name="UsesRegistrationFilter",
    dependency_config={"number": DependencySettings(value_factory=dont_use_default_parameter, filter=with_name("One"))}
)

client1 = container.resolve(Client, filter=with_name("SetsValue"))
client2 = container.resolve(Client, filter=with_name("UsesDefaultValue"))
client3 = container.resolve(Client, filter=with_name("IgnoresDefaultParameterValue"))
client4 = container.resolve(Client, filter=with_name("UsesRegistrationFilter"))


client1.get_number() # returns 50
client2.get_number() # returns 10
client3.get_number() # returns 2
client4.get_number() # returns 1
```

The order of a dependant value is as follows
1. Setting the dependency value_factory to an explicit value
    ```python
    DependencySettings(value_factory=set_value(50))
    ```
    If the falue is a default parameter then the default value factory will use that default parameter value
    ```python
    class Client:
        def __init__(self, number=10):
            self.number = number
    ```
    If you don't want to use the default parameter value you can change the value_factory to pybass it
    ```python
        DependencySettings(value_factory=dont_use_default_parameter)
    ```
2. Going to the container registry to find a registration using the registration filter if, if there is a default value on the dependant paramater you must explicity set.


## Tags

Tags can be added to registrations in order to support filtering. This can be useful as a means to filter registrations when resolving lists of a particular type

```python
class A:
    pass

a1 = A()
a2 = A()
a3 = A()

container = Container()

container.register(A, instance=a1, tags=[Tag("a", "a1")])
container.register(A, instance=a2, tags=[Tag("a")])
container.register(A, instance=a3)

ar1 = container.resolve(A, filter=has_tag("a", "a1")) # returns a1
al1 = container.resolve(list[A], filter=has_tag("a"))  # returns [a2, a1]
al2 = container.resolve(list[A], filter=has_tag("a", "a1")) # returns [a1]
al3 = container.resolve(list[A], filter=~has_tag("a", "a1"))  # returns [a3, a2]
al4 = container.resolve(list[A], filter=~has_tag("a")) # returns [a3]
al5 = container.resolve(list[A]) # returns [a3, a2, a1]
```



## Parent Node Filters

Registrations can also specify that should only apply to certain parents objects by setting the parent_node_filter

```python
class A:
    pass

class B(A):
    pass

class C(A):
    pass

class D:
    def __init__(self, a: A):
        self.a = a

class E:
    def __init__(self, a: A):
        self.a = a

container = Container()

container.register(A, B, parent_node_filter=implementation_type_is(E))
container.register(A, C, parent_node_filter=implementation_type_is(D))
container.register(D)
container.register(E)

e = container.resolve(E)
d = container.resolve(D)

type(e.a) # returns B
type(d.a) # returns C

```



## Accessing the Container, Scope and Resolver within dependencies

Accessing container directly

```python
class Client:
    def __init__(self, container: Container):
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

class Client:
    def __init__(self, resolver: Resolver):
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
class Client:
    def __init__(self, resolver: Resolver):
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

Scopes can also be used as an async context manager

```python
class Client:
    async def get_number(self):
        return 10

container.register(Client)

async with container.get_scope() as scope:
    scoped_client = scope.resolve(Client)
    await scoped_client.get_number() # returns 10
```

## Bundles


A bundle is a just a function that accepts a container, it can be used to set up related registrations on the container

```python
class ClientDependency:
    def get_int(self):
        return 10

class Client:
    def __init__(self, dep: ClientDependency):
        self.dep = dep

    def get_number(self):
        return self.dep.get_int()

def client_bundle(c: Container):
    c.register(ClientDependency)
    c.register(Client)

container.apply_bundle(client_bundle)

client = container.resolve(Client)

client.get_number() # returns 10
```

### Helper for bundles

There is now a ```BaseBundle``` class that gives you a bit more safety around running a module twice etc. Also you might want to pass in instances into the module.
You can find the ```BaseBundle``` in ```clean_ioc.bundles``` module



```python
@dataclass
class ClientConfig:
    url: str

class Client:
    def __init__(self, config: ClientConfig):
        self.base_url = config.url

    def get_thing(self):
        # Do some requests stuff here
        pass



class ClientBundle(BaseBundle):

    def __init__(self, config: ClientConfig):
        self.config = config

    def apply(self, c: Container):
        c.register(ClientConfig, instance=self.config)
        c.register(Client)



client_config = ClientConfig(
    url = "https://example.com"
)

container.apply_bundle(ClientBundle(config=client_config))

client = container.resolve(Client)

client.get_thing()
```


## Dependency Context (BETA feature)

You can inject a special type into your dependants that allows you to inspect the current dependency tree. For instances you can check the parent of the current class you are constructing
One example of where this becomes useful is if injecting a logger, you can get information about the loggers parent to add extra context

```python
class Client:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def do_a_thing(self):
        self.logger.info('Doing a thing')

def logger_fac(context: DependencyContext):
    module = context.parent.implementation.__module__
    return logging.getLogger(module)


container = Container()
container.register(Client)
container.register(logging.Logger, factory=logger_fac, lifespan=Lifespan.transient)
client = container.resolve(Client)
```

***Note*** *If using dependency context on your dependency it's recommended that you use a lifespan of **transient**, because any other lifespan will create only use the parent of the first resolved instance*
## Pre-configurations

Pre configurations run a side-effect for a type before the type gets resolved.
This is useful if some python modules have some sort of module level functions that need to be called before the object get created

```python
import logging

class Client:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def do_a_thing(self):
        self.logger.info('Doing a thing')

def logger_fac(context: DependencyContext):
    module = context.parent.implementation.__module__
    return logging.getLogger(module)

def configure_logging():
    logging.basicConfig()




container = Container()
container.register(Client)
container.register(logging.Logger, factory=logger_fac, lifespan=Lifespan.transient)
container.pre_configure(logging.Logger, configure_logging)

client = container.resolve(Client)


```