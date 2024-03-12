# Decorators

Clean IoC allows you to add extra functionality to dependencies via decoration.
It achieves this with what would look traditionally like an Object Oriantated deocorator pattern. This is very different to trational python deocorator functions.


!!! question "Why use a different decorator pattern?. This looks like Java"

    There are a few reasons for this:

    1. It means we can focus deocating the abstraction rather then the concrete implementation for a registration
    2. Allows decorators to have their own dependencies that can be resolved
    3. When we just register an instances, it can also be deocrated.
    4. Allows us to selectivly apply decorators



!!! question "Are you suggesting that python should change how it tradionally does decoration for cross cutting concerns?"

    Absolutly not. When adding cross cutting concerns to classes and functions in python, tradional python deocorators work fantastically. They do start to fail to get tricky when the deocorator needs dependencies from an ioc container.


```python
class NumberGetter:
    def __init__(self, number: int):
        self.number = number

    def get_number(self):
        return self.number


class DoublerNumberGetter(NumberGenerator):
    def __init__(self, inner: NumberGetter):
        self.inner = inner
    def get_number(self):
        return self.inner.get_number() * 2

container = Container()

container.register(NumberGetter)
container.register_decorator(NumberGetter, DoublerNumberGetter)
container.register(int, instance=10)

getter = container.resolve(NumberGetter)

getter.get_number() # returns 20
```

!!! info "Info"
    Decorators are resolved in order of when first registered. So the first registered decorator is the highest in the class tree

```python
    class Abstract:
        pass

    class Concrete:
        pass

    class DecoratorOne(Abstract):
        def __init__(self, child: Abstract):
            self.child = child

    class DecoratorTwo(Abstract):
        def __init__(self, child: Abstract):
            self.child = child

    container = Container()

    container.register(Abstract, Concrete)
    container.register_decorator(Abstract, DecoratorOne)
    container.register_decorator(Abstract, DecoratorTwo)

    root = container.resolve(Abstract)

    type(root) # returns DecoratorOne
    type(root.child) # returns DecoratorTwo
    type(root.child.child) # returns Concrete
```


## Filtering Decorators

You can also filter decorators like you can with regular registrations.
