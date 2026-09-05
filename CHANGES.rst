2.0.0b6
-------
    Add immutable compilation explanations with selected and rejected candidates,
    stable reason codes, declaration provenance, and ``clean-ioc explain``.
    Add compiled cache and cleanup ownership proofs, owner-correct resource
    finalization, closed-scope safety, and ``clean-ioc ownership``.
    Add typed ``Provider[T]`` and ``AsyncProvider[T]`` handles that execute frozen
    deferred plans without adding service lookup to the runtime hot path.
    Add compile-time assemblies with private-by-default bundle registrations,
    unchanged exposures, explicit root and cross-assembly uses, overlay support,
    structured visibility diagnostics, provenance, and manifest-schema-3 tooling.
    Expand BenchBro coverage for compiler features, strict validation, ownership,
    runtime scaling, allocations, and FastAPI request integration.


2.0.0b5
-------
    Add strict-only custom graph rules that defer expensive validation and AST
    inspection until an explicit validation report or CLI check.
    Make ``clean-ioc check`` strict by default, retaining ``--no-strict`` for
    lightweight checks, and document factory functions returning built containers.


2.0.0b4
-------
    Pass one ephemeral ``ValidationContext`` to custom graph rules and add lazy,
    per-build AST inspection for Python implementation types.


2.0.0b3
-------
    Add reusable custom build-time graph validation rules with structured findings,
    overlay inheritance, and path-aware traversal of compiled occurrences.


2.0.0b2
-------
    Require Python 3.11 or newer.
    Package optional FastAPI boundary declarations as a run-once-per-builder
    ``FastAPIBundle`` and complete the shared builder protocol for nested bundles.


2.0.0b1
-------
    Split mutable composition into ``ContainerBuilder`` and ``ScopeBuilder`` and
    make ``Container`` and ``Scope`` immutable runtime types.
    Compile occurrence-specific component plans at ``build()`` without invoking
    constructors, factories, generators, or context managers.
    Replace ``dependency_config`` and mutable ``DependencySettings`` with one
    ``arguments`` API for fixed values, explicit component selection, and pure
    build-time derivation; remove runtime value providers and list reducers.
    Add immutable user-defined ``build_args`` to root and overlay compilation,
    exposing them to derivation and component filters, with
    ``build_arg(name, default=...)`` for explicit frozen-value projection,
    without implicit runtime injection or disclosure through graph diagnostics.
    Add ``inject()`` for forcing unnamed injection over a Python default and
    ``generic_arg(...)`` for freezing an owning component's generic binding.
    Execute frozen activation instructions without allocating legacy dependency
    graph nodes during normal resolution.
    Specialize compiled runtime steps by lifespan, freeze sync capability and
    default root selection at build, and defer runtime UUID creation until an ID
    is inspected, reducing resolution and ordinary scope-creation overhead.
    Make the compiled builder/runtime design the only public API: retire the V1
    container and its registration/node filters, remove compatibility aliases,
    and expose the implementation through ``clean_ioc.container`` rather than a
    versioned module.
    Replace public registration/node filtering with the immutable ``Component``
    model and shared ``clean_ioc.component_filters`` predicates.
    Add declared scope slots and locked ``Scope.provide()`` values for FastAPI and
    other late framework inputs.
    Add experimental scope overlays whose singletons belong to the built scope and
    descendants.
    Defer subclass, closed-generic, and generic-decorator discovery until
    ``build()``, making the successful build snapshot complete and immutable.
    Specialize closed and open generic factory dependencies at build time, with
    explicit ``factory_specialization`` support for otherwise hidden TypeVars.
    Replace the sealed-container prototype with BenchBro build, runtime, scope,
    request-slot, and Python-allocation experiments.
    Add entry-point markers, aggregated structured build reports, complete compiled
    graph inspection, deterministic redacted manifests, semantic graph diffs, and
    the ``clean-ioc check|graph|diff`` command-line interface.
    Anchor inherited root singletons to their frozen root activation plans and
    make a built scope overlay a fresh scoped-cache boundary.
    Reject direct and transitive ``once_per_graph`` dependencies beneath scoped
    or singleton components as captive dependencies during ``build()``.
    Modernize the FastAPI extension for FastAPI 0.121+, with one-call ASGI
    installation, HTTP and WebSocket scopes, automatic request/header values,
    full-response cleanup, and startup validation of every ``Resolve`` route.
    Remove the ``scoped_teardown`` registration option; generator and context-manager
    factories now provide the single resource-cleanup model.
    Make decorators stable builder definitions with IDs, owned metadata, patch/remove
    operations, one ``when=`` filter, build-time validation, z-index graph rendering,
    and open-generic specialization from actual compiled plans.
    Replace the public V2 ``Lifespan`` enum values with ``Literal`` string arguments
    and expose those same strings through components, filters, and graph manifests.
    Compile pre-configurations as stable, shared singleton initializers with one
    ``when=`` filter, declaration ordering, generic matching, captive-dependency
    validation, concurrent single-flight execution, owner-correct cleanup, and
    deterministic failure/retry behavior.


1.25.0
------
    Add static ``Container.validate()`` checks for missing registrations, circular
    dependencies, captive scoped dependencies, and async-only graphs.
    Add ``Container.explain()`` with readable text and Mermaid dependency plans.
    Raise dedicated ``CircularDependencyError`` and ``CaptiveDependencyError``
    exceptions during runtime resolution.
    Coordinate first-time scoped and singleton activation across concurrent threads
    and async tasks, including safe failure and retry behavior.
    Expand FastAPI support from 0.101.x to all compatible 0.x releases and test both
    the minimum and latest supported versions in CI.
    Add a runnable FastAPI Clean Architecture example, reproducible microbenchmarks,
    and a documentation and project-positioning overhaul.


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

0.18.1
-----
    FIX: pre_configurations failed wehen run in async mode.

1.0.0
-----
    First proper release
    Scopes can now spawn new scopes.
    Pre configrations api has been improved
    Scoped lifespan now acts as a singleton in a container
    Container can now be used as a context manager the same way scopes can.
    Container can now how scoped teardowns and generator factories on sigletons the same way scopes can.

1.1.0
-----
    Decorators can now be functions or generators
    Pre-configurations can now be functions or generators
