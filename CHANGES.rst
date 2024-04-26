0.0.1
-----
    Registration and resolving works.
    Resolve errors easy to trace.
    Open generics working well.
    Instance, factory and implementation registration works
    Decorators working.
    Open generic decoration working
    Scopes working (need to test these with multi threading)
    Allow for named registrations
    Support for list registrations

    Not tested for thread safety and performance yet


0.0.2
-----
    Add support for subclass registration
    Add first support for modules
    Add first README


0.0.3
-----
    Fixes around Scopes
    replace dependency_settings with dependency_config in registration


0.0.4
-----
    Lifestyles changed to Lifespans
    Added support for the dependency nodes and dependency context
    Improved Generic Decorators resolving
    Added factory for a dictionary

0.0.5
-----
    Fixed decorator resolving order


0.0.6
-----
    Added the has_registration to the container
    Added depenency_settings to Decotator registration
    Basics for DependencyGraph


0.1.0
-----
    Move from Beta to Production



0.1.1
-----
    Add pre configurations


0.1.2
-----
    Improve dependency graph modelling
    Add ability for kwargs in dependency settings
    Add generics detection for typing.Protocol

0.1.3
-----
    Fix register method signature for scopes

0.2.0
-----
    Change default registration filter for dependencies from all registrations to is not named
    Add tags feature

0.2.1
-----
    Add more registration filters for tags

0.3.0
-----
    container.resolve, resolver.resolve and scope.resolve now have better type safety
    Scopes can new be context manager and async context manager
    Scopes now track all instances it created by service_type, this enables easy access from the functions on scope teardown
    List reduction filters for list resolving
    Added support for parent context filters

0.3.1
-----
    Add a base module class
    Add fastapi extension

0.3.2
-----
    Change base module class to not need a child class to call super().__init__ 


0.9.0
-----
    Add support for scoped teardowns
    Add parent decorator contexts
    Make dependency graphs and object graphs uniform with each other

0.10.0
-----
    Add py.typed files

0.11.0
-----
    Remove deprecated container.append_module()
    Add unparenting to cached nodes after resolving context is complete to avoid potential memory leaks

0.12.0
-----
    Added predicates for registration filters
    Fix bug with OnlyRunOncePerInstanceBundle
    Added future support for python 3.12 generics

0.16.0
-----
    BREAKING CHANGES:
    Removed ParentContext and DecoratorContext and just use Nodes directly
    DecoratorContextFilter replaced with NodeFilter
    ParentContextFilter replaced with NodeFilter
    clean_ioc.dependency_context_filters replaces with clean_ioc.node_filters
    parent_context_filter arg replaced with parent_node_filter in all registartion methods
    decorator_context_filter arg replaced with decorator_node_filter in all decorator methods


0.16.1
-----
    make Tag class destructurable for filter functions

0.17.0
-----
    improvements to how generic type args are mapped in generic dependencies
    export fast api extension dependencies as already wrapped in Depends
    Remove dynamic name generation when regestering subclasses
    more node filters
    more registration filters
    improve typing for nodes


0.18.0
-----
    container.register(ServiceType, ImplementationType) now allows resolving from implementation types
        container.resolve(ServiceType) and container.resolve(ImplementationType) both work for resolving.