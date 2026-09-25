# 03 — Entry-point activation analysis

Status: Implemented in working tree; Sol review thread requested but not readable  
Priority: P0  
Dependencies: 01; 02 for cache scenarios  
Enables: 06 capability paths; 07 consequences; 08 trace comparison

Implementation notes:

- Added `ActivationReport`, `ActivationObligation`, and `ExecutionRelationship` in `clean_ioc.graph_analysis`.
- Added `CompiledGraph.activation_report()` and `clean-ioc activation` with `cold`, `warm_singletons`, and
  `warm_scope` scenarios plus text, JSON, and Mermaid output.
- Immediate obligation traversal stops at typed-provider handles; provider targets are reported in the deferred phase.
- Reports include scope-slot requirements, local async causes, pre-configuration work, cleanup ownership notes, runtime
  context unknown-work markers, scenario assumptions, and modeled cache-hit skips.
- Verification run: `uv run python -m ruff check clean_ioc tests/test_compiler_tooling.py`; `uv run pytest -q`
  (458 passed, 1 upstream FastAPI/Starlette warning).

## Outcome

Summarize what resolving a root requires, what can be constructed eagerly, what is deferred, why async resolution is
needed, and which owner cleans up each acquired resource. Offer explicit hypothetical cache scenarios without running
the application or pretending to know actual cache state.

```text
Checkout
  Required scope slot: RequestContext
  Eager: Checkout → Repository → Database
  Deferred: Provider[ReceiptSender] → ReceiptSender
  Async cause: Repository → open_database
  Resource owners: request scope / root container
```

## Current foundation

`_Step.sync_supported` already carries transitive sync capability; `Component.requires_async` describes local
activation metadata and must not be mistaken for the whole plan's capability. Providers defer target activation;
collections, decorators, and pre-configurations have specific execution order. Ownership is already compiled.

Primary integration points: `_Step` families, `_CompiledPreConfiguration`, `_CompiledDecorator`, `_PlanSet`,
`_finalize_plan()`, `graph_analysis.py`, `tooling.py`, and sync/async/provider/ownership tests.

## Proposed model and API

- `ActivationReport`: selected root, scenario assumptions, immediate obligations, deferred obligations, async cause
  paths, potential acquisitions, execution relationships, cleanup owners, and unknown runtime work.
- `ActivationScenario`: `cold`, `warm_singletons`, or `warm_scope`. These are named assumptions, not snapshots.
- `ActivationObligation`: scope slot, sync/async requirement, initializer, or resource, with a witness path and eager
  versus deferred phase.
- `ExecutionRelationship`: ordered or potentially concurrent relationships; do not flatten everything into a sequence.

Proposed method: `graph.activation_report(component, scenario="cold")`. Type/name selection must resolve one compiled
root or explicitly request a collection. Add `clean-ioc activation TARGET SERVICE --scenario cold --format text|json`.

## Implementation stages

### 1. Preserve executable semantics for analysis

- [ ] Capture a frozen analysis projection of step relationships during finalisation. Share 01/02 references rather
  than rediscovering activation by inspecting user callables or mutating steps.
- [ ] Record transitive sync capability, initializer-before-core relationships, core-before-decorator relationships,
  and collection member ordering/concurrency as the executor actually implements them.
- [ ] Handle declared resolution requests explicitly. Unrestricted runtime resolution remains an unknown-work marker.
- [ ] Distinguish supplied instances and fixed values from construction operations.

### 2. Calculate obligations and paths

- [ ] Walk eager edges to find slot requirements and all causes of async-only activation, including decorator and
  pre-configuration paths. Reuse bounded path reporting from 01.
- [ ] Stop immediate-obligation propagation at providers; report target obligations under a separate deferred phase.
  Acquiring an async provider is synchronous even though invoking its target may require async.
- [ ] Include every provider-map target as a potential deferred branch without claiming all targets will be invoked.
- [ ] Report pre-configurations as possible first-use work with shared definition identity and declaring owner.
- [ ] Show cache owner and cleanup owner separately, including promoted transient cleanup under a singleton.

### 3. Add scenario analysis

- [ ] Cold assumes empty relevant caches, no completed initializers, and no inherited scoped values.
- [ ] Warm singletons assumes relevant singleton caches and shared initializers are complete; scoped/per-resolution
  caches remain cold. Warm scope additionally assumes relevant scoped caches are populated. State these assumptions.
- [ ] A cache hit skips the cached step's activation subtree. A per-resolution group activates at most once within
  that context; deferred provider calls have separate contexts and no assumed invocation count.
- [ ] Maintain required sync API constraints even when a hypothetical warm cache would skip async construction; runtime
  root capability checks still govern which public resolve method is valid.
- [ ] Report construction counts only where the modeled executor and scenario determine them. Otherwise provide bounds
  or `unknown`. Never count hidden work inside a user factory as compiler-known work.
- [ ] Resource teardown is reverse actual acquisition within an owner. Show partial-order constraints and owner
  boundaries, not a universally fixed finalizer sequence when concurrent acquisition can vary.

### 4. Rendering and documentation

- [ ] Add readable summaries and a Mermaid projection with eager/deferred edges and async cause paths distinguished.
- [ ] Explain required slots versus already-provided runtime values; this static API does not inspect provision state.
- [ ] Document scope inheritance, cold versus warm first-request behaviour, lazy providers, and limitations around
  constructors/factories that perform undeclared work.

## Verification

Cover async-only leaf, async decorator, async initializer, async provider acquisition versus invocation, provider maps,
collections, shared per-resolution diamonds, supplied instances, required/named slots, and hidden dynamic resolution.
Verify scenarios against event-recording fixtures in isolated executions: compare predicted eager operations with
observed operations for the controlled fixture, without treating this as proof for arbitrary user code.

Test scoped inheritance assumptions, overlays with anchored singleton plans, transient resource promotion, and
concurrent collection activation. Assert no eager slot/async propagation across a provider boundary. Exported reports
must contain no slot values, configured values, build-input names, or owner tokens.

## Acceptance criteria

- A developer can trace every reported immediate async/slot requirement to a concrete compiled path.
- Eager/deferred operations and cache-scenario assumptions remain explicit in all formats.
- No misleading exact sequence or count is produced when runtime behaviour is not determined by the plan.
- Analysis performs no application activation and adds no work to normal resolution or scope creation.
