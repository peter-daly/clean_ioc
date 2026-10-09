# Graph memory optimization

The [artifact retest](artifact-retest.md) compares compilation/export and fresh-process
loading after tasks 01 and 02, using the richer fixture. It is a separate local
experiment and does not implement tasks 03 or 04.

The [retest after task 05](artifact-retest-post05.md) compares full and reduced
artifacts using the same current runtime in separate compile/export/load processes.

Created: 2026-10-08\
Status: Tasks 01 and 02 retained; 03 pruning declined; 04 reverted; 05 retained; 06, 07 and 08 investigations complete; 09 refinement complete; isolated prototype retained.

Reduce the memory retained by the compiled output graph while preserving
resolution, ownership, filtering, inspection and diagnostic behaviour. Measure
compilation peak memory and build time alongside retained memory. These nine
tasks follow the investigation using the large graph fixture with registration
templates, decorator templates, providers and maps.

Task 05 adds a different, explicit build mode: `explain_metadata=False` removes
metadata unnecessary for resolution and enabled runtime capabilities. It permits
reduced inspection in that mode, addressing the compatibility constraint that
blocked task 03. GPT-6.1 Sol with high reasoning implemented and verified the option; its
[result](05-result.md) records the capability limits and measured tradeoffs.

Task 06 investigates preventing unnecessary metadata allocation during compilation.
It extends the work from successful-runtime retention to creation costs and
intermediate lifetimes, using task 05's reduced mode as the initial target.

Task 07 investigates object layout and avoidable construction: effective slots
across inheritance, smaller drafts, graph indexes, and cache lookup before step
allocation. It builds on task 06's findings without implementing its proposals.

Task 08 follows up the compact-index probe from task 07, investigating mapping
semantics, artifact compatibility, sparse storage and lookup costs before an
implementation can be recommended.

Task 09 integrates task 08's native dictionary-delegation fixes in an isolated
candidate, selects a small/sparse fallback policy and repeats compatibility and
memory measurements before deciding production readiness.

## Tasks and recommended order

| ID | Task | Status | Starting point |
| --- | --- | --- | --- |
| 01 | [Compact and share decorator-selection facts](01-compact-decorator-selection-facts.md) | Complete | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](01-result.md) |
| 02 | [Separate component definitions from occurrences](02-share-component-definitions.md) | Complete | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](02-result.md) |
| 03 | [Audit and prune discarded compilation records](03-prune-discarded-records.md) | Complete — pruning declined | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](03-result.md) |
| 04 | [Share repeated subtrees through contextual views](04-share-contextual-subtrees.md) | Reverted — dropped | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](04-result.md), [rollback](04-rollback.md) |
| 05 | [Make explanation metadata optional and minimize the runtime container](05-optional-explanation-metadata.md) | Complete — retained | GPT-6.1 Sol (`gpt-6.1-sol`), high reasoning; [result](05-result.md), [inventory](05-inventory.md) |
| 06 | [Investigate avoiding metadata creation during compilation](06-avoid-metadata-creation.md) | Complete — investigation only | GPT-6 Astra (`gpt-6-astra`), high reasoning; [result](06-result.md), [inventory](06-inventory.md) |
| 07 | [Investigate object layout and avoidable allocation](07-object-layout-and-allocation.md) | Complete — investigation only | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](07-result.md), [inventory](07-inventory.md) |
| 08 | [Investigate compact indexes](08-compact-indexes.md) | Complete — investigation only; refine | GPT-6.1 Sol (`gpt-6.1-sol`), high reasoning; [result](08-result.md), [inventory](08-inventory.md) |
| 09 | [Refine compact indexes and verify dictionary compatibility](09-refine-compact-indexes.md) | Complete — isolated prototype retained; not production adopted | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](09-result.md), [inventory](09-inventory.md) |

Tasks 01–08 have recorded outcomes. Task 06 was completed by Astra with high
reasoning on 2026-10-09; production optimization remains unimplemented. Task 07
was completed by GPT-6.1 Sol with medium reasoning on 2026-10-09; its proposals
remain unimplemented. Task 08 was completed by GPT-6.1 Sol with high reasoning on 2026-10-09;
its then-measured index remained not ready pending native-delegation integration
and remeasurement. Task 09 was completed by GPT-6.1 Sol with medium reasoning: integrated native
delegation, bounded small/sparse fallback and final measurements address those
blockers. Its isolated prototype is retained for implementation review; production
adoption is not approved. Reassess recommendations against
the measured compiler.
A task may conclude that a proposed optimization is unsafe
or not worthwhile; record that outcome and its evidence instead of forcing an
implementation.

## Current evidence

The [fixture report](../../docs/graph-memory-fixture.md) and
[raw results](../../benchmarks/graph_memory_results.json) describe the eight-route
baseline on Python 3.14.4, macOS ARM64. Three normal and three separately traced
processes produced:

| Measurement | Baseline |
| --- | ---: |
| Median fixture import, composition and build | 7.630 s |
| Median process RSS after build | 276.2 MiB |
| Median retained traced Python allocations after build | 187.2 MiB |
| Median traced Python allocation peak through build | 222.7 MiB |
| Physical graph records | 88,558 |
| Distinct execution steps | 1,765 |
| Decorator-explanation entries, diagnostics disabled | 56,522 |
| Component-record objects, shallow storage | 21.6 MiB |
| Record index / origin index, shallow storage | 5.0 MiB / 5.0 MiB |

A subsequent one-process inspection counted 565,220 unique decorator decisions
and 565,220 unique template-fact objects. Only 792 decisions were selected;
564,372 recorded `template-target-not-selected`. Explanations, decisions,
template facts and their selected/rejected tuples occupied 139.7 MiB of combined
shallow storage. This additional census is not yet included in the raw result
file; task 01 must make it reproducible before relying on it for comparisons.
Shallow storage is not total process memory or a promise of recoverable savings.

An initial 32-route run exceeded 4 GiB RSS before completion and was stopped.
Use eight routes for the initial comparisons and increase scale deliberately.
The baseline is synthetic and does not establish production memory use.

## Shared implementation and measurement rules

- Preserve the original baseline; write each task's before/after results to new
  files. Record the source revision and any local changes, fixture, interpreter,
  architecture, build options and measurement method.
- Keep the workload fixed within a comparison. Use at least three fresh normal
  processes and three separate traced processes. Run measurements without
  concurrent test or benchmark workloads.
- Report retained Python allocations after collection, allocation peak, current
  and peak RSS, build time, resolution time, and physical versus logical graph
  counts separately. Attribute shared objects once and avoid additive savings
  claims across overlapping representations.
- Preserve registration and occurrence identities, parent context, generic
  bindings, selection order, lifetime/cache/cleanup ownership, and observed
  resolution attribution. Sharing metadata must not share transient instances.
- Preserve public component traversal, explanations, manifests, fingerprints
  and reports. Construct optional inspection views from captured immutable facts;
  never rerun application constructors, template factories or selection callbacks
  to recover omitted evidence.
  Task 05 explicitly relaxes inspection compatibility when `explain_metadata=False`;
  its documented capability boundary applies in that mode. Preserve resolution
  and full-mode inspection, and never reconstruct omitted facts by callback replay.
- Check diagnostics on and off, ordinary and managed providers, maps, scope
  builders/overlays, boundaries and profiling where the change touches them.
  The richer fixture does not cover every library feature by itself.
- Keep ordinary resolution free of new whole-graph traversal or compilation
  work. Measure the cost of inspecting a graph separately if allocation becomes
  lazy, including whether repeated inspection retains new caches.
- For each implementation, run relevant behavioural tests and the repository's
  required checks. Record failures and existing limitations accurately. Mark
  completion only after the acceptance criteria and measurements are recorded.

Example baseline capture for task 01:

```sh
.venv/bin/python -m benchmarks.graph_memory_evidence repeat --routes 8 --repeats 3 --output .work/graph-memory-optimization/evidence/01-before.json
```

The [fixture](../../benchmarks/graph_memory_fixture.py),
[measurement runner](../../benchmarks/graph_memory_evidence.py) and
[integration tests](../../tests/test_graph_memory_fixture.py) are the starting
tools. The [artifact-loading experiment](../../docs/graph-artifact-experiment.md)
remains unfinished and may be dropped; these tasks concern the normal compiler
and runtime graph.

## Task 01 result

[Recorded implementation and evidence](01-result.md): diagnostics-disabled
decorator facts now share captured patterns, with per-occurrence target identities.
Eight-route retained traced allocations decrease from 187.2 to 45.2 MiB; build
time increases from 7.777 to 11.511 seconds. Diagnostic history remains eager.
All 2,055 tests and required checks pass; strict MkDocs retains eight existing
links-to-files-outside-docs warnings. Later task results are recorded below.

## Task 02 result

[Recorded implementation and evidence](02-result.md): frozen occurrences share
eleven captured metadata fields through 116 definitions. Eight-route retained
traced allocations decrease from 45.17 to 38.43 MiB and build allocation peak
from 80.22 to 73.58 MiB. RSS remains effectively unchanged (131.55→132.59 MiB).
Public manifest fingerprints and graph counts match; all 2,070 tests and required
checks pass, with the same existing strict-MkDocs link warnings. Compilation and
inspection observations and limitations are recorded separately. Task 03 is
recorded below; task 04 is recorded below.

## Task 03 result

[Recorded audit and declined experiment](03-result.md): 8,932 records are in
public relationship closure, 50 additional records support runtime/provider roots,
and 79,576 additional records are held by explanation-owner closures. No record
is outside every conservatively protected root. A forwarding selection callback
captures views requiring 600 records outside runtime-root closure at two routes;
the compiler has no escape inventory. Production pruning is therefore declined,
with zero production memory benefit or added runtime/build/inspection cost.
Twelve fresh comparison processes retain 38.43 MiB allocations and 73.58 MiB build
allocation peak with identical production-source hashes and behavior. All 2,079
tests and required checks pass, apart from the same eight existing strict-MkDocs
link warnings. The offline audit costs 0.762 seconds and a separately observed
77.09 MiB temporary allocation peak; it is not integrated into compilation.
Task 04 is recorded below.

## Task 04 result — reverted

The maintainer requested undoing task 04 on 2026-10-09. Its [recorded experiment](04-result.md)
saved 2.66 MiB of retained Python allocations, but process RSS rose about 3.3 MiB
(2.5%), allocation peak increased slightly and graph inspection slowed. This did
not demonstrate a process-memory benefit, so the original KEEP recommendation
was superseded.

The [rollback](04-rollback.md) restores the exact pre-task-04 runtime, memory
runner and schema-5 artifact codec. Tasks 01 and 02, task 03's offline audit and
the richer artifact experiment remain. Task 04's raw measurements are unchanged;
its implementation, tests and probes are archived as inert text for reference.

## Task 05 result — retained

[Recorded implementation and evidence](05-result.md): both builders accept
`explain_metadata=True` by default. Opting out releases explanation/inspection
metadata and 79,576 of 88,558 records while preserving runtime relationships.
Final same-source eight-route Python retention falls 38.43→3.10 MiB, RSS
134.16→129.45 MiB, and allocation peak 73.57→72.84 MiB. Diagnostics-enabled
builds retain the same reduced Python total but still use about 350.84 MiB RSS;
their build allocation peak rises about 3.20 MiB. Future overlays cost about
0.18 MiB; caller-retained snapshots are measured separately. All 2,127 tests,
222 reused reduced-mode execution checks and required CI checks pass, except
strict MkDocs' same eight existing external-file link warnings. Inspection limits,
escaped views, scope modes, ownership and failure evidence are documented.


Task 06's [investigation](06-result.md) locates reduced-mode peak in primary
compilation. Conservative scalar-only weak cache ownership is recommended for a
scoped implementation/review: repeated peak 72.844→52.053 MiB and normal RSS
130.766→106.781 MiB, with unchanged ~3.10 MiB Python retention and graph/activation
counts. Build median rises 7.1%; the three short resolution samples rise 2.410 ms
at the median, so timing needs follow-up before acceptance. Strong fallback
preserves opaque values, map keys and unknown carriers: broad weak caching fails
16 lifetime cases despite passing all 2,132 existing tests. The conservative probe
passes both. Early fact interning avoids 1,695,090 named metadata constructor calls
and lowers build median 40.6%, but has no demonstrated peak-memory benefit.
Smaller drafts and diagnostic history remain unmeasured design opportunities;
coarse fact omission is incompatible. All changes are evidence/tooling, with no
production optimization, commit, or pre-compilation implementation.


## Task 07 result — investigation only

The [result](07-result.md) records source/MRO inventory, independent probes and
five normal/three traced processes per candidate. Effective slots retain weakrefs,
lower traced peak 72.844→71.422 MiB and normal RSS median 130.578→128.812 MiB
(with overlapping RSS ranges), and are ready for scoped implementation/review.
Compact indexes lower peak to 67.851 MiB and RSS to 121.031 MiB, but fail eight
full-artifact cases and need mapping/codec/sparsity design; not ready. Pre-lookup
avoids 25,081 constructors but establishes no peak/RSS/speed benefit. Early draft
sharing remains a bounded feasibility result with unresolved mutation/pool-lifetime
semantics, not an achieved saving. Slots/pre-lookup pass all 2,132 existing tests;
full/reduced attribution/facts and 16 lifetime cases match, and slots checks pass
Python 3.11–3.14. No production/test/benchmark source, commit, push or pre-compilation
implementation is changed.


## Task 08 result — investigation only; refine

The [result](08-result.md) and [inventory](08-inventory.md) record bounded compact
indexes and a direct experimental codec. Reduced peak/RSS decrease
72.844→67.851 MiB / 130.438→119.734 MiB with no established build-time change;
full retention decreases 38.432→33.523 MiB. All eight prior artifact failures are
resolved, all 2,132 tests and focused Python 3.11–3.13 checks pass, and provenance,
callback and lifetime evidence matches. Six stronger custom-hash counterexamples
still fail the measured mapping, including read-only proxy equality. A separate native-
delegation feasibility subclass resolves those cases but is unintegrated/unmeasured.
Sparse-only shallow storage rises 15.3%; full artifact load median rises 8.0% while
load peak/RSS decrease. **REFINE; not ready for implementation** until the complete
adapter and fallback policy are integrated, checked and remeasured. Production,
Task 06 caches, Task 07 layouts and pre-compilation work remain unchanged.

## Task 09 result

[Corrected prototype and final evidence](09-result.md): all six custom-hash
counterexamples, 103 operation/codec-state checks, 2,132 tests and 16 lifetime
cases pass. Focused Python 3.11–3.13 checks pass. The 104-process same-source
matrix shows reduced traced peak 72.844→67.887 MiB and full retained Python
38.431→33.474 MiB; current RSS falls about 9.6–9.7 MiB during compilation.
A bounded fallback keeps sparse/tiny storage at native dictionary plus 72 bytes.
Full artifact load retains 38.060→33.103 MiB and peaks 66.535→60.619 MiB, but
full export/load medians rise ~13% and narrow dense lookup remains ~3× native.
RETAIN the isolated prototype for implementation review; production adoption is
not approved. Production sources and prior evidence are unchanged. Raw repository
lint retains one prior Task 08 E501; a narrowly exempted rerun and other checks pass.
