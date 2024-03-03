
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