# Clean IoC V2 engineering handoff

This document records the V2 architecture and implementation decisions made so far. It is intended for agents and maintainers extending V2 without accidentally restoring runtime graph construction, weakening build invariants, or breaking scope ownership.

V2 is currently published in project metadata as `2.0.0a1`. Its compatibility surface remains experimental.

## Core model

V2 separates mutable composition from immutable runtime execution:

```text
ContainerBuilder
    -> frozen composition blueprint
    -> build-time discovery, validation, filtering, and generic specialization
    -> occurrence-specific component graph and activation steps
    -> immutable Container

Container/Scope
    -> select a compiled root
    -> execute frozen activation steps
    -> cache values and own cleanup
```

- `ContainerBuilder` and `ScopeBuilder` are the only mutable composition APIs.
- `Container` and `Scope` contain frozen `_PlanSet` instances and expose no registration APIs.
- A failed build leaves its builder reusable. A successful build makes the builder single-use.
- Every visible closed root is compiled and validated. `mark_entrypoint()` only focuses tooling and reachability analysis; it does not weaken validation or make unmarked roots unresolvable.
- Building never invokes user constructors, factories, generators, context managers, or parameter value providers.
- Runtime resolution executes `_Step` objects. It does not allocate legacy `DependencyNode`/object-graph structures.

The legacy implementation in `clean_ioc/core.py` still supplies registration storage, activators, dependency parsing, and filters needed for compatibility. V2 converts its public string-literal lifespans to the legacy enum only at this internal boundary. Do not expose that enum through V2 components or route V2 runtime resolution back through the legacy dependency graph.

## Immutable component model

`clean_ioc/components.py` contains the unified public `Component` model used by filters and graph inspection. Registration metadata and compiled graph nodes are not separate public concepts in V2.

Each compiled occurrence records:

- service and implementation identity;
- stable registration `id` and occurrence-specific `occurrence_id`;
- lifespan, name, tags, argument, and generic mapping;
- parent, dependencies, decorators, decorated component, and pre-configurations;
- `ComponentKind`, `ComponentActivation`, `requires_async`, and `manages_cleanup`.

Component kinds currently cover registrations, decorators, pre-configurations, collections, scope slots, fixed/default values, value providers, and runtime contexts. When adding a new activation edge, represent it in this graph as well as in the runtime step tree. Filters, manifests, diagnostics, and reachability depend on the graph being complete.

Draft records are mutable only while `_Compiler` is building the graph. `_ComponentGraph.freeze()` replaces them with immutable records before a runtime is returned.

## Build and validation invariants

`ContainerBuilder.build()` materializes pending discovery rules, specializes generics, compiles all roots, evaluates composition filters, builds structured diagnostics, and freezes the result.

Current hard failures include missing components, circular paths, invalid generic specialization, invalid parent singleton specialization in an overlay, missing marked entry points, and captive lifespans.

Captive lifespan rules are transitive across constructors, factories, decorators, collections, value-provider fallbacks, and pre-configuration dependencies:

```text
singleton -> scoped                         invalid
singleton -> once_per_graph                 invalid
singleton -> transient -> once_per_graph    invalid
scoped -> once_per_graph                    invalid
scoped -> transient -> once_per_graph       invalid

singleton/scoped -> plain transient         valid
transient -> once_per_graph                  valid
once_per_graph -> scoped/singleton           valid
```

Invalid lifespan paths use the `captive-dependency` issue code and retain the complete semantic path. A transient is allowed beneath a long-lived component but cannot hide an invalid descendant.

Independent root failures are aggregated in `BuildReport`. `ContainerBuildError.report` carries the report after failure; successful runtimes expose it as `build_report`. Warnings are nonfatal in Python and may be promoted to failures by CLI policy. Current warnings include ambiguous selection and registrations unreachable from marked entry points.

When changing validation:

1. Validate the whole dependency path, not only direct constructor parameters.
2. Preserve the error code and semantic component path.
3. Keep a failed builder repairable.
4. Test all compiled edge types when the rule is meant to be graph-wide.

## Pre-configuration compilation and ownership

`pre_configure()` stores an immutable `_PreConfigurationDefinition` with a stable ID, target service types, frozen dependency configuration, declaration order, one `when` filter, and failure policy. Definitions execute in declaration order within a layer and parent layers precede overlay layers. Do not route V2 pre-configurations back through the mutable legacy registry or restore separate registration/node filters.

The compiler matches definitions against the actual compiled service type. This is important for open registrations specialized to closed generic aliases: an exact target such as `Service[int]` must not be treated as the iterable of its type arguments, while an open target must apply to its closed specializations.

One definition has one `_CompiledPreConfiguration`, component occurrence, and `_PreConfigurationState` across all matching trigger roots in a compiled plan. Its dependency path is compiled inside an explicit singleton `_CompilerFrame`, independently of the triggering registration's lifespan. This makes scoped and `once_per_graph` captures build errors and makes recursive shared-trigger paths diagnosable.

Scope overlays anchor an inherited initializer to the parent's compiled plan as well as its shared runtime state. Clone its component metadata into the overlay graph, but retain its parent activation steps; otherwise dependency selection would depend on which scope wins the first runtime trigger. A parent definition with no compiled plan cannot become newly applicable in an overlay and reports `overlay-pre-configuration`; declare it on the `ScopeBuilder` instead.

Runtime execution is lazy and single-flight across sync and async callers. A successful attempt marks the shared state complete. A propagated failure wakes current waiters with the same failure but leaves the state retryable; `continue_on_failure=True` logs a configuration-function failure and marks the attempt complete. Dependency-resolution failures always propagate because activation did not occur. Keep dependency resolution and user-code activation outside the state lock.

Pre-configuration generator/context-manager finalizers belong to the definition's declaring owner token. They must not be attached to whichever overlay happened to trigger the initializer first. Dependencies retain their own registration ownership.

## Lifespans, activation, and cleanup

- Public builder arguments and `Component.lifespan` use the literal strings `"transient"`, `"once_per_graph"`, `"scoped"`, and `"singleton"`; the V1 `IntEnum` is internal compatibility machinery only.
- `transient` activates on each dependency edge.
- `once_per_graph` uses the `once_cache` owned by one `_RuntimeResolutionContext`/top-level resolve.
- `scoped` uses the current scope cache and coordinator.
- `singleton` uses the owner selected by the registration layer's owner token.

Generator factories and context managers register finalizers with their cache owner. Sync and async resolution share the compiled plan, with async requirements determined at build time and enforced when selecting the runtime path. Keep resource acquisition and release in the same factory; registration-level cleanup callbacks are intentionally unsupported.

Scoped and singleton first activation is coordinated across threads and async tasks. Preserve `_Coordinator` behavior when modifying caching or activation; failures must wake waiters and permit later retries.

Known follow-up: plain transients are allowed beneath singletons, but cleanup-bearing transient ownership and runtime-context capture deserve separate validation. In particular, `Scope`/`ResolutionContext` can provide dynamic access that static registration traversal cannot fully describe. Do not fold this into an unrelated feature without explicit semantics and tests.

## Scopes and overlays

Ordinary `new_scope()` is cheap and never recompiles. It reuses the parent's plan, inherits provided slot values, and may inherit already-created scoped values. Declared slots are supplied with `scope.provide()` before the first resolution; undeclared, duplicate, late, or missing provisions fail.

`new_scope_builder()` is the explicit child-composition boundary:

- it layers new composition over the frozen parent blueprint and recompiles visible overlay roots;
- it starts a fresh scoped cache boundary so inherited scoped registrations may use overlay dependencies;
- singletons introduced by the overlay belong to the built overlay scope and are finalized there;
- inherited root singletons stay anchored to their original frozen activation step and root owner;
- overlay registrations and decorators must not silently rewire an inherited root singleton.

Singleton anchoring is keyed by stable registration ID plus the requested runtime specialization. If an overlay asks for a parent-owned generic singleton specialization that was never compiled in the parent, the build fails with `overlay-singleton`; the overlay must register its own replacement.

Framework/request data should use declared scope slots rather than post-build registration. `configure_fastapi()` declares the FastAPI boundary and `install_fastapi()` uses ASGI middleware to own one ordinary scope for a complete HTTP request or WebSocket connection. It also validates every route's `Resolve(...)` type and filter against the frozen plan at startup.

## Generics and discovery

- Subclass and closed-generic registration discovery rules are queued on a builder and materialized at `build()` from the then-live Python class set.
- Import candidate modules and retain dynamically created class objects until build. Python's subclass registry uses weak references.
- Open generic registrations are templates, not directly resolvable roots. Closed occurrences are specialized when encountered in a compiled dependency path; explicitly register a closed service when it must be a root.
- Generic factory dependencies are specialized from the requested service type and factory annotations. `factory_specialization=` supplies otherwise hidden bindings.
- Unresolved/conflicting `TypeVar` bindings fail build. `ParamSpec` and `TypeVarTuple` are not supported.
- Decorators are immutable builder definitions with stable IDs. Signature parsing, decorated-argument validation, dependency compilation, and generic specialization happen during build.
- Open decorator definitions match actual closed component plans, not the subclass registry. This covers explicit registrations, factories, fallbacks, and discovered subclasses.
- Generated closed generic decorator types are memoized so repeated builds do not leak new classes.
- Higher decorator positions are outside lower positions; equal positions retain declaration order outside-to-inside. Runtime activation retains the inverse core-to-outside order.
- Decorator components own their name and tags. `when=` is the only V2 applicability filter; it sees the completed undecorated core subtree.

Generic work relies on `typetoolbox`. Use the installed `using-typetoolbox` skill before changing binding or subclass-discovery behavior.

## Compiler tooling

`clean_ioc/tooling.py` exposes read-only tooling over the exact compiled component plans:

- `BuildIssue` and `BuildReport` for structured validation;
- `CompiledGraph` with text and Mermaid renderers;
- schema-version-1 `GraphManifest` with deterministic fingerprints;
- `GraphDiff`/`GraphChange` for semantic added, removed, and changed paths.

Manifests use qualified semantic identities rather than UUIDs, occurrence IDs, memory addresses, or configured values. Fixed/default values are represented by type and activation kind so secrets are not serialized. Preserve deterministic ordering and redaction when adding metadata.

`mark_entrypoint(service_type, filter=...)` marks one selected root; marking `list[Service]` marks every filtered member. Marked roots become the default tooling view. Pass `all_roots=True` for the full compiled root set.

`clean_ioc/cli.py` installs the `clean-ioc` command:

- `check module:object [--strict] [--ignore CODE]`;
- `graph module:object --format text|mermaid|json [--all]`;
- `diff module:object baseline.json [--all]`.

A target may be a builder, a built scope/container, or a zero-argument factory returning one. Errors cannot be ignored. `diff` returns `0` for no change and `1` for a semantic change. Baselines are never updated implicitly.

## Public extension guidance

- Reusable bundles should accept the public `ComponentBuilder` protocol so they work with both builder types.
- Apply bundles only during composition. Never give runtime objects mutation APIs.
- Use `clean_ioc.component_filters` for component selection and `clean_ioc.type_filters` for Python type discovery.
- A filter in composition is evaluated and frozen during build. A filter passed to `resolve()` only selects among compiled roots.
- Prefer constructor/factory dependencies. Use `ResolutionContext` only for selection among already-compiled roots, not as an application-wide service locator.
- If a feature changes activation, update both the `_Step` execution and static `Component` metadata.
- If a feature changes ownership, test root container, ordinary child scope, nested scope, built overlay, sync cleanup, and async cleanup.

## Implementation map

- `clean_ioc/v2.py`: builders, compiler, activation steps, runtimes, scopes, caches, ownership, validation, generics, and discovery.
- `clean_ioc/components.py`: immutable component graph and public builder/filter protocols.
- `clean_ioc/tooling.py` and `clean_ioc/cli.py`: diagnostics, rendering, manifests, diffs, and command-line interface.
- `tests/test_v2_container.py`: V2 composition, generics, discovery, runtime, ownership, concurrency, and cleanup.
- `tests/test_compiler_tooling.py`: structured reports, complete graph metadata, entry points, overlays, lifespan validation, manifests, and CLI behavior.
- `benchmarks/bench_clean_ioc.py`: BenchBro build, runtime, tooling, scope, generic factory, and Python-allocation experiments.

`tests/test_complex_dependencies.py` contains several historically difficult combinations of generics, decorators, contextual filtering, collections, and shared registrations. Re-run it when a compiler change affects graph traversal or specialization.

## Verification workflow

Run from the repository root:

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check .
uv run pytest .
uv run python scripts/validate_docs_examples.py
uv run pre-commit run --all-files
uv build
```

Benchmarks use BenchBro 1.0. Confirm discovery before measuring:

```bash
uv run benchbro list --verbose
uv run benchbro run benchmarks/bench_clean_ioc.py --case compiled-build --no-compare \
  --output-json /tmp/clean-ioc-build.json --output-md /tmp/clean-ioc-build.md
uv run benchbro run benchmarks/bench_clean_ioc.py --case compiler-tooling --no-compare \
  --output-json /tmp/clean-ioc-tooling.json --output-md /tmp/clean-ioc-tooling.md
```

Use temporary output paths while shaping experiments. Do not opportunistically replace or commit machine-local `.benchbro` baselines. Consult the installed `use-benchbro` skill before changing benchmark boundaries or interpreting comparisons.

For each V2 feature, the acceptance bar is: build-time invariants remain complete, runtime plans remain immutable, resolution does not reconstruct the dependency graph, ownership is explicit, static tooling describes the actual activation path, and failed composition is diagnosable before user code runs.
