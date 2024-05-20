
## Bundles
As objects grow bigger it's you will find that you have a lot of cohesive sets of components that you want to register. For example if you want to have a sqlalchemy Session you will likely want a sqlalchemy Engine. This is where bundles come in to plat

A bundle is a just a ```Callable[[Container], None]``` with a container, it can be used to set up related registrations on the container.
The simples type of bundle is a simple function that takes a container as a argument.

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

There are now a set Bundle classes that can be used to set up bundles
    - ```BaseBundle```: Basic callable for containers
    - ```OnlyRunOncePerInstanceBundle```: Only run the bundle once in the container instance
    - ```OnlyRunOncePerClassBundle```: Only run this bundle class once in a container

You can find these classes in the `clean_ioc.bundles` module.

These bundle classes are also useful if you want to pass instances of dependencies with your bundle.


```python
@dataclass
class ClientConfig:
    url: str

class Client:
    def __init__(self, config: ClientConfig):
        self.base_url = config.url

    def get_user(self):
        # Do some requests stuff here
        pass



class ClientBundle(OnlyRunOncePerClassBundle):

    def __init__(self, config: ClientConfig):
        self.config = config

    def apply(self, c: Container):
        c.register(ClientConfig, instance=self.config)
        c.register(Client)



client_config = ClientConfig(
    url = "https://example.com"
)

container.apply_bundle(ClientBundle(config=client_config)) # Gets applied
container.apply_bundle(ClientBundle(config=client_config)) # Does not get applied

client = container.resolve(Client)

user = client.get_user()
```