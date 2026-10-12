# 16 — Managed resource providers

Created: 2026-10-04\
Status: Implemented by Sol Medium and independently reviewed by Sol High; APPROVE / KEEP\
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

## Implementation design (2026-10-04)

The compiled handle is `ComponentKind.managed_provider` with deferred activation, provider mode and one target child.
Its runtime step extends the frozen provider step, preserving existing selection, direct target wiring, and singleton
owner anchoring. Manifests add `scope_policy: per_call` only for managed handles: here this denotes a fresh isolated
scope per context entry, not a method proxy. Target scoped ownership remains `scope`; its managed ancestor identifies
that owner as the acquisition. Singleton ownership remains with the declaring parent owner. Existing graph formats
remain unversioned, and existing graphs require no baseline regeneration.

Each call creates a single-use manager without opening a scope. Entry marks the manager used before checking the owner,
then creates an isolated scope (`inherit_scoped=False`) whose provision lookup follows its bound parent. Exit takes and
clears the acquisition scope before closing it, so finalization happens once. The synchronous handle checks the complete
transitive target capability; an async handle supports either plan. No application method proxy or escape check is added.

Failed entry closes the acquisition before re-raising. Cleanup uses existing reverse-order finalizers and exception
aggregation: a cleanup failure propagates with the activation/body exception in `__context__`; multiple cleanup failures
form the existing cleanup exception group. The original application exception is not suppressed. Cancellation uses the
same async cleanup path. Owners are not pinned, and closing a parent does not close the acquisition's independent cache.

Observed acquisition uses the existing request correlation and resolution context, and stops request timing on entry.
The observed acquisition scope records exit cleanup as its own owner operation. Application work between entry and exit
is excluded from DI activation/request timing. Uninstrumented ordinary runtime paths receive no new observer branch.

Baseline: HEAD `58b1db7`, 1,499 tests, repository CI and strict docs passed before implementation (parent verification).
Focused before/after measurements and implementation acceptance results will be recorded below.


### Final collection execution decision

Managed collections activate members sequentially in the frozen registration order. Parallel activation within a
single collection is not a public promise. Sequential initial activation keeps one activation stack and per-resolution
cache, avoids false cycles on repeated transient edges, preserves per-resolution sharing, and prevents a failed or
cancelled entry from racing another member's context-manager entry or finalizer. Separate managers still support fully
concurrent acquisitions. Tests cover cancellation while a later member is entering after an earlier resource has opened,
including awaited finalizers and cleanup-failure chaining. This replaces the experimental concurrent cancel/drain design.

The compiler captures managed variants for nested collections, declared resolution-context requests, and ordinary
provider targets inside an acquisition. Managed resolution contexts reuse already-frozen managed root variants for the
existing unrestricted root-lookup API; no target adaptation or compilation happens at runtime. Ordinary provider handles
created in this context keep their original calling API and bound lifetime. Named collections of provider handles also
preserve their existing supported shape. Acquisition itself performs no root lookup, callbacks, or discovery.

Nearest isolated boundaries determine scope ownership and sharing: a per-call handle inside a managed acquisition owns
its target's scoped resources per method invocation; a managed handle inside a per-call target owns its resources per
context entry. Singleton and supplied identities remain outside these isolated cache groups.

Inherited limitation: boundary-local marked provider entry points remain unsupported, matching ordinary Provider's
existing `boundary-entrypoint-not-local` behavior. Container-level marked managed entry points and exposed boundary target
injection are supported. This item does not expand boundary entry-point declaration syntax.


### Sync cleanup capability proof

Initial activation still uses the transitive step capability. A separate compiler proof traverses ordinary deferred
provider targets for known asynchronous cleanup owned by the acquisition scope. It stops at independent managed and
per-call boundaries, and ignores cleanup owned by parent singletons or supplied values. Consequently resource-free
async provider work and deferred parent-owned singleton resources remain permitted in a sync managed block; known
acquisition-owned asynchronous finalizers require `AsyncManagedProvider`. Injected and marked sync handles reject such
plans during build with `managed-provider-requires-async`. An unmarked synthetic sync root checks its frozen cleanup
capability before any target activation on entry. Both plain and observed plans preserve that capability. Later caller-controlled scope/unrestricted-context lookup
can introduce resources outside the captured graph; use an async managed handle when such operations require async
cleanup. The proof covers initial activation and known acquisition-owned cleanup, not arbitrary future application work.

## Implementation verification evidence (2026-10-04; final review/status owned by parent)

- `tests/test_managed_providers.py`: **80 passed**. Covers lazy entry, isolated warmed/nested/sequential/concurrent
  scopes, same-acquisition sharing for all lifespans, scope provisions and first-child/root/overlay singleton anchoring,
  parent closure and single-use managers, sync/async registration shapes, failed entry/body/cleanup/cancellation,
  transitive captive checks and real cycles, selections/aliases/closed generics/patterns, actual registration and
  decorator template callbacks, pre-configurations, boundary exposure/privacy, frozen runtime wiring and exception chains.
- Tooling cases cover deferred activation, nearest managed/per-call ownership and sharing, direct policy traversal,
  source-linked SARIF, semantic activation changes, build matrices, root explanations, argument categories and selection
  census. Public reports are deterministic and redact build input names/values. Existing graph regression suites pass;
  new metadata is limited to graphs using the new boundary, with no schema version or baseline regeneration.
- Profiling cases count acquisition and cleanup independently using existing correlation, exercise plain and observed
  failure/cancellation/ownership paths, and verify a large simulated application-body duration is excluded from DI timing.
- `make ci`: **passed**, including Ruff lint/format, `ty`, **1,579 tests**, executable public documentation examples and
  BenchBro discovery. The existing FastAPI/Starlette deprecation warning remains unrelated to this feature.
- Supported Python full suites in isolated uv environments: **3.11.13: 1,571 passed / 8 skipped**;
  **3.12.11: 1,576 passed / 3 skipped**; **3.13.5: 1,579 passed**; **3.14.4: 1,579 passed** (main CI).
  Version-specific skips are the existing unsupported-native-syntax cases. Each interpreter used the final runtime
  including the deferred async cleanup capability proof.
- `uv run mkdocs build --strict --site-dir /tmp/clean-ioc-managed-docs`: **passed**. Sync and async snippets in
  `docs/advanced/special-dependency-types.md` execute through `scripts/validate_docs_examples.py`, using only public imports
  and `assert_type` examples for yielded products. Public docs cover owners, exception chaining, block lifetime and escape
  limitations, collection sequencing, known cleanup proof and caller-controlled later lookup.
- [Focused measurements](16-managed-provider-benchmarks.md) record baseline/after ordinary runtime probes against
  `58b1db7` and 12 final managed/observed variants. No tested ordinary path shows material slowdown. Measurements have
  substantial repeat noise; no small speedup, precise latency bound, compilation-cost bound or real-I/O claim is made.

Independent Sol High review was requested by the parent. Reported findings have been repaired with focused regressions:
root explanation/census parity, managed diagnostic wording, sequential collection failure/cancellation and sharing,
managed context/provider root shapes, nearest isolated boundary ownership, and deferred acquisition-owned async cleanup.
The implementation agent has not committed, pushed, released, changed completion status, or started item 17.

## Independent review

A separate `gpt-6.1-sol` agent at high reasoning independently reviewed the complete implementation,
documentation, tests and benchmark artifacts after `gpt-6.1-sol` medium implementation. Final verdict:
**APPROVE / KEEP**, with no unresolved correctness or acceptance findings. The reviewer independently ran all
80 managed tests and verified the repaired lifecycle, sharing, context/provider, explanation/census, ownership
and async cleanup capability cases in plain and observed plans. Documented collection sequencing, boundary entry-point
limits, owner lifetime, caller-controlled lookup and benchmark uncertainty were accepted.
