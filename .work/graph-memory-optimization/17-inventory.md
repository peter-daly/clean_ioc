# Task 17 — intermediate occurrence last consumers

This audit starts from all 46 accepted task 16 source/harness hashes. The bounded
candidate transfers retained drafts out of an obsolete dictionary during existing
successful run finalization. It does not reclaim rejected candidate subtrees while
compilation or validation is in progress.

## Status and ownership map

| State / owner | Required facts and readers | Last consumer / safe boundary |
| --- | --- | --- |
| Undecided candidate, compiler frame, dependency alternatives | Every contextual parent, dependency, decorator, configuration, owner and generic fact; ordered callbacks, preferences, fallback and boundary filtering | Keep complete until its original decision and every enclosing candidate have finished. A locally selected dependency is still an alternative in its caller. |
| Selected candidate during compilation | `_CompiledCandidate`, root/architecture plans, provider maps and adapters, invariant subplans; Components point to `(graph, occurrence)` rather than owning drafts directly | Complete the entire primary compilation, mandatory final checks, late arbitrary build rules, warmup planning and selected catalogue capture. Descendant-only reachability is insufficient. |
| Rejected candidate | Original decision, root-candidate records, explanations, contextual relationships and opaque execution values; later callbacks may inspect saved Components | Graph-wide rules can read rich rejection facts and caller captures until existing reduction. Opaque cache fallback stays strong. A rejection is not a last-use signal. |
| Decorator decisions and template targets | Ordered selected/rejected facts, target/source Components, original template binding/filter/position results | Late build rules and analysis consumers; no callback replay. Existing detached target/position snapshots own their own records and remain caller-owned. |
| Source inspection graphs | Complete requested source relationships and static definitions in template selections/generated candidates, inherited singleton sources | Existing expansion/blueprint and callback owners. Removing compiler ownership cannot invalidate caller-held source Components. The historical small source-graph cost does not justify a new lifecycle. |
| Owner, parent and contextual provider projections | Graph-local owner and parent IDs; projection context maps physical source and contextual parent; managed providers may perform arbitrary compiled root lookups | Existing runtime closure follows all six relationships, physical projection sources and contextual parents. Keep private managed targets, architecture roots during first retention, warmups and anchored ancestor graphs. |
| Activation cache and invariant/adapter owners | Task 13's exact scalar/key eligibility, arbitrary opaque values, source registration/layer identity; adapter source steps and invariant registration tuple | Existing cache/compiler release. No new weak ownership, value traversal, derived-value replay or early cache clearing. Draft value occurrences hold `type(value)`; execution `_ValueStep` owns the actual derived value. These owners must not be conflated. |
| Failure witnesses | Original path, origin, structural facts, callback failure and budget evidence; rich failed analysis graph/partial attempts where supported | Capture at original failure. Failed finalization freezes complete state using its existing path, before task 17's successful-retention branch. Tracebacks/builders/caller-held foreign errors remain independent owners. |
| Saved primary-graph Component | Graph plus numeric occurrence ID; public field access resolves against the current graph | Same established reduction/expiration boundary. Saved selected Components remain valid; discarded live views expire as before. A saved Component does not directly pin its old `_ComponentDraft`. |
| Detached snapshot Component | Its separate graph/dictionary/records and immutable definitions, conditionally populated generic-map cache | Caller lifetime, including after runtime teardown. No back reference to the primary graph or new history chain. Task 16 snapshot behavior is untouched. |
| Analysis and overlay parent | Complete supported graph/evidence, composition and validation-only rule readers | Analysis lifetime and explicit validation passes. Inherited graph identity remains distinct even when occurrence integers coincide. Task 17's mutable retention branch is not used for ordinary analysis freezing. |

## Checks that prevent general streaming reclamation

Cycle, argument-policy, generic binding, lifetime/captive, deferred provider and
cleanup checks can capture failures when the relevant dependency is compiled.
That does not make their components dead: ancestry, alternate candidate selection,
contextual filters, snapshots and later error witnesses still require them.

Root entrypoint cardinality/fallback checks, boundary-local entrypoints/exposures,
provider-root availability, managed acquisition targets, whole-graph ownership,
arbitrary registered build rules and analysis reachability need the completed
topology or their established full evidence. Warmup planning and observation
preparation have later consumers as well. No rule purity is inferred from source,
an observed read set or previous success. No new requirement flags are introduced.

Compacting a rejected subtree into decision-only facts would lose arbitrary
Component relationship readers. A full compatible compact representation would
still need every exposed field, graph-qualified relationships, stable snapshots
and opaque owners; it is a broader representation project, not demonstrated
reclamation. Task 04 contextual sharing remains reverted.

## Bounded transfer proof

`_retain_runtime_graph` first walks selected executable carriers and computes the
existing complete closure. Its integer `live` set is scoped to `plan.graph`.
Components in other graphs are not seeds in this graph; negative provider views
add both their physical source and contextual parent. This existing closure is
the liveness accounting: no new counters, weak owners or application-key handles.

Before task 17, the local `drafts` variable retains the whole original dictionary
after `graph._drafts` is replaced by the live subset. Consequently selected drafts
remain alive even after `freeze()` constructs their replacement records. The
compiler/plan/candidate/snapshot readers use Components, not that old dictionary.
The source audit finds no published old-dictionary alias: other direct readers
are `record`, source-entry checks, provider preparation and partial failure capture,
which have finished before this successful-retention boundary.

The candidate uses `drafts.pop(occurrence)` instead of `drafts[occurrence]` while
forming the new dictionary. It transfers each selected draft's ownership; it does
not drop a draft before the new dictionary owns it. The iteration is the same
`live` set and the resulting key/record order is unchanged. Old dictionary capacity
is deliberately retained, as are all discarded values in their original relative
order. Existing freeze pops each selected draft and constructs its replacement.
One final `record` local in the closure walker can keep a draft alive until return;
the census counts that real owner rather than assuming every selected draft dies.

Every retained occurrence field is borrowed by the new record. The immutable
definition is borrowed too, except the existing final normalization can select a
definition with the same eleven referents and the same ordered Tag referents.
Live tags are exact tuples from `_Compiler._draft`; replacing such a tuple releases
no distinct opaque Tag referent. Definitions, drafts and their ID-only weak-pool
keys have no application finalizers. No application hash/equality/repr/callback
is invoked by transfer or final-freeze identity keys. Generic caches remain the
existing per-record behavior.

Discarded drafts keep the original disposal boundary after freeze. The bounded
internal ownership witness deliberately gives a discarded draft the last strong
reference to an opaque implementation. Its finalizer reads a retained Component
with two distinct original Tag tuples that final freeze normalizes. The original
and transfer both observe a frozen graph and normalized tags. The broader
`del drafts` alternative observes an unfrozen graph and unnormalized tags. This is
an internal ownership counterexample, not a claim that this exact private setup
is a public registration recipe. It demonstrates why broad alias disposal is not
authorized by the selected-only proof.

Failures in selection, arbitrary rules, budgets and warmup planning occur before
this branch and retain their original freeze/witness paths. Freeze remains an
internal, nontransactional allocation pass; the change adds no callback or new
user-controlled failure operation. Recovery from injected private freeze faults
or allocation exhaustion is not a new transactional guarantee. Existing public
failure/retry tests remain required.

## Measurement separation

The bounded screen uses symmetric captured-source loaders before measurement,
three normal and three separate traced fresh serial processes per policy, with
BEFORE/TRANSFER order reversed on the middle repeat. It runs the unchanged eight-
route public run control. Constructor/destructor census and segment-peak observers
run in separate processes; their timings are not performance evidence. The
whole-build peak, simultaneous drafts/records and freeze-overlap observations are
reported separately. No stage percentages are summed and no new definition-density
policy is included.
