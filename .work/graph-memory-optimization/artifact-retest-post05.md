# Compiled graph artifact retest after task 05

Date: 2026-10-09\
Status: Retest complete; artifact feature remains an unfinished local experiment.

The user requested a separate-process artifact retest after task 05 introduced
`explain_metadata=False`. The local schema-7 codec now supports the compact
runtime registration carriers and accepts reduced plans. It exports already
pruned graphs and loads them directly, without compilation or pruning on load.
Production compiler/runtime code is unchanged by this retest.

The same eight-route template/decorator/provider/map fixture is measured with
metadata on and off. Each comparison runs three normal and three separately
traced fresh processes for each of compile-only, compile/export and load.
All processes run serially without concurrent tests or benchmark workloads.
Diagnostics and future scope builders are disabled, and no builder or callback
views are retained. Earlier measurements are preserved.

**The reduced artifact gives a material startup-memory benefit in this fixture.**
Compared with compiling the same reduced runtime, loading lowers process peak RSS
by 62.7%, collected current RSS by 62.9%, and preparation time by 99.0%. It avoids
the compilation footprint rather than materially shrinking the already reduced
retained runtime. The full-metadata control shows a much smaller peak-RSS saving.

## Reduced runtime results

[Raw reduced samples](evidence/artifact-post05-reduced.json): three normal and
three separately traced fresh processes for each mode, eighteen processes total.
Python 3.14.4, macOS ARM64. Timing and RSS come from normal processes; traced
allocation figures come from the separate instrumented processes.

| Measurement | Compile reduced runtime | Load reduced artifact |
| --- | ---: | ---: |
| Prepare, including fixture imports | 11.345 s | 0.115 s |
| Current RSS after preparation and collection | 127.83 MiB | 47.39 MiB |
| Process peak RSS through preparation | 127.83 MiB | 47.70 MiB |
| Retained traced Python allocations | 3.098 MiB | 3.012 MiB |
| Peak traced allocations through preparation | 72.842 MiB | 5.943 MiB |
| Resolve complete provider/map workload | 15.28 ms | 13.81 ms |
| RSS with application results retained | 127.83 MiB | 47.61 MiB |
| Retained traced allocations with results | 4.220 MiB | 4.136 MiB |

The reduced artifact contains 30,999 serialized objects and occupies 2,470,435
bytes (2.356 MiB). Export adds a median 0.159 seconds after compilation; exporter
peak RSS is 127.83 MiB. That memory cost remains in the separate build process.

The loader retains almost the same Python data as ordinary reduced compilation.
It avoids the compiler's temporary allocation footprint: peak RSS is about 63%
lower, and traced allocation peak falls from 72.84 to 5.94 MiB. This is a local
synthetic result, not an estimate for a deployed service.

Normal reduced compilation RSS ranges from 127.67 to 130.02 MiB. Loader current
RSS ranges from 47.17 to 47.44 MiB and its peak from 47.47 to 47.75 MiB. Loader
preparation times range from 0.1143 to 0.1161 seconds.

## Full-metadata control

[Raw full samples](evidence/artifact-post05-full.json): another eighteen fresh
processes using the same runtime, codec, fixture and runner sources. Only the
metadata option differs. The full control runs after the reduced group; samples
are not randomized and the operating-system file cache is not flushed.

| Measurement | Compile full runtime | Load full artifact |
| --- | ---: | ---: |
| Prepare, including fixture imports | 11.591 s | 1.195 s |
| Current RSS after preparation and collection | 133.27 MiB | 93.75 MiB |
| Process peak RSS through preparation | 133.27 MiB | 117.95 MiB |
| Retained traced Python allocations | 38.431 MiB | 38.063 MiB |
| Peak traced allocations through preparation | 73.567 MiB | 66.538 MiB |
| Resolve complete provider/map workload | 25.54 ms | 22.10 ms |
| RSS with application results retained | 133.27 MiB | 94.05 MiB |
| Retained traced allocations with results | 39.554 MiB | 39.186 MiB |

The full artifact contains 320,113 serialized objects and occupies 29,484,023
bytes (28.118 MiB). Export adds 1.696 seconds after compilation and reaches a
157.55 MiB peak RSS in the exporter. Full loader current RSS ranges from 93.69
to 94.48 MiB and peak RSS from 117.86 to 118.69 MiB.

Full loading still saves time and current RSS, but reduces startup peak RSS by
only 11.5%. Its decoder must reconstruct substantially more data. Comparing the
two artifact loaders directly, reduced metadata lowers current RSS from 93.75
to 47.39 MiB and peak RSS from 117.95 to 47.70 MiB. Artifact size falls 91.6%.
These results support further investigation of the reduced artifact approach;
they do not remove the experiment's feature and compatibility restrictions.

## Measurement boundary and verification

Preparation includes fixture imports and compilation or loading after common
library/measurement imports. It is not total interpreter startup. RSS is the
whole Python process, not Docker/cgroup memory. Peak RSS is the cumulative process
high-water mark and includes those common imports. Memory snapshots follow
collection, which does not guarantee returning allocator pages to the OS.
Files are loaded after export without clearing the operating-system file cache.

Export happens before application objects are constructed. Separate loader
processes disable builder entry points, compiler construction, legacy registration
construction, dependency inspection and runtime graph/carrier pruning. Template
callbacks and application activations must remain zero through preparation.

After the measured phases, every run verifies the same resolution workload,
activation counts, laziness, lifetimes, managed cleanup, physical links, provider
contexts and shared definitions. Export/load artifact hashes must match. Reduced
mode also checks that metadata entries stay empty and repeated graph access fails
without rebuilding inspection caches. Full mode additionally checks public graph
fingerprints. No public manifest is claimed for reduced mode.

All thirty-six full-size processes passed. Reduced mode retains 8,982 records;
full mode retains 88,558. Both retain 1,765 execution steps and 116 shared
definitions. The [comparison ledger](evidence/artifact-post05-comparison.json)
verifies identical source hashes, resolution signatures, activation counts and
lazy behaviour across all processes, plus matching graph links/counts within
each mode. Full inspection preserves the earlier task-02/task-05 fingerprint.
Production-source hashes match task 05's final measured sources. This
extension only changes the private codec, evidence runner, tests and documentation;
schema 6 was used by the reverted task 04, so the new private schema is 7.

[Full-suite validation](evidence/artifact-post05-tests.json): 2,132 tests passed,
including full/reduced lifetime round trips and independent rich-fixture export
and load. Ruff lint/format, type checking, executable docs and benchmark discovery
also passed. The existing FastAPI/Starlette warning remains. The small two-route
comparison passed all six processes before the full-size runs began.
The [strict documentation check](evidence/artifact-post05-docs-check.json) aborts
with the same eight pre-existing links to files outside the documentation tree;
no new warning was introduced. Report/index file links and whitespace checks pass.

## Reproduction

Build/export and load as two distinct processes:

```sh
.venv/bin/python -m benchmarks.graph_memory_artifact_evidence export --routes 8 --no-explain-metadata --artifact .cache/graph-artifact/post-task05-reduced.jsonl
.venv/bin/python -m benchmarks.graph_memory_artifact_evidence load --routes 8 --no-explain-metadata --artifact .cache/graph-artifact/post-task05-reduced.jsonl
```

Repeat the full reduced comparison:

```sh
.venv/bin/python -m benchmarks.graph_memory_artifact_evidence compare --routes 8 --repeats 3 --no-explain-metadata --artifact .cache/graph-artifact/post-task05-reduced.jsonl --output .work/graph-memory-optimization/evidence/artifact-post05-reduced.json
```

Omit `--no-explain-metadata` and use separate artifact/result paths for the full
control. Preserve the recorded evidence by selecting new result paths for reruns.
Artifacts remain trusted local outputs tied to exact source, Python and imported
module versions. Existing exclusions remain: instances, slots, warmups, boundaries,
pre-configurations, arbitrary callbacks/factories and general generic support.
The artifact feature remains unfinished and is not a supported production API.
