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
Only create a new instance through the lifetime a [scope](#scopes). When not in a scope the behaviour is the same as **singleton**.

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
