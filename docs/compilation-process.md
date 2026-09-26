---
description: An in-depth walkthrough of Clean IoC's compiler, from registration blueprints and occurrence-specific graph construction to frozen execution steps and runtime caches.
---

# How compilation works

Clean IoC 2 separates deciding how to construct objects from constructing them. `ContainerBuilder.build()` resolves
the composition decisions and stores their results as reusable execution plans. Later, `resolve()` follows those plans
and maintains instance caches and cleanup state.

The compiler's output is an in-memory `_PlanSet`: executable dependency plans, an inspectable component graph, root
lookup tables, and diagnostic metadata. It contains live Python references to types, callables, and configured values.
It is not generated source code, bytecode, or a graph JSON file loaded back into the runtime.

This guide explains the implementation for readers who want to understand or maintain the compiler, particularly
those familiar with V1. Underscore-prefixed types and methods are private implementation details and may change during
the V2 beta. Use the [build boundary](validation.md) and [compiler tooling](compiler-tooling.md) guides for the public API.

## From V1 resolution to V2 compilation

In V1, resolution combined candidate lookup, contextual selection, dependency-node creation, object activation,
decoration, and caching. `_Registration.build()` created a `DependencyNode`, found applicable pre-configurations,
resolved arguments, activated the object, found decorators, and cached the resulting node.

V2 computes the wiring decisions at build time and preserves them as executable steps:

```text
V1
register → resolve → select registrations → construct dependency nodes
                  → activate objects → decorate → cache

V2
register → build → select and validate wiring → freeze graph and steps
                                                       │
                resolve → follow steps → activate and cache
```

The original activation abstractions remain useful. V2 still uses internal registration, dependency, and activator
machinery from `_legacy.py`. It does not run the V1 resolver that constructs runtime dependency nodes.

Compilation does not eagerly construct application objects. Constructors, factories, generators, and context managers
run during activation. Explicit composition callbacks do run during build: filters, `derive(...)` functions,
provider-map key functions, decorator-template source filters and factories, and build-mode validation rules.

## The build pipeline

The root build follows this call chain:

```text
ContainerBuilder.build()
  ├─ _layer()
  │    ├─ snapshot registration storage
  │    └─ materialize queued registration discovery
  ├─ _Blueprint(layers, boundaries)
  └─ _compile_with_report(blueprint, build_args)
       ├─ normalize type aliases
       ├─ prepare boundary visibility
       ├─ expand decorator templates from closed, visible source registrations
       │    └─ compile undecorated sources, filter them, and call selected factories
       ├─ _Compiler(...).compile()
       │    ├─ match generated templates to eligible target occurrences
       │    ├─ recursively compile root candidates
       │    ├─ compile provider roots and boundary-local roots
       │    ├─ freeze component records
       │    └─ return _PlanSet
       └─ _finalize_plan(plan)
            ├─ validate entry points and analyze reachability
            ├─ construct the public CompiledGraph
            ├─ materialize ownership reporting
            ├─ run build-mode validation rules
            └─ attach BuildReport

Container(plan, root_owner_token)
```

The builder is marked built only after successful compilation and runtime construction. If build fails, the builder
can be repaired and retried. After success, its composition is frozen and it cannot be built again.

## Input: registrations, layers, and the blueprint

### Registration data already has structure

`_BuilderBase` uses an internal `legacy.Container` as its composition store. A public `register()` call translates the
V2 arguments and lifespan into that store's registration API, then records additional V2 metadata.

Consequently, compilation starts with familiar internal objects: `_Registry`, `_Registration`, `Dependency`, dependency
settings, and activator classes. Much of the basic signature interpretation has already happened during registration.
Generic specialization, decorators, and pre-configurations can require further signature processing during build.

The compiler does not inspect arbitrary application function bodies to discover what objects they might construct.
It compiles the dependencies expressed through supported registration and annotation mechanisms.

### A layer adds composition and ownership context

`_Layer` contains registration storage alongside:

- A declaring owner token.
- Registration predicates and declaration origins.
- Factory specializations and structural-pattern definitions.
- Decorator and pre-configuration definitions.
- Scope slots, entry points, and validation rules.
- Provider-map definitions.

For a root builder, `_layer()` snapshots the registry containers and materializes queued subclass/generic discovery.
Explicit registrations precede convention-discovered registrations. This snapshot does not deep-copy arbitrary
application values.

`_Blueprint` combines layers with boundary declarations. A normal root build usually has one ordinary layer. An overlay
has its own layer before inherited layers. Live boundary builders are snapshotted at this point, including all bundles
applied since their creation. Boundary-local definitions have separate visibility rules. Successful build freezes the
parent and its boundary handles together; failed compilation leaves them editable.

The blueprint answers: **which definitions are visible for this requested type, from this composition area, and in
what precedence order?** The compiler then determines the concrete plan those definitions produce at each occurrence.

Boundary preparation resolves `Expose` and `Use` contracts before normal root compilation. Dependencies of an exposed
registration compile with its defining area's visibility. A consumer cannot acquire extra access merely by calling it
from another boundary. See [boundaries](boundaries.md).

## The recursive unit: a component and an execution step

The central operation returns two linked representations:

```text
component, step = _compile_registration(...)
```

`Component` describes the occurrence for filtering, validation, and inspection. `_Step` executes that occurrence later.

The following is a structural sketch, not standalone executable code:

```text
compile_registration(registration, parent, requested_type):
    validate argument names

    if this is an anchored parent singleton:
        return cloned component occurrence, existing parent step

    check for a registration cycle
    check lifespan against retaining ancestors
    allocate component and mutable draft
    push registration and ownership frames

    try:
        dependencies = compile arguments
        declared_requests = compile declared runtime-resolution requests
        bind those requests into supported context dependencies
        configurations = compile pre-configurations
        decorators = compile decorator pipeline

        step = lifespan-specific step containing:
            registration and component
            dependency steps
            configurations and decorators
            declaring owner and cleanup descriptor
            transitive synchronous capability

        return component, step
    finally:
        pop frames
```

The component draft exists before recursive dependency compilation begins, so a child's compilation can inspect its
parent. The finished parent step is constructed after its children, so it can hold direct references to their steps.

### Occurrence-sensitive expansion

If `Database`, `Repository`, and `Handler` are visible registered roots, and `Handler → Repository → Database`, the
compiler produces occurrences resembling:

```text
Database

Repository
└─ Database

Handler
└─ Repository
   └─ Database
```

The three appearances of `Database` can have separate component records and separate execution-step objects. Their
parents, argument names, ancestors, derived values, applicable filters, and cleanup context can differ.

Compilation therefore expands dependency occurrences instead of creating one global step per service type. There is
targeted reuse for specialized registrations, shared initializers, and anchored parent singleton steps.

A component's `id` identifies its registration; `occurrence_id` identifies a particular use. Distinct occurrences do
not automatically imply distinct cached instances: caching uses the registration identity and the lifespan's owner.

## Candidate compilation and selection

For an ordinary dependency, the selection process is:

1. Find definitions visible in the current composition area.
2. Choose the applicable definition tier: exact registrations, matching structural patterns, or open-generic fallback.
3. Specialize candidate registrations where required.
4. Compile each candidate's subtree.
5. Evaluate its registration-level `when` predicate.
6. Apply the dependency's selection filter.
7. Select the first matching ordinary component, or retain matching collection members.

Candidate compilation precedes contextual filtering. `_compile_candidates()` calls `_compile_registration()` before
evaluating `when`. This gives the predicate a compiled candidate subtree to inspect.

It also means a false predicate cannot hide a structurally invalid candidate:

```python
from clean_ioc import ContainerBuilder, ContainerBuildError


class Missing:
    pass


class Disabled:
    def __init__(self, missing: Missing):
        self.missing = missing


builder = ContainerBuilder()
builder.register(Disabled, when=lambda component: False)

try:
    builder.build()
except ContainerBuildError as error:
    assert any(issue.code == "missing-component" for issue in error.report.errors)
else:
    raise AssertionError("The invalid candidate should fail before its predicate runs")
```

For an ordinary single dependency, several selected candidates produce an `ambiguous-selection` warning and the first
is used. Typed-provider ambiguity and incomparable structural patterns have stricter error rules. Filters rejecting
the selected definition tier do not cause a search through lower-precedence tiers.

Boundary-crossing predicates are evaluated from the defining side. The actual graph retains the consumer relationship,
but an external consumer cannot make a source registration eligible simply by becoming its contextual parent.

Composition filters are not repeated during runtime dependency activation. A filter supplied directly to `resolve()`
still executes to choose among already-compiled root plans.

## Compiling arguments into operations

V1's `Dependency.resolve()` interpreted settings, selected registrations, handled special dependencies, and resolved
the result. V2's `_compile_dependency()` chooses an executable operation during build.

| Argument meaning | Compiled operation |
| --- | --- |
| Fixed value or Python default | `_ValueStep(value)` |
| Concrete result of `derive(...)` | `_ValueStep(computed_value)` |
| Injected service | Direct reference to the selected registration step |
| Collection | `_CollectionStep(collection_type, member_steps, ...)` |
| Declared scope slot | `_ProvidedStep(service_type, name)` |
| Runtime scope or resolution context | `_ScopeStep(requested_type, ...)` |
| Typed deferred dependency | `_ProviderStep(mode, target_step, ...)` |

Each argument becomes a `_CompiledDependency` containing its parameter name and step. Activation uses those names to
build the keyword-argument dictionary expected by the constructor or factory.

A `_ValueStep(30)` simply returns `30` at runtime. A dependency step follows a direct reference to the selected
component's construction plan. A `_ProvidedStep` retrieves the declared slot from the resolving scope: its selection
is frozen, while its value is deliberately supplied later.

`inject()` and `select(...)` force dependency injection even when the parameter has a Python default. `build_arg(...)`
and `generic_arg(...)` lower through explicit build-time derivation. A derivation can also return `INJECT`, in which
case compilation continues through dependency selection rather than creating a value step.

For ordinary service injection, the compiler first attempts component selection, then a matching declared scope slot.
If neither is available, it reports a missing or visibility-related dependency error. See [argument policies](advanced/arguments.md).

## Building and freezing the component graph

`_ComponentGraph` stores occurrence records indexed by `occurrence_id`. A public `Component` is a small handle with a
reference to that graph and its occurrence ID.

During compilation, its record is a mutable `_ComponentDraft`. Recursive compilation fills fields such as
`dependency_ids`, `pre_configuration_ids`, and `decorator_ids`. On success, `graph.freeze()` converts the drafts into
frozen `_ComponentRecord` objects and clears the draft store.

Existing `Component` handles continue to work because they access their records through the graph. Records hold type
information, generic mappings, relationship IDs, names/tags, activation kinds, ownership metadata, and boundaries.

A component seen by a callback during compilation reflects that stage of construction. Its ancestors may still be
under construction. The final public graph is frozen and complete for the compiled relationships.

The graph is a description of possible construction, not a record of which objects have actually been activated.
Runtime instance caches do not live in these component records.

## Worked example: steps and caches

This complete example records construction events and uses only public APIs:

```python
from clean_ioc import ContainerBuilder


created: list[str] = []


class Database:
    def __init__(self):
        created.append("Database")


class Repository:
    def __init__(self, database: Database, timeout: int):
        created.append("Repository")
        self.database = database
        self.timeout = timeout


class Handler:
    def __init__(self, repository: Repository):
        created.append("Handler")
        self.repository = repository


builder = ContainerBuilder()
builder.register(Database, lifespan="singleton")
builder.register(Repository, lifespan="scoped", arguments={"timeout": 30})
builder.register(Handler)

with builder.build() as container:
    assert created == []

    with container.new_scope() as scope:
        first = scope.resolve(Handler)
        second = scope.resolve(Handler)

        assert first is not second
        assert first.repository is second.repository
        assert first.repository.database is container.resolve(Database)
        assert first.repository.timeout == 30

assert created == ["Database", "Repository", "Handler", "Handler"]
```

The relevant executable plans have this shape. Occurrence labels below are illustrative, not stable public IDs:

```text
Root: Database
_SingletonRegistrationStep [Database occurrence A]

Root: Repository
_ScopedRegistrationStep [Repository occurrence B]
  database → _SingletonRegistrationStep [Database occurrence C]
  timeout  → _ValueStep(30)

Root: Handler
_PerResolutionRegistrationStep [Handler occurrence D]
  repository → _ScopedRegistrationStep [Repository occurrence E]
    database → _SingletonRegistrationStep [Database occurrence F]
    timeout  → _ValueStep(30)
```

The Database steps can be different Python objects with the same registration ID. They consult the same declaring
owner's singleton cache. Separate Repository occurrences likewise share when resolved against the same effective scoped
cache. Each top-level Handler resolution gets a fresh per-resolution cache.

The result is two handlers, one repository, and one database, despite the expanded static graph.

## Executing a registration step

`_RegistrationStep` holds the registration, component, compiled dependencies, pre-configurations, decorators, declaring
owner token, cleanup descriptor, and `sync_supported` flag.

Its activation follows the same broad order as V1:

```text
run the compiled pre-configurations
resolve each compiled argument step
call the original implementation through its activator
apply the compiled decorators from core to outside
return the resulting object
```

The lifespan-specific subclass supplies the cache strategy:

| Step class | Runtime cache behaviour |
| --- | --- |
| `_TransientRegistrationStep` | Activate on each executed dependency edge |
| `_PerResolutionRegistrationStep` | Use `context.resolution_cache[registration.id]` |
| `_ScopedRegistrationStep` | Use the scope's scoped cache/inheritance lookup and first-activation coordinator |
| `_SingletonRegistrationStep` | Find the declaring owner, then use its singleton cache and coordinator |

Execution remains recursive. The recursion follows preselected step references rather than repeatedly interpreting
registrations and constructing dependency nodes. Normal root singleton/scoped cache hits also have direct shortcuts
in `Scope.resolve()` and `resolve_async()`.

## Lifespan checks and cleanup ownership

The compiler maintains `_stack` for active registrations and cycle detection, and `_frames` for richer path context:
lifespan, declaring owner, component kind, and occurrence.

For `SingletonA → TransientB → ScopedC`, SingletonA's frame is still active when ScopedC is compiled. That is how the
compiler detects the transitive captive dependency. A transient does not erase retaining ancestors.

Compilation distinguishes cache ownership from cleanup ownership. A cleanup-bearing transient retained by a singleton
has no cache of its own, but its finalizer belongs to the retaining singleton's declaring owner.

The public graph records ownership categories and reasons. The step stores an executable `_CleanupOwnerDescriptor`,
including an owner token when necessary. `_ActivationContext` adapts the existing activator interface: its
`add_finalizer()` uses that descriptor rather than the lifespan supplied by the activator.

Per-resolution cache clearing and resource cleanup are separate events. A per-resolution resource normally closes
with the resolving scope, not as soon as the top-level `resolve()` returns. Supplied values are not automatically
finalized as container-created resources. See [lifespans and cleanup ownership](lifespans.md).

## Sync capability, providers, and maps

A registration step's `sync_supported` combines its own activator capability with the capabilities of every compiled
dependency, pre-configuration, and decorator. Synchronous resolution can therefore reject an async-only root plan before
starting that root's activation. `Component.requires_async` describes local activation metadata; it is not the same
field as the execution step's transitive capability.

Typed providers preserve a direct reference to the compiled target step. Acquiring a provider does not execute its
target; calling it starts a new resolution context in its bound scope. Acquiring an `AsyncProvider[T]` can be
synchronous even though invoking the target requires `await`.

A provider frame creates a deferred boundary for eager-retention analysis. The target is still compiled and validated,
and additional checks prevent a singleton from retaining a provider whose target reaches request/scope state. A
singleton-captured provider is bound to the singleton's declaring scope owner.

Provider maps compile their selected targets and evaluate their key functions during build. The resulting map step
stores frozen key-to-index information and provider targets. Runtime map acquisition creates scope-bound handles;
looking up a key and calling its handle activates the selected target without repeating key calculation or selection.
See [special dependency types](advanced/special-dependency-types.md).

`ProviderMapGroup` maps make the candidate set explicit before specialization and target compilation: only visible
registrations whose `contributes` metadata contains that exact group identity are considered. Contributions are
composition metadata, not a resolution filter. The existing `component_filter` then runs on the compiled selected
targets, and all ordinary cycle, ownership, async, boundary, and key validation remains in force.

## Decorators and shared pre-configurations

Decorator applicability is evaluated against the completed undecorated core subtree before decorator dependencies
are added. Selected definitions become `_CompiledDecorator` objects with their own dependency steps, activators,
cleanup descriptors, and sync capability.

Runtime decoration proceeds from core to outside. Component inspection presents the pipeline outside-to-inside.
Decorator dependencies participate in the same cycle, lifetime, and async analysis as constructor dependencies.

Pre-configurations compile once per definition and are shared across applicable targets. Their dependency paths are
validated as singleton-owned paths even if a transient component triggers them. They remain lazy: the first applicable
activation runs the initializer, and concurrent callers join its in-flight attempt.

The wiring is fixed, but `_CompiledPreConfiguration` references mutable completion/coordination state. Default failures
can be retried by a later resolution. See [pre-configurations](pre-configurations.md) for optional-failure semantics.

## Generic specialization

For a structural factory template `Serializer[list[T]]` requiring `Serializer[T]`, a request for
`Serializer[list[Order]]` binds the pattern variable to `Order` and compiles a `Serializer[Order]` dependency.

The original factory remains the callable invoked at runtime. Specialization rewrites dependency descriptions and
closed registration metadata. Closed generic constructors similarly receive substituted dependency annotations while
preserving the original class.

Factory specializations are memoized by registration identity and requested runtime type key. Their specialized IDs
give different closed services separate lifespan caches. This memoization does not eliminate parent-specific occurrence
compilation: one specialized registration may still appear under several parents.

Service generic mappings and factory-pattern bindings can differ. For example, a service parameter can map to
`list[Order]` while the pattern's variable maps to `Order`.

Open templates do not enumerate an unlimited set of roots. `_Compiler.compile()` skips unresolved open templates as
direct roots, compiles known closed requests, and incorporates supported discovered pattern requests. An entry-point
marker focuses an available request; it does not cause arbitrary unseen specializations to exist. Runtime resolution
does not compile new types. See [generics](generics.md) for exact registration and pattern rules.

## What is in the final plan?

Each `_RootPlan` pairs a `Component` with a `_Step`. `_PlanSet` collects these roots and the surrounding metadata:

| Field | Purpose |
| --- | --- |
| `roots` | Service key to ordered eligible root candidates |
| `default_roots` | Service key to the preselected default root |
| `default_root_groups` | Unnamed root candidates for default group selection |
| `provider_roots` | Precompiled deferred root plans |
| `graph` | Internal occurrence-record store |
| `compiled_graph` | Public graph inspection and tooling interface |
| `blueprint` | Retained composition structure for overlays and validation |
| `build_args` | Immutable mapping of inputs associated with the build |
| `build_report` / `compiler_issues` | Final findings and compilation diagnostics |
| `root_candidates` / `occurrence_explanations` | Recorded selection evidence |
| `architecture_roots` / `area_root_candidates` | Architectural roots and boundary-local candidate evidence |

`RootPlan.component` lets tooling inspect wiring; `RootPlan.step` lets the runtime execute it. Private boundary roots
can participate in architectural validation without becoming publicly resolvable roots.

The JSON manifest is a deterministic, redacted projection for inspection and comparison. It does not serialize the
executable `_PlanSet`. Configured values, build-input keys/values, runtime identities, and provenance are excluded from
default semantic manifests as described in [compiler tooling](compiler-tooling.md).

"Immutable" describes supported composition and runtime wiring. It does not imply that every reachable Python object
is deeply immutable: fixed values can be mutable application objects, internal mappings are not all deeply frozen,
and caches and pre-configuration coordination state necessarily change during execution.

## Finalization and failed builds

After recursive compilation, `_finalize_plan()` validates entry-point selections, computes reachability warnings,
constructs the public `CompiledGraph`, materializes ownership reporting, and runs custom rules with `mode="build"`.
It returns the plan with its `BuildReport`, or raises when the report contains errors.

Rules with `mode="validation"` run only during explicit validation. That pass retains stored build findings without
rerunning build-mode rules. Entry-point markers influence default rendering and reachability warnings; they do not
reduce whole-composition validation to only the marked roots.

The main recursive descent generally raises on its first structural failure. When no complete report is already
available, `_error_report()` attempts roots independently with fresh compiler instances and aggregates their failures.
Errors before normal graph compilation, such as invalid boundary contracts, can instead produce an immediate report.

Diagnostic retries can execute composition callbacks again. "Runs at build time" does not mean "runs exactly once".
Filters and derivations should be pure. Explanation rendering reads captured decisions and does not rerun them.

Successful compilation proves the supported structural constraints, not the eventual success of user activation. A
factory can still fail to connect to a database, and objects created inside arbitrary application code remain outside
the statically declared dependency graph.

## Overlay compilation and anchored steps

`ScopeBuilder` creates a blueprint with its layer before the parent's layers, and passes the parent's singleton steps,
initializer plans, and owner tokens to the compiler.

When an inherited singleton is encountered, the compiler clones its component representation into the overlay graph
but retains the parent's executable step. The graph can describe its relationship to a new consumer while execution
keeps the original dependencies, build arguments, decorators, and cleanup owner.

An overlay cannot introduce a previously uncompiled specialization of a parent-owned singleton. It must provide an
appropriate overlay-owned definition instead. Inherited pre-configurations are anchored similarly.

The built overlay starts a fresh scoped-cache boundary and owns its newly declared singletons. Ordinary `new_scope()`
reuses its parent's `_PlanSet` and performs no compilation. See [scopes and scope builders](scopes.md).

## Source reading map

The following symbols connect the public build boundary to the executable output:

| Source | Symbols to follow |
| --- | --- |
| [`container.py`](https://github.com/peter-daly/clean_ioc/blob/main/clean_ioc/container.py) | `ContainerBuilder.build()`, `_BuilderBase._layer()`, `_Blueprint`, `_compile_with_report()` |
| [`container.py`](https://github.com/peter-daly/clean_ioc/blob/main/clean_ioc/container.py) | `_Compiler.compile()`, `_compile_candidates()`, `_compile_registration()`, `_compile_dependency()` |
| [`components.py`](https://github.com/peter-daly/clean_ioc/blob/main/clean_ioc/components.py) | `_ComponentDraft`, `_ComponentRecord`, `_ComponentGraph`, `Component` |
| [`container.py`](https://github.com/peter-daly/clean_ioc/blob/main/clean_ioc/container.py) | `_RootPlan`, `_PlanSet`, `_RegistrationStep`, `_RuntimeResolutionContext`, `Scope.resolve()` |
| [`tooling.py`](https://github.com/peter-daly/clean_ioc/blob/main/clean_ioc/tooling.py) | `CompiledGraph`, `CompilationExplanation`, `BuildReport`, `GraphManifest` |
| [`_legacy.py`](https://github.com/peter-daly/clean_ioc/blob/main/clean_ioc/_legacy.py) | Registration/dependency representation and activators reused by the compiled implementation |
