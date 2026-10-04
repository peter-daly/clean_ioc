# 17 — Declared warm-up plans

Created: 2026-10-04\
Status: Planned; implementation not started\
Priority: P1\
Baseline: Clean IoC 2.0.0b29 on `version2`\
Dependencies: Existing frozen root/activation plans, singleton ownership, and structured diagnostics\
Related work: [Entry-point activation analysis](03-entrypoint-activation-analysis.md),
[runtime profiling](12-runtime-resolution-profiler.md),
[resource ownership proof](../.v2_roadmap/06-resource-ownership-proof.md), and
[build matrices](../.v2_roadmap/04-build-variant-matrix-checking.md)

## Outcome

Declare which singleton services an application wants initialized before accepting traffic. Compilation selects and
validates those targets without constructing them. After build, application startup explicitly runs a named warm-up
plan, activates its frozen targets, and receives an aggregated report of initialization successes and failures.

This makes startup activation deliberate and reviewable while preserving lazy activation everywhere else.
An ordinary `resolve()` already initializes a singleton; the feature packages selected startup requests into a named,
compiled plan with reporting and failure aggregation. It does not prove service health or invoke application methods.

All APIs and examples below are proposed until implementation lands. Creating this work item does not start implementation.

## Proposed public API

Add immutable `WarmupTarget` and `WarmupPlan` declarations, plus `WarmupReport` and `WarmupError`, in a proposed
`clean_ioc.warmup` module with public root exports. Names and exact signatures must be finalized before implementation.

```python
import clean_ioc.component_filters as cf
from clean_ioc import ContainerBuilder, WarmupPlan, WarmupTarget

builder = ContainerBuilder()
builder.register(DatabasePool, factory=create_pool, lifespan="singleton")
builder.register(CacheClient, factory=create_cache, lifespan="singleton", name="primary")

builder.add_warmup_plan(
    WarmupPlan(
        "startup",
        targets=[
            WarmupTarget(DatabasePool),
            WarmupTarget(CacheClient, filter=cf.with_name("primary")),
        ],
    )
)

# Build compiles and validates declarations; it opens no application resources.
with builder.build() as container:
    report = container.warmup("startup")
    report.raise_for_errors()
    serve_application(container)
```

The async runtime method awaits activation directly:

```python
async with builder.build() as container:
    report = await container.warmup_async("startup")
    report.raise_for_errors()
    await serve_application_async(container)
```

`WarmupTarget` captures a closed service key and an optional synchronous component filter. Its default filter uses
the normal unnamed-root selection convention. A target must identify exactly one visible resolvable singleton
registration; explicit named or ID filters can select among several registrations. Reject empty or ambiguous selections
during build instead of choosing an arbitrary startup target. Normalize aliases and specialize closed generic requests
through the existing compiler.

`WarmupPlan` requires a nonempty unique name and captures the target iterable into an immutable ordered tuple.
The initial builder API is on `ContainerBuilder` and `ScopeBuilder`; ordinary runtime scopes reuse compiled declarations.
Do not introduce post-build declaration or modification. Duplicate plan names across visible declaration layers are
rejected in the initial design; a replacement/editing API is outside this item.

There is no automatic run-on-build option. The application chooses when to run one named plan; unknown plan names and
closed scopes fail clearly before activation. Do not implicitly execute every declared plan.

## Declaration and compilation contract

1. Resolve and validate all target requests during build, including type aliases, generic specialization, filters,
   fallback selection, boundary visibility, decorators, pre-configurations, factory return annotations, and ownership.
   Capture direct executable target steps. Runtime warm-up never recompiles or reevaluates selection callbacks.
2. Limit initial top-level targets to resolvable singleton services. Scoped, per-resolution, transient, collection,
   scope-slot, provider-handle, managed-provider-handle, and per-call-handle requests are not warm-up targets. Their
   semantics do not establish one persistent startup instance. Applications can declare individual singleton targets
   explicitly instead of warming a provider map or invoking a managed acquisition.
3. Keep the target's ordinary dependencies and cleanup semantics. A singleton may depend on ordinary transient
   resources with promoted ownership when already permitted by the compiler. Existing captive dependencies and
   runtime-context restrictions remain hard failures.
4. Closed generic warm-up requests count as explicit compilation demand, so the compiler can materialize the requested
   specialization even if no consumer currently requests it. Declarations do not create entry-point markers, change
   default graph focus, or expose private boundary services.
5. A `dependency_only` registration cannot be selected as a direct warm-up target. Warm a resolvable singleton that
   depends on it when startup initialization is required; preserve the existing root-policy contract.
6. `ScopeBuilder` inherits declarations and compiles their selections against the overlay's visible composition.
   An inherited parent singleton stays anchored to its parent plan and owner; an overlay override uses its overlay
   singleton owner. Ordinary child scopes reuse frozen selections and do not compile another warm-up plan.
7. Named plans are independent declarations. Reject repeated requests selecting the same compiled target within one
   plan with a stable diagnostic rather than introducing duplicate report entries. Targets shared across distinct
   plans remain legal and use the normal singleton cache/coordinator.
8. Missing/ambiguous selections, duplicate names/targets, invalid keys/filters, and non-singleton targets produce
   structured build diagnostics with the declaration source and target request. Failed builders remain repairable.
9. A plan records whether any target needs async activation or cleanup, using the whole frozen step capability rather
   than only a component's local `requires_async` flag. Declaring an async target is valid; runtime callers select the
   async API. A sync run preflights the complete plan and activates nothing if an async-only target makes it invalid.

## Runtime execution and failure contract

- Execute top-level targets sequentially in declaration order in the calling runtime's normal resolution context
  boundary, with a fresh top-level context per request. Underlying steps retain their existing dependency concurrency,
  pre-configuration ordering, caching, and cleanup. The declaration list is not a new global construction-order guarantee.
- Request the captured target step directly. Do not build a temporary overlay, activate all graph nodes, traverse
  deferred providers, or invoke application health-check/service methods. A factory's own declared startup behavior
  remains application code; hidden work inside it is not compiler-proven.
- Continue to later targets after ordinary `Exception` failures and record each result. A shared failing dependency
  may be retried by a later target under the existing initialization/coordinator rules; report the real outcomes rather
  than fabricating a dependent-target skip. Do not automatically retry an individual target beyond that normal behavior.
- Successful singletons remain cached under their existing owners. Repeated runs request them normally and do not
  reactivate successful cached factories. Failed initializations may retry on a later explicit run. Concurrent runs and
  ordinary resolutions must use the same singleton coordinator without duplicate successful initialization.
- An invalid warm-up report does not close the container or roll back successful resources. A failed initializer's
  already-acquired dependencies retain their existing cleanup owners. The application decides whether to continue,
  retry, or abort startup. In the examples, `raise_for_errors()` escapes the owning `with`/`async with` and normal owner
  shutdown closes all acquired resources. Do not introduce transactional startup or a second finalizer registry.
- Cancellation, `KeyboardInterrupt`, and other `BaseException` control signals stop the run and propagate; do not
  turn them into an ordinary finding and continue startup. Preserve existing activation-context completion and resource
  ownership on cancellation. Cleanup occurs under the application's enclosing ownership boundary.
- Closing the runtime rejects new runs. Warm-up does not pin owners or extend singleton lifetime; callers keep the
  relevant owners open for the run and application usage. Preserve ordinary scope/owner close behavior.
- A succeeded target means its requested initialization completed. It does not prove external connectivity,
  application readiness, completed deferred acquisitions, or health of a returned lazily connecting client.

Initial runtime execution is sequential. Parallel warm-up, target dependency scheduling, retry/backoff, timeout policy,
and fail-fast modes are follow-up decisions, not initial requirements. Existing internal dependency execution remains unchanged.

## Reports and diagnostics

`WarmupReport` is an immutable runtime observation with `.is_valid`, `.to_text()`, `.to_json()`, and `.to_sarif()`.
It identifies the named plan, matching full graph fingerprint, and declared target order. Each attempted target has its
safe service/implementation identity, semantic component path, succeeded/failed status, and qualified exception type
when failed. Sync preflight failures report targets as not executed; they must not appear initialized.

Do not label a successful target "already warm" or claim activation/cache counts unless actual runtime evidence
supports that distinction. Any durations are observed elapsed durations with clear coverage, not static estimates;
they never enter structural fingerprints. Rendering the same captured report is deterministic.

`WarmupReport.raise_for_errors()` raises a proposed `WarmupError` containing the safe report when failures remain.
Provide `.assert_valid()` for tests using the existing SARIF assertion convention. These helpers do not run warm-up,
repeat validation, retry targets, or close owners. Warm-up findings remain separate from `BuildReport`: constructors can
fail at startup even when the static graph passed all build rules.

Use source-linked target/declaration locations where available. Record a nested dependency witness only when actual
captured execution evidence identifies it; do not infer the throw site from the entire possible dependency graph.
Exception messages, tracebacks, exception objects, callback representations, instantiated resources, configuration,
provision values, build-input keys/values/hashes, runtime IDs, and owner tokens stay out of the retained/exported report.
Use fixed failure messages plus a safe qualified exception-type label. Do not invoke arbitrary `str()` or `repr()`.

Proposed codes include `warmup-invalid-target`, `warmup-missing-component`, `warmup-ambiguous-component`,
`warmup-non-singleton-target`, `warmup-duplicate-plan`, `warmup-duplicate-target`, `warmup-requires-async`, and
`warmup-activation-failed`. Finalize code placement, source capture, preflight findings, and invalid runtime name behavior
in the first design stage. Reuse existing structural diagnostics where they already describe the failure accurately.

## Graph, tooling, and profiling

Capture declarations and selected target references in frozen plan metadata. Expose a read-only inspection of named
warm-up plans and selected paths so reviewers can see intended startup activation without running it.

Warm-up intent is an application declaration; outcomes are runtime observations. Default graph manifests/fingerprints
remain unchanged when only warm-up intent changes and the compiled graph stays the same. An explicit closed request
that adds a specialization may legitimately change the graph. Keep intent in a separate inspection/export projection,
using existing graph identities rather than adding configuration values to manifests.

`build()`, `validation_report()`, `clean-ioc check`, `clean-ioc activation`, graph export, semantic diff, and `BuildMatrix`
must not execute warm-up. Existing activation reports remain hypothetical cache-scenario analyses; declaring a plan or
choosing `warm_singletons` does not prove any real cache is populated.

The opt-in runtime profiler should observe the actual target resolutions, factory/decorator/pre-configuration work,
cache hits/waits, and eventual owner cleanup using existing identities and counters. Add no warm-up branch, callback,
plan scan, or instrumentation work to ordinary uninstrumented `resolve()` or provider calls.

## Scope and repository map

This item delivers declarations, compilation, explicit sync/async execution, safe startup reports, graph inspection,
tests, documentation, and verification. It does not deliver health checks, readiness state management, automatic
framework startup hooks, CLI activation of application resources, background scheduling, automatic retries, or managed
resource providers. Item 16 and detailed tracing are not prerequisites.

- `clean_ioc/warmup.py` (proposed), `__init__.py`: declarations, safe report/error models, exports.
- `clean_ioc/container.py`, `components.py`: builder/protocol signatures where needed, immutable declaration layers,
  closed target demand, frozen selected steps, scope/container methods, and owner-aware activation.
- `clean_ioc/tooling.py`, `sarif.py`, `graph_analysis.py`: source/path capture, declared-plan inspection, report export,
  and honest separation from static activation scenarios.
- `clean_ioc/instrumentation.py`: use existing observed resolution/cleanup paths where needed.
- `tests/test_warmup_plans.py` (proposed): behavioral tests plus focused extensions to existing scope, profiling,
  compiler, matrix, and SARIF regression suites.
- Proposed `docs/warmup-plans.md`, executable docs validation, `mkdocs.yml`, `README.md`, `V2_DEVELOPMENT.md`, and
  `CHANGES.rst`: user-facing lifecycle guidance and public examples.

## Implementation stages

1. Confirm declaration shapes, root-policy handling, source capture, inspection format, direct step execution,
   sync preflight, safe error retention, and cancellation behavior before changing the compiler. Record compatibility
   and performance baselines for ordinary singleton resolution.
2. Add immutable declarations and builder validation, closed-request materialization, unique target selection,
   inheritance/overlay handling, and frozen target references without activation during build.
3. Implement ordered sync/async runs, ordinary failure aggregation, normal cache/coordinator reuse, cancellation
   propagation, and report helpers. Preserve existing singleton ownership and cleanup behavior.
4. Integrate source-linked diagnostics/SARIF, declared-plan inspection, static-tooling non-activation, and existing
   runtime profiling. Verify redaction and no additional work on normal runtime paths.
5. Add executable examples and behavioral tests. Run CI, strict docs, supported-Python checks, and focused lifecycle
   and performance measurements; record results and limitations.
6. Obtain independent review under the work-list workflow, resolve findings, and mark complete only after the entire
   public/compiler/runtime/reporting contract is verified.

## Acceptance evidence

- Declaration capture is immutable; invalid names/targets/filters, duplicates, missing/ambiguous selections, root
  policy violations, and non-singleton targets fail clearly before application resources are activated.
- Build, static tooling, explicit validation, and build matrices perform zero warm-up activations. Calling a named
  warm-up method is the only new activation trigger.
- Target order is preserved; independent ordinary failures aggregate; a later successful target still initializes.
  Sync preflight activates nothing when the plan requires async; async runs accept sync and async targets.
- First successful activation caches normally; repeated/concurrent warm-up and ordinary resolution initialize each
  singleton successfully once under normal cache/coordinator behavior. Failed targets follow normal retry behavior.
- Successful resources survive the report until their owner closes. Failure reporting does not add rollback or close
  unrelated owners; aborting startup through the enclosing context manager finalizes acquired resources exactly once.
- Parent versus overlay singleton selection/ownership is correct; ordinary child scopes reuse frozen declarations.
  Closed scopes reject runs, and control-signal cancellation stops later target attempts.
- Aliases, unions, closed generics, patterns/fallbacks, named filters, boundary exposures, decorators/templates,
  pre-configurations, and resource factories retain normal compilation and execution semantics.
- Runtime reports and SARIF accurately distinguish success, failure, and not-executed targets, retain useful sources
  and actual paths, and never retain/export secrets, runtime objects, tracebacks, or arbitrary exception text.
- Intent inspection is side-effect free and distinct from runtime results and hypothetical cache scenarios.
  Declaration-only changes preserve default fingerprints when the graph does not change.
- Existing profiling counts actual resolutions, cache outcomes, initialization and later cleanup without introducing
  a second observation system. Ordinary uninstrumented runtime paths gain no warm-up overhead.
- Public examples demonstrate successful startup, aggregated failures, async activation/cleanup, and safe owner shutdown.

## Definition of done

Implementation and independent review are complete. Acceptance tests, CI, supported-Python checks, executable examples,
strict docs, and focused measurements are recorded. Startup remains explicit; build stays side-effect free; ownership,
runtime outcomes, and static declarations remain distinct. The item remains planned until those conditions are met.
