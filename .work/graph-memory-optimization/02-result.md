# Task 02 result — shared component definitions

Completed: 2026-10-08\
Implementation agent: GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning\
Decision: Retain the narrow representation split for its measured reduction in
retained Python allocations and build allocation peak. Process RSS did not improve.

## Reassessment and representation

The post-task-01 eight-route graph still contains 88,558 records, with 256 bytes
of shallow storage each. The [baseline census](evidence/02-before.json) found
31,311 identity patterns across twelve candidate metadata fields, including
31,026 different synthetic value IDs. Retaining registration identity on each
occurrence reduces the remaining metadata to just 116 patterns. IDs identify
registrations and synthetic records; they need not prevent sharing identical
captured metadata. They continue to drive the same runtime attribution and caches.

The [field census](evidence/02-contextual-field-census.json) records identity
variation for all 27 draft fields, by kind, after the split. Definition counts are:

| Kind | Physical occurrences | Shared definitions |
| --- | ---: | ---: |
| Registration | 56,506 | 34 |
| Value | 31,026 | 1 |
| Decorator | 792 | 2 |
| Ordinary provider | 168 | 27 |
| Managed provider | 50 | 36 |
| Provider map | 16 | 16 |

For example, registration records retain 56,506 occurrence identities, 16,777
parent referents, 43,571 dependency tuples, three cache/cleanup owner categories
and four ownership-reason referents. These contextual facts remain per occurrence,
even when metadata happens to repeat in this fixture.

`_ComponentDefinition` captures eleven fields: service type, implementation,
implementation type, lifespan, name, tags, build arguments, kind, activation,
boundary and declared service spelling. Equivalence requires identical referents
for each field, with identical tag referents in identical order. This is stricter
than application equality. Generic specializations, derived argument mappings,
boundaries and aliases must therefore match exactly before sharing occurs.
Sharing does not infer equivalence from registration IDs or implementation types.

The key contains only built-in integer identities and tuples of those integers.
It invokes no application equality, hashing, repr, constructor, template factory
or selection callback. Definitions retain every referenced object, preventing
identity reuse while the interning dictionary exists. The index is local to one
graph freeze and is cleared afterward; graphs retain no definition index or
process-global definition cache. Ordered immutable tag containers may share,
while each captured tag object is preserved.

`_ComponentRecord` has eighteen slots, including its definition pointer. It keeps
registration and occurrence identities, async/cleanup flags, cache/cleanup owner
categories, owner identity and reason, provider mode, position, argument, all
relationships and the lazy generic-mapping slot. No override dictionaries or
new containers for absent metadata are introduced. Existing public properties
forward through the record to the captured definition. Resolution steps,
instance caches and cleanup machinery are unchanged; transient instances are
never shared by this representation.

Lazy generic-map initialization remains on each occurrence. Typetoolbox already
interns some `GenericTypeMap` objects; the existing library behavior is preserved,
including deferred initialization of each occurrence's cache slot. Provider views
and escaped predicate snapshots preserve contextual links and ownership, and
frozen view replacements still reset their generic-map cache as before.
Decorator position previews now replace their captured definition separately
from their contextual record. The private, source-coupled artifact experiment
recognizes the new definition class and advances its schema to 4; no artifact
loading feature was added.

## Measurement method and source state

The original `benchmarks/graph_memory_results.json` and all task 01 evidence are
preserved. [Before](evidence/02-before.json) and [after](evidence/02-after.json)
each contain three fresh normal processes and three separate traced processes,
run serially without concurrent tests or other benchmarks. The fixture, eight
routes, diagnostics-disabled options and resolution workload are unchanged.
Tracing starts before fixture import, and retained memory is observed after
collection. Census, validation and inspection stay outside build/resolution
intervals. These samples used Python 3.14.4, macOS ARM64.

The [comparison ledger](evidence/02-comparison.json) records revision
`31f1682075b2c146de7672fa37cb5fb563a0ffc7`, local changes, before/after source hashes
and additional hashes for the artifact adapter and new tests. All six processes
within each comparison group have identical source hashes. The fixture hash
matches between groups. The evidence runner gained a definition census and
separate public traversal/manifest observations; these additions occur outside
the measured build and resolution workloads. Task 01 and earlier fixture work
remain uncommitted and preserved alongside this task.

Reproduction:

```sh
.venv/bin/python -m benchmarks.graph_memory_evidence repeat --routes 8 --repeats 3 --output .work/graph-memory-optimization/evidence/02-new-after.json
.venv/bin/python -m benchmarks.graph_memory_evidence measure --routes 8 --inspection --output .work/graph-memory-optimization/evidence/02-new-inspection.json
.venv/bin/python -m benchmarks.graph_memory_evidence measure --routes 2 --diagnostics --inspection --output .work/graph-memory-optimization/evidence/02-new-diagnostics-inspection.json
PYTHONPATH=. .venv/bin/python .work/graph-memory-optimization/evidence/02-freeze-profile.py .work/graph-memory-optimization/evidence/02-new-freeze.json
PYTHONPATH=. .venv/bin/python .work/graph-memory-optimization/evidence/02-field-census.py .work/graph-memory-optimization/evidence/02-new-field-census.json
```

The recorded before files were captured before changing library code. The
commands above reproduce the current representation; they do not restore the
original representation or overwrite recorded before samples.

## Results

Medians from the six-process comparison:

| Measurement | Post-task-01 baseline | Task 02 |
| --- | ---: | ---: |
| Fixture import, composition and build | 11.520 s | 11.291 s |
| Resolution workload | 26.81 ms | 24.33 ms |
| Current / peak RSS after build | 131.55 / 131.55 MiB | 132.59 / 132.59 MiB |
| Current / peak RSS after resolution | 131.55 / 131.55 MiB | 132.59 / 132.59 MiB |
| Retained traced allocations after build | 45.17 MiB | 38.43 MiB |
| Traced allocation peak through build | 80.22 MiB | 73.58 MiB |
| Retained traced allocations after resolution | 46.30 MiB | 39.55 MiB |

Retained build allocations decrease 14.9% and allocation peak decreases 8.3%.
RSS increases 0.8% in these samples: Python allocation savings did not translate
into returned process pages. Before normal-process RSS ranges from 131.45 to
134.55 MiB and after from 132.27 to 133.03 MiB. Build and resolution medians are
slightly lower, but these synthetic samples do not establish a general speedup.

Shallow storage counts every definition once:

| Storage | Before | After |
| --- | ---: | ---: |
| Occurrence records | 22,670,848 bytes | 15,586,208 bytes |
| Shared definitions | 0 | 13,920 bytes (116 objects) |
| Retained definition interning index | 0 | 0 |
| Combined records and definitions | 22,670,848 bytes | 15,600,128 bytes |
| Record index | 5,242,960 bytes | 5,242,960 bytes |

The net shallow reduction is 7,070,720 bytes (6.743 MiB), after counting new
definitions. This overlaps the traced allocation improvement and must not be
added to it. Relationships, integer storage, origin indexes, execution objects
and decorator evidence counts/storage are unchanged. Physical records remain
88,558, distinct execution steps 1,765, public traversal visits 8,932 and provider
view contexts 50. This task prunes no records or repeated subtrees.

A separate two-route freeze observation resets the tracing peak immediately
before each graph freeze, capturing the actual phase high-water mark, including
its temporary interning storage. It is a single process per representation,
not an eight-route median. The largest graph has 2,368 records in both cases:

| Largest two-route freeze, under tracing | Before | After |
| --- | ---: | ---: |
| Freeze time | 52.6 ms | 47.2 ms |
| Retained allocations before freeze | 2,409,474 bytes | 2,401,629 bytes |
| Retained allocations immediately after freeze | 2,428,482 bytes | 2,240,693 bytes |
| Allocation peak during freeze | 2,550,090 bytes | 2,447,853 bytes |

[Before](evidence/02-before-freeze.json) and [after](evidence/02-after-freeze.json)
retain every freeze sample and the preceding build high-water mark. This profiler
is separate from the main measurements and intentionally resets peaks; use the
six-process results for whole-build allocation peaks.

## Inspection and compatibility

Separate fresh eight-route [before](evidence/02-before-definition-inspection.json)
and [after](evidence/02-after-inspection.json) runs trace inspection only after
build, resolution, validation and census. Each explanation pass covers 128
components and 1,280 decisions. Traversal accesses all twelve public identity /
definition properties on every visit; manifests cover all roots.

| Single traced inspection observation | Before | After |
| --- | ---: | ---: |
| First / repeated explanation sample | 100.8 / 27.8 ms | 99.6 / 28.4 ms |
| First / repeated public traversal | 91.8 / 90.8 ms | 94.7 / 101.7 ms |
| First all-roots manifest construction | 547.8 ms | 609.9 ms |
| Repeated cached manifest access | 0.009 ms | 0.028 ms |

Definition access adds property indirection. These single-process measurements
show its inspection tradeoff but do not establish stable latency percentages.
All first/repeated retained allocation observations match byte-for-byte between
representations. The existing manifest cache retains about 13.5 MiB in this
inspection; task 02 adds no inspection cache. Both manifest passes in both runs
have the same fingerprint:
`fa06427a9c823d18961ba2d173294ce206f38c516f2478dd229e7d1bebaaa722`.
The [diagnostics-enabled two-route inspection](evidence/02-after-diagnostics-inspection.json)
also completes without rerunning callbacks. Task 01's eager diagnostic history
and compact diagnostics-disabled facts remain intact.

The comparison ledger verifies identical validation results, activations, lazy
activation counts, callback counts, equivalence patterns and all other graph
counts/storage. The workload continues to validate 124 transient workers, 248
wrappers, 7,812 tree objects, 26 managed scopes and 64 async source-map calls,
plus singleton and ordinary scoped identity.

## Verification, limitations and task boundary

- All 2,070 tests pass. Fifteen new cases cover each definition equivalence
  condition, hostile equality/hash/repr objects, ordered tags, independent graph
  caches, contextual ownership/relationships, generic specializations/laziness,
  escaped callback snapshots and provider-view replacements.
- Existing suites cover runtime filters, diagnostics on/off, manifests, semantic
  fingerprints, reports, ordinary/managed providers and maps, scope builders,
  overlays, boundaries, ownership/cleanup and observed resolution/profiling.
- Ruff lint/format checks, type checks, documentation examples and benchmark
  discovery pass. The existing FastAPI/Starlette deprecation warning remains.
- Strict MkDocs still fails on the same eight existing outside-docs links.
- No production, cross-platform, RSS reduction or general speed claim is made.
  Sharing is deliberately identity-conservative; workloads with few repeated
  metadata patterns can pay for many definitions and may gain less or use more
  memory. Optional callback snapshots without a graph freeze index do not intern
  definitions. Neither the graph index nor draft representation was redesigned.
- No 32-route retry, commit, push, deployment, or task 03–04 implementation was
  performed. Tasks 03 and 04 remain planned.

The implementation is complete and uncommitted. Keep it for the demonstrated
Python allocation benefit, with the recorded process-memory and inspection limits.
