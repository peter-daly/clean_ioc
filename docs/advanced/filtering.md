

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


