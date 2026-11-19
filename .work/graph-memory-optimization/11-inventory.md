# Task 11 — required evidence, readers and lifetimes

Reviewed against task 10's accepted current source on 2026-10-10. This supersedes
historical flag-based lifetime assumptions only for the new public modes. The
[task 06 inventory](06-inventory.md) and its failed probes remain intact.

## Reader and lifetime inventory

| Reader / source owner | Required evidence | Last supported consumer / lifetime |
| --- | --- | --- |
| Blueprint preparation, aliases, source/template expansion, boundary Expose/Use checks | Definitions, declaration order, registration identity, boundary/layer and origins; lazy source relationships and actual callback results | Primary compilation and all required preparation checks; retain original builder separately for unsuccessful-build retry; analysis retains composition for overlays |
| `_Compiler` structural checks | Complete dependency/parent/owner relationships, lifespans, cleanup ownership, deferred/managed-provider boundaries, cycles, generic bindings and missing/ambiguous selections | Actual selection/activation-plan decision; cannot substitute optional histories for structural state or skip unused declarations that analysis must validate |
| Registration/candidate/filter/preference/decorator callbacks | Current component and contextual ancestry, eligibility, order, dependency and decorator views; source template identities and parameter policies | Synchronous original invocation; detached snapshots may escape and remain caller-owned; no replay to recover omitted metadata |
| `_recorded_root_selection`, `_finalize_plan` | Root candidates including fallback reasons, entrypoint requests and captured filter results, boundary-local exposure/locality | Complete-graph mandatory entrypoint checks, before custom build rules; entrypoint origins are now attached to issues at creation |
| Existing build-mode rules (root, boundaries, inherited overlays, `PolicyPack`) | Arbitrary supported graph APIs: walks, ownership, origins, generic/parameter selections, decorator selected/rejected facts, template sources, manifests, census, AST helpers | Both modes run rules. Public run conservatively enables rich temporary diagnostics whenever any build rule is registered. All yielded findings are consumed in order; unknown callable requirements remain rich |
| Validation-only rules | Same supported graph APIs | Analysis `validation_report()` only, once per explicit pass. Build callbacks are not replayed. Run registration does not invoke or retain the callbacks. CLI/matrix exact-pass behavior remains task 10's tested contract |
| Budget admission and refusal | Original counters, phase, path/origin, findings already yielded, callback-error state, original failure, primary compiler partial state when analysis requested | Refusal dominates callback errors even when a callback raises a foreign error after exhaustion; no diagnostic recovery after refusal; public run strips optional histories only after capturing admitted findings |
| Warmup planning | Selected frozen singleton targets, async activation/cleanup support, paths and manifest fingerprint | After mandatory validation, before run reduction; failed warmup expires already-issued run views; actual warmup activation still happens only on explicit runtime execution |
| Instrumentation preparation / profiler binding | Executable/private architecture relationships, static fingerprint, path/ownership/sharing attribution | Before run reduction; failed profiler binding also expires views. Ordinary runtime profiling uses prepared descriptors and does no new graph-wide work |
| Selected-registration catalogue | Identity and implementation type of selected executable roots, dependencies, private/deferred targets and decorators | Captured before reduction, retained in both runtimes. Architecture-only roots do not become public roots/catalogue members merely for discovery |
| Successful run reduction | Complete execution closure, required provider projections/parents, warmup and observation state | Reduction after all consumers. Every `CompiledGraph` replacement of that build expires together; inherited analysis graph remains live |
| Run failures | Original code/message/path, safe origin, existing structural mechanism facts, one representative rejection/failing-callback witness where captured, budget facts | Exception/report retains these facts without a compiled graph, optional history, or replay. No claim of complete independent-root analysis |
| Analysis failures and private historical finalization | Existing frozen failed-finalization graph, diagnostics and supported partial/retry history | Unchanged rich inspection. Additional orphan work / retries can invoke additional callbacks. Task 06's failed-finalization counterexample remains valid here |
| Exception ownership | This build's errors, plus ordinary traceback references and possibly unrelated callback-owned errors | Only errors constructed within the run build's ownership scope are normalized. Saved foreign analysis errors/graphs are never mutated. Tracebacks and user builders are separate owners, not counted as removed |

## Ownership implementation

Each `CompiledGraph` has a build-local `_InspectionLifetime`. It keeps an integer
identity → weak-reference registry, never graph hashes/equality. Weakref callbacks
hold only a weak reference to the registry owner. Dead boundary views remove their
entries immediately, avoiding an accumulating history of explicit validation
passes. `dataclasses.replace` shares the lifetime for boundary and warmup views.
New builds, overlays and loaded experimental graphs receive separate lifetimes.

Expiration clears roots, evidence maps and all inspection caches on every live
view, then clears the registry. It does not mutate the underlying analysis parent
or detached result objects extracted by the application. The graph's public
access guard still rejects saved bound methods. The registry does not add runtime
resolution work and is compatible with Python 3.11's dataclass weak-reference slot.

Public run `_build_plan` owns a lifetime even if a budget stops before a finalized
plan can be returned. A context-local marker identifies exceptions constructed in
that build, with proper nesting/reset for nested builders. Run cleanup may traverse
cause/context links but only normalizes matching ownership. External errors remain
caller-owned. Failed observation preparation is handled after `_build_plan` too.

`GraphVisit.issue` captures a graph-qualified identity token in addition to numeric
occurrence paths. The token is the weak registry owner, not the graph. Rule-origin
capture and SARIF reject foreign numeric matches; manual/foreign issues fall back
to the rule declaration rather than inventing exact occurrence provenance.

## Concrete capability decisions

- No new rule requirement DSL or fine-grained build flags. There is no demonstrated
  avoided-allocation payoff that justifies restricting arbitrary existing callbacks.
  Future explicit declarations would require checked access and conservative unknown
  fallback; source inspection or observed-read inference is not acceptable.
- Keep all currently constructed decorator/template facts until their consumers
  finish. Task 06's coarse omission remains rejected. Task 12 can change the
  representation/construction order but must provide the same truthful views.
- Public run failures deliberately differ from private historical reduced failures:
  rich views expire on failure as well as success, but useful original findings and
  witnesses survive. `diagnostics_enabled=False`, no graph/partial graph, and triage
  `attempt_history_available=False` mean unavailable history, not complete empty history.
- Origins can be unknown when no declaration/source was captured. Do not infer them
  from labels, numeric occurrence coincidences, callback code, exception formatting or
  a replay. One selection witness is representative; it is not a selected/rejected
  catalogue or a completeness claim.
- Validation-only command/saga policy registration and selected-type discovery remain
  accepted in public run mode. Synthetic command-shaped boundary rules and the rich
  provider/template fixture cover the contract; actual Bark/Cop verification remains
  task 18 and is not claimed here.

## Handoff to 12 and later lifetime tasks

Task 12 should construct compact facts directly, preserve graph-qualified identities,
order/reasons/targets, and keep diagnostic history rich whenever build-rule compatibility
requires it. Measure no-rule run separately from rich-rule run and analysis. Do not
attribute this task's bounded escaped-view retention fix to the ordinary no-callback
eight-route fixture. The one rejection witness in diagnostics-off selection is captured
only when no candidate survives; no full diagnostic object is introduced per successful
selection. Failure callbacks capture their witness once at the exception site.

Tasks 13–17 still require ownership proof for compiler cache values, map keys,
mutable drafts, detached callback snapshots and graph-wide validation. This task
does not weaken those constraints or integrate any archived task 06–09 prototype.
