0.0.1
-----
    Registration and resolving works.
    Resolve errors easy to trace.
    Open generics working well.
    Instance, factory and implementation registartion works
    Decorators working.
    Open generic decoration working
    Scopes working (need to test these with multi threading)
    Allow for named registartions
    Support for list registartions

    Not tested for thread safety and performance yet


0.0.2
-----
    Add support for subclass registartion
    Add first support for modules
    Add first README


0.0.3
-----
    Fixes around Scopes
    replace dependency_settings with dependency_config in registartion


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