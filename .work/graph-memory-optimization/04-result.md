# Task 04 result — contextual frozen dependency subtrees

Completed: 2026-10-08\
Status: Reverted on 2026-10-09 — original KEEP recommendation superseded
Implementation agent: GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning

## Maintainer decision and rollback

The maintainer requested undoing task 04 after reviewing its higher process RSS
and slower graph inspection. The implementation, codec changes and active probes
were removed; pre-task-04 source hashes are restored. Tasks 01 and 02, task 03's
audit and the artifact experiment remain. See [rollback verification](04-rollback.md).

The remainder of this report records the implementation as tested before its
removal. Its measurements and raw evidence are preserved unchanged; statements
about the sharing representation below describe that historical experiment.

## Equivalence and representation

The offline census separates service/kind/ordered-dependency shape from captured
selection and activation equivalence. It does not assume execution-step identity
proves occurrence equivalence. The initial eight-route candidate experiment found
65 structural shapes, 62,057 strict shapes and 87,132 narrowly eligible physical occurrences; maximal
disjoint sharing projects 24,633 occurrences through 391 contexts. Synthetic
value IDs and differing captured facts remain distinct. The first audit's broader
structural counter includes 50 negative provider IDs; the verified census counts
physical records separately.

Production sharing runs only after each graph freezes. All predicates, factories,
selection callbacks and derived-argument preparation have already run. The key
uses builtin integer identities and ordered tuples, with no application equality,
hashing, repr or callbacks. Equivalence requires the same captured definition
(service and specialization, implementation, lifespan, name, ordered tags,
build-argument mapping, kind, activation, boundary and declared spelling), the
same registration/value ID referent, argument, position, async/cleanup flags,
cache/cleanup owner categories, ownership reason and provider mode. Ordered
selected children must recursively satisfy that rule.

Only constructor/supplied registration/value dependency trees qualify. Attached
decorators, preconfigurations, decorated or explicit owner links, provider records,
negative provider projections, repeated children, non-tree parent links and
cycles remain concrete. Every child must identify its actual enclosing parent.
Trees smaller than four records remain concrete to avoid context overhead.
A build-local ID census first rejects unique captured ID referents: they cannot
appear in two equivalent disjoint trees. Rejection propagates to enclosing trees.
This reduces temporary indexing without changing the final sharing set. Ineligible
nodes receive no size entry; the graph itself supplies source records, avoiding a
second record index and releasing replaced records immediately.
An iterative postorder prevents a new recursion-depth limit.

The source tree is frozen and reserved. Each use retains its original positive
occurrence IDs through an immutable explicit source-to-target map, including the
root's captured external parent. The record index keeps every original key;
per-occurrence projections contain a source pointer, context pointer and their
own lazy generic-map cache slot. Parent and dependency links project through the
map. Registration IDs, ownership metadata and every other captured scalar stay
identical. Generic cache initialization remains independent per occurrence.

Canonical source trees and projected target trees never overlap; sources are
always concrete records, never projections. Contextual parents may themselves be
logical occurrences. Existing provider views can project a positive subtree
projection; their existing negative-ID contract remains unchanged. Inherited
source graphs remain separate, with cloning and snapshot materialization keeping
their existing graph qualification. Snapshot `freeze()` returns an ordinary
record. No new persistent equivalence index or materialized dependency-tuple cache
is retained.

Occurrence origins and all explanation sidecars remain intact. Differing
contextual explanation paths/selection provenance are not claimed equivalent:
they continue to belong to their own occurrence. Escaped callback Components
keep their graph and exact IDs, so subsequent parent/dependency inspection still
works. This implements metadata sharing without task-03 pruning or an escape
inventory. Runtime steps, instance caches and cleanup ownership are unchanged;
sharing creates no application instances and merges none.

The private artifact codec advances from schema 5 to schema 6 solely to encode
these two captured representation classes and their read-only maps. Its source
compatibility hashes still cover all compiler modules. Earlier artifacts/evidence
are preserved; no public persistence capability is added.

## Fresh-process measurements and rejected approaches

[Baseline](evidence/04-before.json) and [kept implementation](evidence/04-kept-after.json)
each use three fresh normal and three separate traced processes, run serially
without concurrent builds, tests or benchmarks. The fixture, eight routes,
diagnostics-disabled options and resolution workload are fixed. Python 3.14.4,
macOS ARM64; revision `31f1682075b2c146de7672fa37cb5fb563a0ffc7` with all earlier
local work preserved. Tracing starts before fixture import; retained observations
follow collection. Validation, census and inspection are outside timed preparation
and resolution. The cancelled first baseline attempt is excluded and explained
in [the run note](evidence/04-run-note.txt); no successful raw evidence was overwritten.

The [comparison ledger](evidence/04-comparison.json) verifies consistent source
hashes within each six-process group, an unchanged fixture hash, and unchanged
container, tooling and selection-census hashes. It records the new helper,
components, artifact adapter, audit and regression-test provenance. Every original
graph census field except intended shallow storage remains equal, as do template
callbacks, lazy activations, ordinary activations and workload validation.

| Measurement, median | Baseline | Kept sharing |
| --- | ---: | ---: |
| Fixture import, composition and build | 11.227 s | 11.195 s |
| Resolution workload | 23.04 ms | 21.81 ms |
| Current RSS after build | 131.89 MiB | 135.17 MiB |
| Peak RSS through build | 131.89 MiB | 135.19 MiB |
| Retained traced allocations after build | 38.43 MiB | 35.77 MiB |
| Build traced allocation peak | 73.58 MiB | 74.07 MiB |
| Retained traced allocations after resolution | 39.55 MiB | 36.89 MiB |
| Current / peak RSS after resolution | 131.89 / 131.89 MiB | 135.19 / 135.19 MiB |

Net retained Python allocations fall **2.66 MiB (6.9%)**, after all retained
projection/context/remapping overhead. Allocation peak rises 0.49 MiB (0.7%).
RSS rises about 3.3 MiB (2.5%); there is no RSS reduction claim. The normal-process
RSS ranges are 131.09–133.47 MiB before and 133.27–136.92 MiB after. Small build
and resolution timing differences do not establish a general speedup; ordinary
resolution adds no graph pass or compiler work.

The naive [first implementation](evidence/04-after.json) achieved the same retained
allocation saving but reached 118.70 MiB traced peak and 176.67 MiB peak RSS.
It indexed every unique contextual fact and retained a duplicate source-record
index. That version is rejected. The [ID-prefilter intermediate](evidence/04-final-after.json)
reduced the peak to 80.87 MiB but still retained unnecessary size entries and
replaced records. The kept implementation removes both. The intermediate runner's
`physical_records` field counted full concrete records only; the kept runner
correctly counts every physical occurrence object and reports concrete/projection
classes separately. These raw files are preserved as unsuccessful iterations,
not substituted for the final comparison.

## Physical storage and logical identity

All counts below concern the primary graph unless stated otherwise.

| Storage/count | Baseline | Kept sharing |
| --- | ---: | ---: |
| Physical occurrence record objects / logical positive IDs | 88,558 | 88,558 |
| Full concrete frozen records | 88,558 | 63,925 |
| Small contextual projection records | 0 | 24,633 |
| New subtree contexts / remapping entries | 0 / 0 | 391 / 24,633 |
| Existing negative provider contexts | 50 | 50 |
| Shared component definitions | 116 | 116 |
| Distinct execution steps | 1,765 | 1,765 |
| Public walk visits | 8,932 | 8,932 |
| Occurrence records, shallow bytes | 15,586,208 | 12,630,248 |
| New contexts, read-only views and backing maps, shallow bytes | 0 | 922,760 |
| Retained relationship tuples, shallow bytes | 2,653,968 | 1,878,224 |
| Record index / origin indexes, shallow bytes | 5,242,960 / 5,242,960 | Same |
| Occurrence integers, shallow bytes | 2,481,424 | Same |
| Retained equivalence/size/source indexes | 0 | 0 |

The combined primary occurrence/context/link shallow reduction is 2,808,944 bytes
(2.679 MiB); it overlaps the traced allocation saving and must not be added to it.
These are metadata projections, not record pruning or a collapse to execution-step
count. A separate post-collection [graph inventory](evidence/04-generic-verified.json)
finds one retained component graph in this fixture: the primary graph above.
Temporary source-inspection graphs are included in whole-build peaks but do not
survive collection here. Escaped callback snapshots can retain additional graphs;
the existing forwarding-callback regression continues to protect them.

The [verified offline census](evidence/04-subtree-audit-verified.json) reports
88,493 structurally repeated physical occurrences, 25,075 strictly repeated
occurrences and the same 391 disjoint projection contexts. Its broader eligibility
census includes unique nonrepeatable shapes; production's early ID rejection
avoids allocating their keys. Main-graph offline audit time is 0.378 s in one
normal process. A separate [audit-only traced run](evidence/04-audit-only-traced.json)
peaks at 61.98 MiB temporary allocations and retains 15,080 bytes after collection,
including its result. This offline candidate census is not production machinery.

The workload still validates 124 distinct transient workers, 248 wrappers,
7,812 tree objects, 26 managed scopes and 64 async source-map calls, with the same
scoped/singleton identity and complete template callback counts.

## Inspection and lazy caches

Separate fresh [unshared](evidence/04-before-inspection.json) and
[shared](evidence/04-after-inspection.json) processes trace inspection only after
build, resolution, validation and the census. The unshared reference disables
only the subtree pass through an evidence-local patch. These are single-process
observations, not three-repeat latency medians.

| Inspection under tracing | Unshared | Shared |
| --- | ---: | ---: |
| First / repeated 128 explanations (1,280 decisions) | 100.9 / 27.6 ms | 124.5 / 29.6 ms |
| First / repeated full public traversal | 91.9 / 92.5 ms | 152.2 / 151.8 ms |
| First all-roots manifest | 557.9 ms | 674.4 ms |
| Repeated cached manifest | 0.009 ms | 0.026 ms |

Projection property indirection and ephemeral relationship remapping increase
inspection cost. Every first/repeated retained-allocation observation matches
between representations byte-for-byte: 527,712 bytes after the first explanation
sample, 528,440 after traversal and 14,207,399 after manifest construction;
repeated observations are 14,207,983 / 14,208,439 / 14,208,880. The approximately
13.5 MiB manifest/membership retention already exists. No remapped dependency-tuple
or materialized subtree cache is added. Both passes have fingerprint
`fa06427a9c823d18961ba2d173294ce206f38c516f2478dd229e7d1bebaaa722`.

The [two-route diagnostics-enabled observation](evidence/04-diagnostics-inspection.json)
preserves its fingerprint and 1,264 walk visits, with selection-census access
153.8 / 96.7 ms and no callback replay. Task 01's eager diagnostic history remains.

The separate [generic-cache observation](evidence/04-generic-verified.json) initializes
256 projection slots in 0.374 ms and repeats access in 0.114 ms; exactly 256 remain
initialized after both passes. Retained traced changes are 232 bytes then 552
bytes of observation bookkeeping. Generic maps for these fixture types are already
interned during compilation; this is not a cold-library-cache measurement.
Regression tests prove the source slot remains lazy when the target initializes.

## Verification, decision and limitations

All **2,104 tests pass**, including 25 added cases covering full captured-field
identity, contextual differences (derived arguments, boundary, selection argument,
registration ID, async/cleanup/owner facts), cycles and non-tree links, provider
views over projections, immutable remappings, independent lazy generic slots and specialized TypeVar bindings,
same-graph public explanation/census/manifest equality with diagnostics on/off,
and overlays across all four lifespans. The pre-existing suites cover parent-based
templates, escaped predicates, filters, failed builds, managed sync/async cleanup,
failures, concurrency, calling-edge observations and schema-6 independent artifact
loading. Transient products remain distinct.

[Completed checks](evidence/04-checks-verified.json) record Ruff lint/format, type
checks, docs examples and benchmark discovery passing. The first check log is
preserved: its only new static failures were formatting/type annotations in
three offline evidence scripts, subsequently repaired. The suite was rerun after adding explicit specialized-generic regression cases. Strict MkDocs
reproduces the same eight pre-existing outside-docs link warnings; the existing
FastAPI/Starlette deprecation warning remains.

The original agent recommendation was **KEEP**, based on the measured 6.9% net
retained Python allocation reduction. That recommendation is superseded by the
maintainer's rollback decision above. The measured limits were the 2.5% RSS increase,
slightly higher allocation peak and materially slower public traversal/first
manifest inspection. There is no general performance, production-memory or wider
platform claim. Identity-conservative eligibility can miss safe opportunities;
workloads with little repetition pay for a build-local scan without savings.
Owner/decorator/provider/non-tree sharing and arbitrary nested source projections
remain excluded. No 32-route retry, commit, push, deployment or unrelated chat
contact was performed. All earlier implementation and artifact evidence remains
local, intact and uncommitted.
