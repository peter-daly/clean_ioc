# Typed deferred dependencies

Status: Proposal
Priority: P1
Dependencies: Resource ownership proof; compilation provenance for complete explanations
Release gate: Must not ship before resource ownership and runtime-context capture rules are implemented

## Summary

Add `Provider[T]` and `AsyncProvider[T]` as explicit, typed, precompiled deferred edges. Calling a provider executes an
already frozen target plan in the provider's bound scope; it cannot register components, choose an uncompiled type, or
rebuild the graph.

## Problem and differentiation

Applications sometimes need on-demand construction, repeated transient construction, or selection at a later operation.
The current escape hatch is `ResolutionContext`, which can resolve any compiled root and hides the target type from a
constructor signature. Factory classes can model the behavior manually but repeat container plumbing.

A typed deferred edge keeps dynamic timing while preserving static graph visibility. The compiler can validate its target,
async mode, lifespan, scope slots, ownership, and cleanup before returning the runtime.

## Goals

- Declare a deferred target in ordinary constructor or factory annotations.
- Compile the target and selection once, including collections, generics, decorators, and pre-configurations.
- Bind the handle to an explicit scope and reject calls after that scope closes.
- Preserve normal transient, once-per-graph, scoped, and singleton semantics per provider call.
- Represent the deferred relationship in `Component`, manifests, explanations, validation, and ownership reports.

## Non-goals

- Runtime registration, patching, or arbitrary type lookup.
- Assisted factories accepting caller-supplied constructor arguments in the first release.
- A general callable proxy or interception system.
- Automatically selecting between sync and async at call time.
- Replacing explicit framework scope slots for request data.

## User stories

- A batch handler asks for `Provider[UnitOfWork]` and creates one transient unit for each item.
- A synchronous strategy receives a named `Provider[Client]` selected at build time.
- An async worker receives `AsyncProvider[Repository[int]]` with its generic specialization validated before startup.
- Graph tooling shows that an entry point can create a target later, even though it is not activated initially.

## Public API

Export two generic, non-user-constructible handle types from `clean_ioc`:

```python
from clean_ioc import AsyncProvider, Provider, select
import clean_ioc.component_filters as cf


class BatchRunner:
    def __init__(self, unit_of_work: Provider[UnitOfWork]):
        self._unit_of_work = unit_of_work

    def run_one(self, item: Item) -> None:
        unit = self._unit_of_work()
        unit.process(item)


builder.register(
    ClientSelector,
    arguments={"client": select(cf.with_name("primary"))},
)
```

The protocols are:

```python
T_co = TypeVar("T_co", covariant=True)


class Provider(Protocol, Generic[T_co]):
    def __call__(self) -> T_co: ...


class AsyncProvider(Protocol, Generic[T_co]):
    async def __call__(self) -> T_co: ...
```

The runtime injects private frozen implementations. Calling the public protocol class directly is unsupported. Provider
calls accept no positional or keyword arguments. Assisted input is reserved for a separate proposal.

`Provider[T]` and `AsyncProvider[T]` may also be resolved as roots:

```python
provider = scope.resolve(Provider[Report])
report = provider()

async_provider = await scope.resolve_async(AsyncProvider[Report])
report = await async_provider()
```

For an argument annotated as a provider, `arguments={name: select(filter)}` applies the filter to `T`, not to the
synthetic provider component. Plain values, `build_arg`, `generic_arg`, and `derive` are invalid provider-argument
policies because the provider must retain a compiled component target.

`T` may be a closed service type or a supported `list[T]`, `tuple[T, ...]`, or `set[T]` collection request. Open generic
targets and nested providers are rejected.

## Compilation model

The compiler unwraps the provider annotation, selects and compiles the target exactly as a normal edge, and emits a
synthetic provider step containing direct references to the frozen root step or collection steps. It does not perform a
runtime service-type lookup.

Add:

- `ComponentKind.provider` for the synthetic handle;
- `ComponentActivation.deferred` for creation timing;
- one child component representing the complete deferred target plan;
- the graph relationship `provides on demand`;
- metadata identifying sync or async invocation without storing the runtime handle.

The target is part of complete-graph validation, reachability, architecture policies, manifests, fingerprints, and
impact analysis. An entry point with a provider edge therefore keeps the target reachable. Explanations show the
provider selection and rejected candidates.

`Provider[T]` requires every selected target step to support synchronous resolution. Otherwise compilation reports
`provider-requires-async` and recommends `AsyncProvider[T]`. `AsyncProvider[T]` accepts sync or async targets and always
returns an awaitable.

## Runtime and caching semantics

A provider handle captures the `Scope` that resolved the component containing it, or the scope from which the provider
root was resolved. It does not capture `_RuntimeResolutionContext`.

Each call creates a fresh top-level resolution context on that bound scope:

- transient targets activate once per provider call and per dependency edge;
- `once_per_graph` targets are shared only within that one provider call;
- scoped targets use the bound scope's cache;
- singleton targets use their compiled owner token;
- declared scope slots are read from the bound scope and must already be provided;
- cleanup-bearing non-singletons use the owner assigned by the resource-ownership compiler.

Concurrent provider calls use the existing scoped and singleton coordinators. Separate calls do not share
`once_per_graph` values. Provider handles contain no mutable candidate or plan cache.

Calling a provider after its bound scope is closed raises `ProviderScopeClosedError`, a `ScopeClosedError` subclass. A
provider does not keep a scope alive, close it, or transfer ownership to another scope.

## Lifespan and ownership rules

The provider handle is owned by the component that captures it; the target remains a deferred edge. Static captive
validation follows these rules:

- transient, once-per-graph, and scoped components may capture a provider bound to their current scope;
- a singleton may use a provider only when the target graph contains no scoped component, scope slot, `Scope`, or
  `ResolutionContext` edge;
- a provider may target cleanup-bearing transient components only after resource-ownership compilation assigns their
  finalizers to the bound scope or singleton owner safely;
- a provider returned from a scope may escape in user code, but all later calls fail after that scope closes;
- an inherited parent singleton's provider remains bound to its original owner scope and frozen parent target plan;
- an overlay singleton's provider may reference only plans valid in that compiled overlay and remains owned by the
  overlay scope.

Violations report the complete parent-provider-target semantic path. A deferred edge does not weaken ordinary captive
checks inside the target graph.

## Errors and failure modes

- `provider-invalid-target`: missing type argument, open generic, nested provider, or unsupported provider collection.
- `provider-missing-component`: no compiled target satisfies the request.
- `provider-ambiguous-component`: target selection is ambiguous.
- `provider-requires-async`: a synchronous provider targets any async-required step.
- `provider-invalid-argument-policy`: a value-producing policy is applied to a provider argument.
- `provider-captive-scope`: a singleton-held provider reaches scoped state, a scope slot, or runtime scope access.
- `provider-unsafe-cleanup`: ownership cannot prove safe cleanup for the deferred target.
- `ProviderScopeClosedError`: a `ScopeClosedError` subclass raised when a handle is invoked after its bound scope closes.

Build errors use `ContainerBuildError` and aggregate with independent root failures. Runtime target activation failures
propagate unchanged and retain the existing retry behavior for scoped and singleton coordination.

## Privacy and serialization

Manifests describe the provider kind, sync/async mode, target type, selection metadata, and target graph. They never
serialize the handle, scope identity, callable filters, or runtime values. Provider targets affect fingerprints because
they change executable architecture.

## Compatibility

This is additive. Existing `ResolutionContext` remains available for genuinely open selection among compiled roots, but
documentation recommends a typed provider whenever the target type is known. Builder and runtime mutation remain
forbidden.

## Rejected alternatives

- **Inject `Callable[[], T]`:** arbitrary callables are ambiguous and lose explicit graph semantics.
- **Let providers call `scope.resolve(T)`:** a stored type lookup would repeat selection and weaken the compiled-step model.
- **Capture `ResolutionContext`:** that context is valid for one top-level resolve and must not escape it.
- **Accept runtime constructor arguments:** assisted injection needs a separate placeholder and ownership design.
- **Choose sync versus async on first call:** async capability is already known at build time.

## Rollout

1. Complete resource-ownership and runtime-context capture enforcement.
2. Add synchronous provider compilation, graph metadata, and root resolution.
3. Add async providers and collection targets.
4. Add explanations, manifests, policies, overlays, and framework examples.

## Acceptance tests

- Inject and root-resolve providers for transient, once-per-graph, scoped, singleton, collection, decorated, and closed
  generic targets.
- Verify repeated calls create fresh resolution contexts while scoped/singleton caches and coordinators remain correct.
- Compile named and custom-filter selection once and prove provider calls do not reevaluate filters.
- Reject missing, ambiguous, open-generic, nested, incorrectly configured, and async-in-sync targets.
- Validate complete captive and cleanup paths, including singleton, overlay singleton, inherited singleton, and scope slots.
- Raise after bound-scope closure and never retain or close a scope implicitly.
- Test concurrent sync calls, concurrent async calls, activation failure, retry, cancellation, and finalization order.
- Show provider nodes and deferred targets consistently in text, Mermaid, manifests, fingerprints, explanations, and diffs.
- Prove runtime calls allocate activation state and instances only; they do not construct component graphs or perform
  service-type candidate scans.
