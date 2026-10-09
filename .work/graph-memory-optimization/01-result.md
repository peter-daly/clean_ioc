# Task 01 result — compact decorator-selection facts

Completed: 2026-10-08\
Implementation agent: GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning\
Decision: Retain the scoped implementation for its measured memory benefit;
review the build and inspection cost before adopting it for latency-sensitive compilation.

## Implementation and compatibility

With diagnostics disabled, completed decorator explanations share an immutable
pattern containing every captured decision and template field except target
occurrence identity. Each occurrence stores that identity and its captured path.
The interning key includes subject, selected/rejected ordering, outcomes, reasons,
origins, template/source/target registration identities, bindings, boundaries and
preference metadata. It shares evidence, never instances or callback evaluations.

`CompiledGraph.explain_decorators` constructs its existing public representation
from these facts on request, with no retained explanation cache. Provider views
remap the stored target identity into their contextual occurrence. Clone remapping
keeps the shared original pattern, and explanations with multiple template targets
retain the eager implementation. All predicates, factories and position callbacks
are still evaluated by the existing compiler code; neither resolution nor
inspection reconstructs facts by replaying application code.

Diagnostics-enabled explanations remain eager. Diagnostic history and selection
census currently deduplicate by explanation object identity. Compacting that
representation would change census attribution unless the identity contract were
also redesigned, so that work is outside this narrow implementation. This task
therefore claims a memory improvement only with diagnostics disabled. The initial
clone-only approach did not address the richer fixture's main allocation source;
repeated compilation required interning completed captured facts as well.

## Measurement method and preserved baseline

The original `benchmarks/graph_memory_results.json` was preserved. The new
[before samples](evidence/01-before.json) reproduce the additional object census
in three fresh normal processes and three separate traced processes. Their
[source ledger](evidence/01-before-source.json) records revision
`31f1682075b2c146de7672fa37cb5fb563a0ffc7`, local changes and source hashes.
The [after samples](evidence/01-after.json) record the same metadata per process;
all six after samples have identical source hashes, and the fixture hash matches
the before ledger. All measurements used eight routes, diagnostics disabled,
Python 3.14.4, macOS ARM64 and the unchanged resolution workload. No tests or
other benchmark workload ran concurrently. Allocation tracing began before
fixture import; retained allocations were observed after collection. Object
census, topology walking and inspection occurred outside build/resolution intervals.

The evidence runner subsequently gained public traversal counting and an
inspection-only eager-reference switch. These additions do not change measured
build/resolution work. Reproduction:

```sh
.venv/bin/python -m benchmarks.graph_memory_evidence repeat --routes 8 --repeats 3 --output .work/graph-memory-optimization/evidence/01-new-after.json
.venv/bin/python -m benchmarks.graph_memory_evidence measure --routes 8 --inspection --eager-decorator-facts --output .work/graph-memory-optimization/evidence/01-new-eager-inspection.json
.venv/bin/python -m benchmarks.graph_memory_evidence measure --routes 8 --inspection --output .work/graph-memory-optimization/evidence/01-new-after-inspection.json
.venv/bin/python -m benchmarks.graph_memory_evidence measure --routes 2 --diagnostics --inspection --output .work/graph-memory-optimization/evidence/01-new-diagnostics-inspection.json
```

The eager-reference flag disables pattern capture and compact clone remapping
only in the evidence process. It recreates the eager representation for inspection
comparisons; it is not a runtime build option. The recorded original six-process
before result was obtained before modifying library code.

## Results

Medians from the six-process before/after comparison:

| Measurement | Before | After |
| --- | ---: | ---: |
| Fixture import, composition and build | 7.777 s | 11.511 s |
| Resolution workload | 0.0802 s | 0.0255 s |
| Current RSS after build | 277.2 MiB | 135.3 MiB |
| Peak RSS through build | 277.2 MiB | 135.3 MiB |
| Current / peak RSS after resolution | 277.2 / 277.2 MiB | 135.3 / 135.3 MiB |
| Retained traced allocations after build | 187.2 MiB | 45.2 MiB |
| Traced allocation peak through build | 222.7 MiB | 80.2 MiB |
| Retained traced allocations after resolution | 188.3 MiB | 46.3 MiB |

Retained traced allocations decrease 75.9%, RSS decreases 51.2%, and allocation
peak decreases 64.0%. Build time increases 48.0%. The measured resolution time
is lower, but ordinary resolution code is unchanged; these small synthetic
samples do not establish a general runtime speedup.

The same 88,558 physical records, 1,765 distinct execution steps, 50 provider
view contexts, record kinds, activation kinds and metadata-entry counts remain.
Separate public traversal counts agree at 8,932 `graph.walk()` visits, including
contextual views. Public visits, physical stored records and distinct executable
steps are different counts. This task removes no graph records.

The additional shallow object census is identity-deduplicated:

| Retained evidence | Before | After |
| --- | ---: | ---: |
| Explanation objects, including shared source patterns | 56,522 | 56,565 |
| Decision objects | 565,220 | 430 |
| Template-fact objects | 565,220 | 430 |
| Selected/rejected tuples | 56,923 | 60 |
| Distinct captured patterns | — | 43 |
| Combined shallow explanation/decision/template/tuple storage | 139.7 MiB | 3.1 MiB |

All logical facts remain: 792 selected, 564,428 rejected, including 564,372
`template-target-not-selected` and 56 `decorator-filter-rejected`. Stored-object
outcome counts differ because shared objects are counted once; the runner also
reports logical outcome/reason counts by explanation entry. The
[comparison ledger](evidence/01-comparison.json) verifies logical outcomes and
reasons, every other recorded graph count and resolution validation against the
original before samples. Shallow storage is not additive with traced allocations
or RSS and is not a promise of recoverable process memory.

All processes validate 124 distinct transient workers, 248 wrappers, 7,812 tree
objects, 26 managed scopes, singleton policies, ordinary scoped identity and
64 async source-map calls. Template callback counts are unchanged.

## Inspection costs and cache retention

Inspection runs use separate fresh processes, with tracing begun after build,
resolution and the object census. Each explanation sample covers the first 128
eligible public components (1,280 decisions at eight routes), rather than every
stored explanation. These are single-process observations, not three-repeat
medians or production latency estimates.

| Eight-route public explanation sample, under tracing | Eager reference | Compact |
| --- | ---: | ---: |
| First 128 explanations | 74.7 ms | 100.9 ms |
| Repeated 128 explanations | 0.6 ms | 28.5 ms |
| Retained allocation after first sample | 527,712 bytes | 527,712 bytes |
| Retained allocation after repeated sample | 528,296 bytes | 528,296 bytes |

The increased repeated-access cost pays for uncached public materialization.
Initial retained allocation comes from existing graph-membership inspection
caches; the repeated 584-byte difference is measurement bookkeeping. Compact
explanation objects retain no new materialized cache.

At two routes with diagnostics enabled, the original
[before inspection](evidence/01-before-inspection.json) and
[after inspection](evidence/01-after-diagnostics-inspection.json) observed full
public selection-census access at 135.2/86.3 ms and 137.9/86.6 ms
(first/repeated). Both retained exactly 1,252,200 bytes after first census and
1,253,208 bytes after repeated census; diagnostic explanations stay eager.
Selection census continues to require diagnostics when called publicly.

Eight-route inspection files are [eager](evidence/01-eager-inspection.json) and
[compact](evidence/01-after-inspection.json). Their absolute RSS includes the
preceding census and traversal; use the six-process build samples for retained
build-memory comparison.

## Verification and limitations

- 2,055 tests pass, including three added tests for eager/compact equivalence,
  all captured fields and complete richer-fixture public provider-view facts.
- Existing suites cover diagnostics on/off, template provenance and bindings,
  overlap/order, callbacks, explanation errors, validation, selection census,
  reports, boundaries, overlays, providers/maps and profiling.
- Ruff lint, repository formatting, type checks, docs examples and benchmark
  discovery pass. The test suite has one existing FastAPI/Starlette deprecation warning.
- Strict MkDocs still fails on the same eight pre-existing links to files outside
  `docs`; no new warning was introduced.
- No 32-route retry was attempted after the earlier greater-than-4-GiB failure.
  No production-memory or wider-platform performance claim is made.
- Diagnostic history remains eager; build cost and repeated explanation access
  are the material tradeoffs. Tasks 02–04 remain planned and untouched.

The implementation is complete and ready for review, uncommitted. Keep the
memory-focused change if the recorded compilation and inspection costs are
acceptable for the intended workload; do not present it as a universal speed
optimization.
