# 16 — Managed resource providers

Created: 2026-10-04\
Status: Planned; implementation not started\
Priority: P1\
Baseline: Clean IoC 2.0.0b29 on `version2`\
Dependencies: Existing typed providers, resource ownership proof, and isolated per-call scope machinery\
Related work: [Per-call scopes](09-per-call-scopes.md), [runtime profiling](12-runtime-resolution-profiler.md),
[typed deferred dependencies](../.v2_roadmap/05-typed-deferred-dependencies.md), and
[resource ownership proof](../.v2_roadmap/06-resource-ownership-proof.md)

## Outcome

Let an application component acquire a precompiled dependency inside an explicit `with` or `async with` block.
Each acquisition owns a fresh isolated scope, so scoped resources and their dependencies are released when the block
ends. The consumer controls the operation boundary without receiving a container or building an overlay.

Ordinary `Provider[T]` activates its target in its bound scope; its resources remain owned by that scope.
`ManagedProvider[T]` would activate the same kind of frozen target plan inside a separate acquisition scope and return
the target through a context manager. This feature controls dependency lifetime, not application method invocation.

All APIs and examples in this document are proposed until implementation lands.

## Proposed public API

Add and export two typed protocols from `clean_ioc.providers` and `clean_ioc`:

```python
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Protocol, TypeVar

T_co = TypeVar("T_co", covariant=True)


class ManagedProvider(Protocol[T_co]):
    def __call__(self) -> AbstractContextManager[T_co]: ...


class AsyncManagedProvider(Protocol[T_co]):
    def __call__(self) -> AbstractAsyncContextManager[T_co]: ...
```

The async protocol's `__call__` is synchronous: it creates an async context manager. Acquisition happens in
`__aenter__`, so usage is `async with provider()` without `await provider()`.

Like existing providers, these handles take no arguments. Targets use the existing closed service and supported
collection shapes (`list[T]`, `tuple[T, ...]`, and `set[T]`). Support constructor, ordinary factory, generator,
context-manager, async factory, and async resource registrations; a cleanup-bearing target is not mandatory.

Injection requires no new registration option. Register the target normally and request the managed provider type:

```python
from collections.abc import Iterator
from contextlib import contextmanager

from clean_ioc import ContainerBuilder, ManagedProvider


@contextmanager
def create_session(config: DatabaseConfig) -> Iterator[DatabaseSession]:
    session = DatabaseSession.connect(config.url)
    try:
        yield session
    finally:
        session.close()


class ReportRunner:
    def __init__(self, sessions: ManagedProvider[DatabaseSession]):
        self.sessions = sessions

    def run(self, report_id: int) -> Report:
        with self.sessions() as session:
            return session.load_report(report_id)  # Return materialized application data.


builder = ContainerBuilder()
builder.register(DatabaseConfig, instance=config)
builder.register(DatabaseSession, factory=create_session, lifespan="scoped")
builder.register(ReportRunner)
```

For asynchronous targets:

```python
class AsyncReportRunner:
    def __init__(self, sessions: AsyncManagedProvider[DatabaseSession]):
        self.sessions = sessions

    async def run(self, report_id: int) -> Report:
        async with self.sessions() as session:
            return await session.load_report(report_id)
```

Support root resolution of both handle types and marked provider entry points. `select(...)` applies to the target
with the same build-time candidate filtering and ambiguity rules as ordinary typed providers. Generic specialization,
aliases, registration patterns, fallback selection, names, tags, boundaries, decorators, and pre-configurations retain
their normal composition semantics. Do not introduce a runtime target lookup or implicit discovery.

## Acquisition and ownership contract

1. Building, resolving a handle, and calling the handle do not activate application components or open a scope.
   Each call returns a new single-use context manager. Only entering that manager creates its scope and activates
   the target. A manager that is never entered acquires no resources.
2. Each entry gets a fresh isolated scoped cache, including when the parent has already activated scoped services.
   Reuse the isolated scope behavior behind `scope="per_call"`; ordinary `new_scope()` inheritance stays unchanged.
   Scoped dependencies share within one acquisition and differ across sequential, nested, and concurrent acquisitions.
3. Registration lifespans remain meaningful. Scoped values belong to the acquisition; per-resolution values share
   within its initial resolve; transients retain their ordinary behavior. Singleton instances and their owners remain
   shared. A managed acquisition of a singleton does not make it fresh or finalize it at context exit.
4. Inherit declared scope provisions from the bound scope under existing provision/locking rules, without inheriting
   its scoped cache. There are no call-time arguments, provision overrides, or injectable acquisition-manager controls
   in this item. Application code provides slot values on its enclosing scope before resolving the consumer.
5. Bind a retained handle to its actual owner and frozen composition. A root singleton consumer anchors to the root
   owner's plan, even when first resolved from a child or overlay; it must not capture that first request's values.
   An overlay-owned singleton anchors to its overlay owner. Other handles follow their resolving scope.
6. A singleton consumer may retain a managed handle whose target uses acquisition-scoped resources. The isolated
   boundary removes only the outer retention constraint. Normal captive-lifespan, runtime-context, slot, and cycle
   checks still apply inside the target graph. Do not grant ordinary providers a broader lifetime exemption.
7. A root-bound handle inherits root provisions, not whichever child happens to call it. Missing supplied slot values
   remain runtime provision failures; declared slot types remain statically validated. Acquisition must clean up any
   resources created before a provision or activation failure.
8. Exit closes the acquisition scope exactly once, attempts its finalizers in reverse acquisition order, and retains
   the existing cleanup exception aggregation. Do not close or finalize parent-owned singletons. Acquisition failure,
   body failure, and async cancellation must all run applicable scope cleanup.
9. Preserve body/activation exceptions when cleanup also fails, through the existing exception chain or group;
   document and test the precise behavior. Do not suppress application exceptions or wrap successful values.
10. The handle is reusable; an individual returned manager is not reusable or reentrant. Separate managers may be
    nested or used concurrently. Closing one acquisition must not close another's resources.
11. Closed bound owners reject new acquisition with `ProviderScopeClosedError`, including an owner that closes
    between manager creation and entry. Acquisitions do not extend the parent's lifetime: callers must keep the bound
    owner and shared singleton owners open for the block. Exit still cleans its own scope if the parent has closed;
    this item does not add owner pinning or change ordinary parent/child close semantics.
12. The target is valid for the block's lifetime. Arbitrary returned objects, closures, and resource-backed lazy
    results cannot be proven safe after exit. Document this explicitly; no automatic method proxy or general escape
    detector is part of this feature. A singleton target retains its ordinary longer lifetime.

## Compiler and graph representation

Compile a dedicated managed-provider step holding the selected target step and binding owner. Runtime entry executes
that direct plan in the isolated scope. No `ScopeBuilder`, candidate selection, filter evaluation, template callback,
registration, or compilation occurs per acquisition.

Represent the handle as a distinct deferred boundary in the public graph, proposed as
`ComponentKind.managed_provider` with `ComponentActivation.deferred`, the sync/async provider mode, and a target child.
Record enough frozen ownership metadata to distinguish acquisition-owned scoped resources from parent singleton owners.
Confirm the precise fields against existing per-call and provider representations before implementation.

Selection explanations, ownership reports, activation analysis, sharing groups, reverse dependencies, policy traversal,
manifests, semantic diffs, SARIF paths, and build matrices must understand the new boundary. They must not report its
target as eagerly activated or treat acquisition-scoped instances as globally shared. Direct dependency policies should
traverse this synthetic bridge like existing providers and per-call handles.

`ManagedProvider[T]` requires a wholly synchronous activation and cleanup plan; report an incompatible target during
build using proposed code `managed-provider-requires-async`. `AsyncManagedProvider[T]` supports sync and async plans.
Use existing provider target and selection diagnostics when their meaning agrees; preserve existing provider codes and
behavior. Finalize any additional new stable codes in the first implementation stage.

Metadata changes describing this new lifetime boundary may affect manifests/fingerprints for graphs using it.
Existing graphs must retain their output. Preserve unversioned beta formats and document baseline regeneration where
needed. Do not serialize provision values, build-input keys/values/hashes, runtime scope IDs, owners, or callback state.

Integrate with the existing opt-in runtime profiler: count acquisition resolution and target activation/cache outcomes,
then cleanup as a separate owner operation. Application work inside the block is not factory or DI activation time.
Reuse current correlation identities; do not introduce a second observation model or require detailed tracing.

## Scope and non-goals

This item delivers the typed handles, context managers, compiled lifetime boundary, ownership proof, tooling integration,
tests, documentation, and performance evidence. It does not implement assisted runtime arguments, multiple factory
outputs, resource pooling, warm-up plans, or managed-provider map declarations. The two factory proposals remain in the
[maybe pile](../.v2_roadmap/README.md#maybe-pile).

No ASGI/FastAPI integration, workflow, release, or external application change is required. Ordinary providers and
per-call method scopes retain their public APIs and behavior.

## Repository map

- `clean_ioc/providers.py`, `__init__.py`: proposed protocols and exports.
- `clean_ioc/container.py`: request normalization, target selection, ownership frames, direct activation steps,
  isolated scopes, owner binding, cleanup, observed variants, and overlays.
- `clean_ioc/components.py`, `tooling.py`, `graph_analysis.py`, `semantic_diff.py`, `policies.py`: deferred-boundary
  metadata and consistent traversal, reporting, sharing, and comparison.
- `clean_ioc/type_aliases.py`: normalization of the new generic handle forms where required.
- `tests/test_managed_providers.py` (proposed): focused behavior; extend existing ownership, provider, per-call,
  profiling, graph, policy, and matrix regression suites where their existing fixtures cover the integration.
- `docs/advanced/special-dependency-types.md`, `docs/scopes.md`, `docs/lifespans.md`, `docs/runtime-profiling.md`,
  executable documentation validation, `README.md`, `V2_DEVELOPMENT.md`, and `CHANGES.rst`: supported usage and semantics.

## Implementation stages

1. Confirm the frozen graph/ownership representation and exact manager state and exception behavior against the
   existing runtime. Record those decisions before editing compiler behavior. Capture ordinary-provider and per-call
   regression/performance baselines.
2. Add protocol exports and closed-target normalization, target filtering, root requests, build diagnostics, and
   sync/async capability checks, with no application activation during build or handle acquisition.
3. Implement separate sync/async single-use managers executing captured target steps in isolated scopes. Cover parent
   anchoring, slot inheritance, cleanup on failed entry, exceptions, cancellation, and independent acquisitions.
4. Complete ownership, boundary/overlay, decorator/generic, graph-analysis, policy, SARIF, semantic-diff, and profiler
   integration. Keep ordinary runtime paths unchanged.
5. Add behavioral tests and executable public documentation examples. Run repository CI, strict docs, supported-Python
   checks, and focused lifecycle/performance measurements. Record results and limits.
6. Obtain the independent review required by the work-list workflow, resolve findings, and update work-item/roadmap
   status only when the complete feature is verified. Creating this work item does not start implementation.

## Acceptance evidence

- Sync and async examples use only supported public imports after implementation and infer the yielded product type.
- Build, graph validation, handle resolution, and unentered manager creation cause no application activation/cleanup.
- Scope entry uses the frozen plan; no callbacks, discovery, or compilation are replayed at runtime.
- Pre-warmed parent scoped resources are isolated; repeated edges share inside one acquisition; sequential, nested,
  and concurrent acquisitions have distinct scoped resources and independent cleanup.
- Singleton reuse and cleanup ownership remain correct, including a root singleton consumer first resolved from a
  short-lived child, inherited root singletons in overlays, and overlay-owned singleton consumers.
- Declared provisions inherit from the correct bound scope without leaking the first caller's request values.
- Named selection, roots/entry points, collections, aliases, closed generics/patterns, fallbacks, boundaries,
  decorators/templates, pre-configurations, and the factory-return build rule preserve their intended behavior.
- A sync handle cannot target async activation or cleanup; an async handle can acquire either kind of plan.
- Acquisition/body failure, cancellation, multiple cleanup failures, manager reuse, closed-owner entry, and parent
  closure before exit have deterministic tested ownership and exception behavior.
- Captive dependencies and real cycles inside the target still fail; only the managed acquisition edge changes the
  enclosing retention proof. Ordinary provider lifetime restrictions remain enforced.
- Ownership/activation/sharing reports, policy checks, semantic diffs, matrix findings, and SARIF describe the deferred
  scope boundary and remain deterministic and redacted. No public manifest contains runtime resources or input values.
- Enabled profiling counts acquisition and cleanup correctly without measuring application work as DI activation.
- Existing uninstrumented resolution, ordinary providers, ordinary scope creation, and per-call paths gain no managed
  feature branches or work. Measure handle acquisition, fresh scope activation/cleanup, cached singleton targets,
  sync/async resources, and observed variants with appropriate existing benchmark tooling.

## Definition of done

Implementation and independent review are complete; acceptance evidence, CI, supported-Python checks, docs examples,
strict documentation build, and focused measurements are recorded. Public APIs, compiler metadata, runtime ownership,
diagnostics, and tooling agree. This item remains planned until those conditions are met.
