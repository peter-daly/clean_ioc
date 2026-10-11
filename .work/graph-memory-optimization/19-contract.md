# Task 19 — Reviewed build and analyse contract

Date: 2026-10-10\
Status: Design review complete; builder/composition recommendations accepted by the maintainer\
Scope: Planning only. No runtime implementation or new performance measurements.

The maintainer has settled the two operations and the single rule API, and on
2026-10-10 accepted single-attempt builders and explicit external composition
ownership after review. This contract incorporates the review's simpler
composition lifecycle: no separate close/context-management API. The remaining
details form the reviewed implementation plan, not implemented APIs or measured
savings. [Inventory](19-inventory.md) supplies the source/check boundary;
[result](19-result.md) records the decisions and readiness.

## Operations and capabilities

```python
ContainerBuilder.build(*, build_args=None, profile=None, budget=None,
                       instrumentation=None) -> Container
ContainerBuilder.analyse(*, build_args=None, profile=None,
                         budget=None) -> AnalysisResult[Container]
ScopeBuilder.build(*, build_args=None, profile=None, budget=None,
                   instrumentation=None) -> Scope
ScopeBuilder.analyse(*, build_args=None, profile=None,
                     budget=None) -> AnalysisResult[Scope]
builder.add_validation_rule(rule) -> None
```

`build()` binds and emits execution, including declared provider roots, selected
dependencies, decorators, scope slots, cleanup and warmup instructions. It runs
**zero registered rules**, built-in validation passes or safety-policy audits.
It allocates no library `CompiledGraph`, analysis report, manifest, selection
census or inspection index. Registering any number of rules, including graph/AST
readers or failing callbacks, cannot change that path. Internal execution graphs
and callback snapshots are a different population and remain where required.

`analyse()` performs supported declaration, graph, architecture and compatibility
analysis and runs **all applicable registered rules before returning**. Policy
findings do not stop subsequent checks on an otherwise available graph. Its
execution projection uses the same binding, preference, lifetime and cleanup
calculations as build. Extra architecture roots are inspection-only, never new
resolvable roots. Neither operation implicitly resolves a service, executes a
pre-configuration, activates application factories/constructors, or runs warmups.

| Capability | `build()` output | `analyse()` output |
| --- | --- | --- |
| Return | Ordinary `Container` or `Scope` | `AnalysisResult[Container]` or `AnalysisResult[Scope]` |
| Resolve / provide / ordinary child scopes | Yes | Through an explicitly created test runtime |
| Selected registration discovery | Frozen execution catalogue | Same catalogue when execution emission completed; partial inspection is separately labelled |
| Validation | None; no success report fabricated | Completed immutable `result.report`, including coverage and failures |
| Full graph, manifest, explain, census, ownership/sharing analysis | Absent | `result.graph` and captured diagnostic evidence where available |
| Composition for new overlays | External `Composition` owner, explicitly retained | `result.composition` owns the captured composition |
| Compilation profiling / budget | Explicit operation inputs | Explicit operation inputs covering analysis too |
| Runtime instrumentation | Optional compact execution instrumentation | Passed to explicit test-runtime creation, never required for analysis |
| Partial compilation | Minimal raised `ContainerBuildError`; no runtime | Returned report and partial evidence; no partially wired runtime |

Choose a distinct result over a rich runtime. A rich runtime has convenient
`resolve()` syntax but misrepresents failed/incomplete analysis as a runtime,
encourages accidental activation, and leaves reporting/blueprint ownership on
every runtime. A distinct result gives success and partial failure the same
handling, and makes expensive owners explicit. The additional `.create_runtime()`
call is justified. No successful analysis token is required by `build()`.

## Analysis result, report and test runtime

Recommended public shape (names are proposed, not implemented):

```python
AnalysisResult[T]:
    report: AnalysisReport
    graph: CompiledGraph | None
    partial_graph: PartialGraph | None
    composition: Composition | None
    emission_complete: bool
    selected_registrations: tuple[RegistrationInfo, ...] | None
    create_runtime(*, instrumentation=None) -> T
    close() -> None
    aclose() -> Awaitable[None]
```

`AnalysisReport` replaces the public `BuildReport` name and preserves existing
issue/evidence serialization capabilities. It contains `issues`, `errors`,
`warnings`, `is_valid`, `complete`, the operation's requested/compiled/failed root
counts, stage outcomes, and rule outcomes. Each rule outcome identifies the
declaration, declaring boundary/layer, actual context, and one of `completed`,
`failed`, `unavailable` or `interrupted`. Findings belong to that declaration and
context; a rule that yields no findings still has an outcome. Built-in stage
coverage records unsupported/unknown type reasoning without falsely proving it.
`is_valid` means `complete and no errors`; warnings alone do not invalidate it.

The report is final when returned. Properties, `to_text()`, JSON/SARIF exports,
assert helpers and repeated reads do not invoke rules, selections, derivations,
templates, runtime activation or diagnostic retries. Lazy pure indexes over
already captured graph data remain allowed. Queries explicitly supplied with a
new user filter are new queries, not report reads or reconstruction of old facts.
Report assertions may raise a report-owning analysis exception without running
anything. CLI/check/matrix require only `analyse().report`, not another operation.

`graph` represents the complete supported analysis graph when available, including
policy-invalid graphs. `partial_graph` captures the primary failed attempt and
independent diagnostic attempts when compilation was incomplete. It does not
masquerade as a complete graph. Declaration failures can precede any component
graph: `graph=None`, with a preparation failure and unavailable stage outcomes.
`composition` may be absent if capturing the declarations itself failed.

`emission_complete` is separate from validity. It is true only when the complete
requested execution plan, providers, slots and warmup bindings exist. An error
in an inspection-only root may leave execution complete but analysis incomplete.
The selected execution catalogue is either complete or `None`; tooling must not
present a partial catalogue as the application's full inventory.

`create_runtime()` allocates an ordinary runtime from the already emitted
execution plan, without compilation, rule callbacks or activation. It is allowed
when `emission_complete=True`, including a policy-invalid result: this is an
explicit testing action, not an endorsement. Otherwise it raises
`AnalysisRuntimeUnavailableError` referring to the existing report. No special
invalid-policy opt-in switch is introduced. Production uses a fresh composition
factory and `build()` regardless of whether analysis was run.

Each created root test runtime has fresh singleton/pre-configuration/cache state.
Multiple runtimes do not share runtime singleton state accidentally. Supplied
instances and opaque callback closures retain their explicit object identity;
neither method clones application objects. For a scope result, parent singleton
anchors are intentionally borrowed from the declared live parent, as for an
ordinary overlay. Child scoped state remains independent. A result does not
activate the parent or claim it analysed dynamic object state.

The result supports sync and async context management. It owns the test runtimes
it created and closes them in reverse creation order; scope results never close
their borrowed parent. Explicitly closed runtimes are safe to encounter again.
Async cleanup requires async close/context management, preserving runtime cleanup
errors and aggregation. `close()` prevents further runtime creation and closes
owned test runtimes; an overlay still requires a live matching parent. It does
not revoke a separately retained `Composition` or erase captured report/graph
facts. Those stay inspectable while held; retaining a result or graph retains its
evidence. Runtimes do not point back to the result/report/composition.
Caller-retained detached Components remain independent owners. No destructor is
relied on for resource cleanup.

## Complete validation and partial failure

Rule ordering preserves current declaration/context ordering: root rules from
oldest parent layer to newest overlay, in registration order per layer; then
boundary rules in composed boundary order and declaration order. An inherited
declaration runs once for the newly analysed composition, not once per ancestor.
Registering the same function twice creates two declarations and two invocations.
Root rules see the full composed analysis view. Boundary rules receive the
boundary-local roots/entrypoints with the existing reachable dependency view;
this is not a promise to hide every imported dependency from inspection.

One invocation means call the rule once and exhaust its returned synchronous
iterable once. Preserve valid yielded findings before any later failure.
Exceptions, async returns, malformed results and malformed yielded issues produce
`validation-rule-error` plus a `failed` outcome. Continue other available rules.
Do not infer requirements, purity or applicability from callback source, prior
success or observed reads. Remove both old rule categories internally as well
as publicly. Type/callability/synchronous-callback shape checking at registration
is input parsing, not executing or evaluating the rule.

| Situation | Required analysis outcome |
| --- | --- |
| Fully compiled graph, built-in policy errors | Run every rule; return all findings, `complete=True` if all checks completed, `is_valid=False` |
| One rule throws or yields a bad value | Keep earlier findings, run remaining rules, mark failed rule; `complete=False`, `is_valid=False` |
| Primary wiring failure | Keep original failure/provenance; attempt independent supported diagnostic roots; run available declaration/partial checks; record unavailable full-graph checks |
| Incomplete graph | Do not pass a partial view off as a full `ValidationContext`; all custom graph rules are `unavailable` unless a complete graph was actually obtained for this analysis |
| Diagnostic retries succeed after primary failure | Preserve primary failure and inconsistent-attempt evidence; do not certify success or publish a runtime from a retry |
| Explicit budget exhausted | Stop admitted work, retain prior findings, mark unrun/interrupted work; return incomplete report and exhaustion facts |
| Cancellation / `KeyboardInterrupt` / `SystemExit` / allocation failure / internal compiler defect | Propagate; do not fabricate a complete report or convert compiler bugs into user policy issues |

The deliberately conservative partial-graph rule policy needs no rule-requirement
DSL: arbitrary rules currently accept a whole `ValidationContext`. A future
partial-analysis callback protocol would be separate work. Rules unavailable due
to missing context are not silently omitted and are not counted as passed. With
an unlimited budget and an available complete graph, every declaration runs even
if earlier rules have errors. With budget/cancellation/failure, the result honestly
records why complete validation was impossible.

Analysis-only diagnostic root retries may repeat wiring callbacks as independent
attempts, retaining attempt IDs and inconsistent results as today. They never
rerun a validation declaration and never replace primary execution with a
different successful composition. Build has no diagnostic retries. Reading a
report cannot initiate either kind of work.

## Builder consumption, mutation and retry

Use a single-attempt state machine shared by root and scope builders:
`mutable -> compiling -> consumed`. Before admission, bad Python call signatures,
invalid option types or a closed parent raise input/state errors and leave the
builder mutable. Once compilation starts, success, returned invalid/incomplete
analysis, ordinary compilation failure, budget interruption and cancellation all
consume the builder. Failed attempts are not implicitly retryable. This deliberately
replaces the current successful-build-only consumption contract.

All methods that mutate declarations, descendant boundary handles, and both
operations reject reentrant mutation or compilation while `compiling`; after
consumption they raise `BuilderAlreadyBuiltError` with the revised message.
Concurrent use of one builder is unsupported and must fail the same admission
gate rather than start two operations. A template/selection/validation callback
cannot mutate or recursively compile its active owner. Other independent builders
remain usable. No rollback of callback side effects is promised.

Consequently `builder.analyse(); builder.build()` and the reverse are unsupported,
even after a failed analysis. Use `make_builder(inputs).analyse()` and a fresh
`make_builder(inputs).build()`. These are separate compositions; selections and
derivations may run in each and stateful callbacks may produce different outcomes.
Analysis certifies the captured inputs/attempt only, not every environment.
Internal analysis root attempts are part of one admitted operation, not builder
retries. Release consumed builder composition references where no external owner
needs them; never clear caller-owned application values or detached snapshots.
Single-attempt consumption permits ownership transfer and release but does not
itself lower memory. Task 21 must implement the releases at proven last use;
tasks 22/25 measure retained owners and peak overlap. Keeping a consumed builder
alive must not accidentally keep its entire declaration registry alive solely
for an unsupported retry. Exception tracebacks and caller-held references remain
independent owners and must be reported honestly.

## Ordinary scopes and explicit overlay composition ownership

Keep `runtime.new_scope()` available on every execution runtime. It shares the
compiled plan and singleton owners; nested ordinary scopes retain existing
parent scoped-value lookup/provision semantics. An overlay built by `ScopeBuilder`
uses its own scoped cache (`inherit_scoped=False` today), borrows existing parent
singleton/pre-configuration anchors, and owns its new activations/cleanup.
Closed-parent checks and actual owner-token lookup are runtime state/instruction
requirements, not validation policy. No child can close or replace a parent owner.

Use an explicit **`Composition` handle**, obtained with
`builder.retain_composition()` before the operation. This method does not compile,
analyse, resolve or snapshot the subclass graph. It requests an external owner of
the realized declaration snapshot when that builder later compiles. Repeated
calls before admission return the same handle. The handle is pending until a
complete execution composition is captured, then sealed to that operation; failed
or incomplete realization leaves it unusable for overlay construction. It retains
declarations, rules, original wiring inputs and realized discovery/template facts
needed for overlays, but no analysis report/graph merely because it was requested.
Its captured declaration structure is immutable after sealing; application values,
instances and callback closures remain their original opaque objects, not deep
copies or promises of immutable application state.

```python
builder = make_builder(config)
composition = builder.retain_composition()
runtime = builder.build()
child_builder = ScopeBuilder(runtime, composition=composition)
child = child_builder.build()       # zero validation, even with inherited rules
```

This is a composition-retention API, not a validation switch or analysis token.
Plain `make_builder().build()` requires neither a handle nor prior analysis.
The execution runtime stores only opaque composition/owner identity needed to
match a supplied handle; it has no reference to the handle or blueprint. Matching
prevents combining an arbitrary blueprint with another runtime's singleton
anchors. Ordinary descendants inherit this small identity. The handle owns the
realized snapshot outside the runtime; releasing it has no effect on execution.

`ScopeBuilder(parent, *, composition)` replaces the one-argument constructor.
The parent must be live and match the handle's realized composition/owner lineage.
Overlay singleton specializations without a frozen parent anchor remain a local
emission failure; do not instantiate a second singleton secretly. The child
builder can retain its own handle for later layered overlays. Parent handles stay
independent; new declarations cannot mutate installed parent boundaries or
parent-owned plans. Boundary visibility still determines which identities may be
patched, rather than treating private IDs as globally editable.

Analysis captures this owner as `result.composition` without a separate retention
request. After `test = result.create_runtime()`, use
`ScopeBuilder(test, composition=result.composition)`; the test runtime has the
matching identity. `ScopeBuilder.analyse()` reads inherited rules from that handle
and returns its own complete result. It does not replay a parent analysis report
as approval of an altered graph. `Composition` has no `close()`, `aclose()` or
context-manager lifecycle and owns no application-resource cleanup. Its storage
follows ordinary reference ownership. Releasing the last reference allows its
otherwise unowned declaration data to be collected; it does not invalidate
already emitted children. A child analysis result/active builder owns the source
facts it still needs. Retaining any other handle/result/active builder can keep
those facts alive. Analysis-result cleanup still closes its owned test runtimes,
whose closed-parent checks prevent new overlays; it does not revoke a handle.

The handle may be small while its retained declaration data is substantial.
Moving that data outside the runtime saves no process memory while it remains
retained. Compare unrequested, held and released composition in tasks 22/25;
measure builder/source overlap and do not claim automatic peak-memory savings.

This proposal adds explicit ownership rather than keeping a special rich-runtime
subclass. No `runtime.new_scope_builder()` convenience that hides source retention
remains. The maintainer accepted explicit ownership and the minimal lifecycle
using the API shape above. Do not add a separate composition-resource lifecycle
without a concrete implementation need and a reviewed contract change.

## Inputs, discovery and instrumentation

`build_args` stays an immutable shallow mapping with string keys. Overlay values
override parent inputs by the existing merge semantics. Values remain opaque
referents, not recursively copied or serialized. `set_provider_roots(None)` keeps
the documented automatic provider families; an explicit iterable declares those
public handles, and `()` disables automatic public handles. Injected/private
providers and managed runtime-context roots still bind as needed. This input is
wiring, never a validation switch. A requested provider target that cannot be
bound is an emission failure.

Preserve `selected_registrations` as frozen `RegistrationInfo` entries deduplicated
by selected registration identity and visible canonical service identity, in
execution traversal order. Include selected dependency-only registrations,
deferred provider/map/managed targets, decorators and warmup targets. Preserve
closed implementation types and static instance implementation identity; unknown
factory result identity remains `None`, not a reason to reject a build. Exclude
synthetic components, rejected alternatives and unreachable architecture-only
inspection roots. Public-root visibility does not expand to enable discovery.
Reads run no callbacks or activation. Compare semantic catalogues across fresh
builders; random registration IDs cannot be compared across independent inputs.

Compilation budgets remain explicit operational limits, not safety certificates.
Keep nonnegative integer admission limits for occurrences, dependency depth,
specializations, generated outputs, preparation operations and diagnostic attempts.
Build uses zero diagnostic attempts and never adds diagnostic work to consume that
allowance. Analysis counts independent attempts and rule invocation/iteration work.
Limits are cooperative admission counts, not hard CPU/time/memory limits inside
arbitrary callbacks. Budget exhaustion raises a minimal build error or returns an
incomplete analysis report. It never invokes an analysis fallback.

`CompilationProfiler` observes the named operation and records counts/spans and
completed/failed/interrupted status. Analysis returning an invalid report is a
completed operation with an invalid analysis outcome, not a missing report.
Profiler bookkeeping, labels and optional costs must be measured separately; it
cannot request diagnostics, alter target selection or activate rules in build.

Runtime `Instrumentation` remains optional. Replace manifest fingerprints/graph
paths/sharing-report keys with compact **execution-plan identity + local step or
owner identity**, and service/registration labels captured from execution facts.
Identity is stable within the plan/owner lineage, not a semantic manifest hash
across processes. Parent anchors keep their parent's identity; cleanup/cache and
request events keep separate event kinds. Rich analysis can map these IDs to its
captured paths without adding a reverse graph owner to execution. Overlay
instrumentation continues to use the parent's profiler so shared owner events
are coherent; an incompatible profiler is an input error. Ordinary scopes inherit
instrumentation without compiling. `create_runtime(instrumentation=...)` installs
wrappers once on that test runtime without a manifest/index/analysis rerun.

Warmup descriptors use those compact target/plan identities and sync/async facts,
not `CompiledGraph.manifest()` or graph path indexes. Remove the old manifest
fingerprint interpretation in `WarmupReport` and profiling output; migrate serializers
and consumers explicitly. Compile target bindings in declaration order. Warmup
execution remains explicit, respects the target's declared lifetime/cache owner,
aggregates ordinary activation failures, and performs ordinary cleanup. A
representable non-singleton warmup or duplicate target emits normally and is an
analysis finding; do not silently promote it to singleton or deduplicate declared
activations. Missing/ambiguous bindings and duplicate plan names without a unique
address remain emission failures. Sync execution of required async work retains
the existing runtime refusal/report behavior and does not run an analyser.

## Failure boundary and concrete acceptance examples

`ContainerBuildError` becomes a minimal emission error: `code`, bounded local
`path`, a library-authored message, optional operation/origin identity and budget
facts. It owns no report, graph, explanations, census or partial-attempt catalogue.
Do not format arbitrary application values or exception strings to elaborate it.
Original Python exception chaining/tracebacks retain their normal debugging
semantics and may keep caller/compiler frames alive; this is not a promise of
zero retained memory on failure. Do not mutate foreign errors or application
objects to achieve a smaller error. Internal invariant bugs propagate as defects,
not a new safety-policy report.

| Concrete declaration | Build | Analyse |
| --- | --- | --- |
| Singleton takes a scoped dependency/slot or `ResolutionContext` | Emit declared cache/owner/context instructions; no captive audit | Captive lifetime/runtime-context error |
| Service `A`, factory annotated to return unrelated `B`, dependencies fully bind | Emit factory call and retain static discovery facts | Definite return mismatch; unknown annotations remain unknown |
| `factory()` configured with fixed `extra=1`, no `**kwargs` | Emit call with that keyword; activation may raise Python `TypeError` | Invalid configured argument finding |
| Unique `Provider[A]` whose target requires async activation | Emit bound sync handle with existing runtime refusal semantics | Sync/async compatibility error |
| Supported per-call contract, implementation missing one method | Emit generic forwarding wrapper; call may fail | Implementation conformance error |
| Bound transient warmup target, or repeated same target | Emit ordered warmup steps respecting transient/repeated semantics | Warmup lifetime/duplicate-target finding |
| Two ordinary scalar candidates with existing first/preference winner | Emit the established winner | Existing ambiguity advisory |
| Missing marked scalar entrypoint with no actual dependency requesting it | Emit existing execution roots; resolution may be unavailable | Missing entrypoint error |
| Required constructor dependency has no target/default/slot | Minimal missing-target error | Compilation finding, partial evidence, unavailable graph checks |
| Injected scalar provider has two equal candidates and no unique winner | Minimal binding ambiguity; no invented first-wins policy | Same binding failure with diagnostic context |
| Required dependency TypeVar has no resolvable binding | Minimal specialization error | Same failure plus available independent findings |
| Direct recursive eager construction has no finite supported instruction plan | Minimal cycle/emission error | Cycle evidence; deferred handles are evaluated under their own wiring semantics |
| Provider map callback throws, key is unhashable, or two distinct entries require the same key | Minimal map binding error | Map failure plus available evidence; no arbitrary collision winner |
| Cannot map cleanup to an actual owner token, or parent singleton specialization has no anchor | Minimal owner/anchor emission error | Same failure; never remove cleanup or create a duplicate parent singleton |

These are future contract acceptance cases, not claims the current source already
allows them. [Inventory](19-inventory.md) distinguishes mixed subcases such as
alias normalization, return-only generic variables, duplicate declarations,
per-call forwarding shape, slot provisioning and boundary cycles. A helper's
current `validate` name or error label does not classify its entire body.

## Public removal and migration

Remove `BuildMode`, `ValidationRuleMode`, `build(mode=...)`, rule `mode=...`,
`build_mode`, `explain_metadata_enabled`, `allow_scope_builders`, runtime
`build_report`, runtime `validation_report()` and runtime graph/inspection access.
Remove the private compatibility route that enables rich diagnostics for rules.
There is no deprecated adapter, hidden mandatory-rule subset or public fine-grained
policy flags. Keep runtime execution-root `components` and discovery without
claiming those roots form a full inspectable graph. Move graph inspection to the
result; migrate report type imports to `AnalysisReport`.

Production wrappers call `builder.build()` with actual wiring/operational inputs.
CI calls `result = make_builder(inputs).analyse()` and reads/asserts
`result.report.is_valid`. CLI check/explain/manifest/diff/census/triage and matrix
variants consume the result directly, including invalid/incomplete output.
Profiler commands select an operation in the command interface, not via a library
build mode. Both real Bark UoW rules stay registered through the single API and
run only in analyse. Invalid-UoW policy assertions move to analysis tests while
actual dispatch, cleanup and capacity tests stay intact. Historical evidence and
archived harness source remain unchanged. The parked artifact project gains no
support or implementation through this migration.
