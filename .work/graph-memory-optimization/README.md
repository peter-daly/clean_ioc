# Graph memory optimization

The [artifact retest](artifact-retest.md) compares compilation/export and fresh-process
loading after tasks 01 and 02, using the richer fixture. It is a separate local
experiment and does not implement tasks 03 or 04.

Created: 2026-10-08\
Status: Tasks 01 and 02 retained; 03 pruning declined; 04 reverted on 2026-10-09.

Reduce the memory retained by the compiled output graph while preserving
resolution, ownership, filtering, inspection and diagnostic behaviour. Measure
compilation peak memory and build time alongside retained memory. These four
tasks follow the investigation using the large graph fixture with registration
templates, decorator templates, providers and maps.

## Tasks and recommended order

| ID | Task | Status | Starting point |
| --- | --- | --- | --- |
| 01 | [Compact and share decorator-selection facts](01-compact-decorator-selection-facts.md) | Complete | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](01-result.md) |
| 02 | [Separate component definitions from occurrences](02-share-component-definitions.md) | Complete | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](02-result.md) |
| 03 | [Audit and prune discarded compilation records](03-prune-discarded-records.md) | Complete — pruning declined | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](03-result.md) |
| 04 | [Share repeated subtrees through contextual views](04-share-contextual-subtrees.md) | Reverted — dropped | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](04-result.md), [rollback](04-rollback.md) |

Start with 01 and record its result before continuing. The remaining order is a
recommendation; reassess it against the measured graph after each task. A task
may conclude that a proposed optimization is unsafe or not worthwhile; record
that outcome and its evidence instead of forcing an implementation.

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
