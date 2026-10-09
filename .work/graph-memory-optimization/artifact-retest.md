# Compiled graph artifact retest after tasks 01 and 02

Date: 2026-10-08\
Status: Retest complete; local artifact feature remains an unfinished experiment.

The user requested a fresh test with compilation/export and artifact loading in
separate processes after the first two graph-memory optimizations. This retest
uses the eight-route template/decorator/provider/map fixture so that both
optimizations participate. It also repeats the original constructor-only case
as a control. Tasks 03 and 04 remain planned.

## Method

The compiler creates an unresolved container and exports its frozen plan to a
JSON Lines artifact. A different Python process imports the referenced modules,
loads the plan and resolves the same workload. It has builder compilation,
compiler construction, legacy registration construction and dependency inspection
replaced with functions that fail if invoked. Load-time template callback and
application-constructor counts must be zero.

Compile-only, compile/export and load are measured separately. Each mode runs in
three fresh normal processes for timing/RSS and three additional processes for
Python allocation tracing. Processes run serially, with no concurrent tests or
other benchmark workloads. Measurements include fixture imports and preparation
after common library/measurement imports, not full interpreter startup. The OS
file cache is not cleared between runs; loading follows export.

Post-build and post-load snapshots follow garbage collection. The resolved
snapshot retains all application results and the ordinary scope; managed
acquisition scopes have closed. Topology checks, census and manifest generation
happen after memory/timing snapshots. Process peak RSS is cumulative, so the
exporter's high-water mark includes compilation and export; it does not belong
to the separate loader. Traced allocations and RSS are measured in different
processes and must not be subtracted from each other.

Every export/load pair must have identical artifact SHA256, graph fingerprint,
physical/semantic graph counts, shared-definition and decorator-fact counts, and
resolution validation. The rich workload checks both template dependency
directions, decorator order, all four provider forms, both maps, scoped/singleton
identity and transient object uniqueness. Source hashes and local Git state are
stored with each rich sample. Earlier task and artifact evidence is preserved.

## Local prototype extension

The previous codec handled only the constructor tree. Schema 5 adds explicit
allowlisted records for the richer fixture's compiled decorators, provider steps,
maps, view contexts, compact explanation patterns and fixed/selected argument
metadata. Shared definitions from task 02 remain shared through the object table.
Provider/Mapping aliases reconnect imported Python types. The two built-in
`with_id`/`with_name` predicates are encoded as factory names plus scalar arguments;
their callable code and captured structure are checked on export. Arbitrary
closures, Python bytecode, service instances and live runtime caches are not saved.

This changes only the experimental codec, measurement harness, tests and reports.
It introduces no new public API or compiler/runtime optimization. Instances,
slots, warmups, boundaries, pre-configurations and general arbitrary callback or
generic support remain outside the prototype. Artifacts remain tied to the exact
source, Python and local build; they are trusted local outputs.

## Reproduction

Build/export and load as two independent steps:

```sh
.venv/bin/python -m benchmarks.graph_memory_artifact_evidence export --routes 8 --artifact .cache/graph-artifact/post-task02-rich.jsonl
.venv/bin/python -m benchmarks.graph_memory_artifact_evidence load --routes 8 --artifact .cache/graph-artifact/post-task02-rich.jsonl
```

Capture repeated comparisons without overwriting the original evidence:

```sh
.venv/bin/python -m benchmarks.graph_memory_artifact_evidence compare --routes 8 --repeats 3 --artifact .cache/graph-artifact/post-task02-rich.jsonl --output .work/graph-memory-optimization/evidence/artifact-post02-rich.json
.venv/bin/python -m benchmarks.graph_artifact_evidence compare --roots 256 --repeats 3 --artifact .cache/graph-artifact/post-task02-tree.jsonl --output .work/graph-memory-optimization/evidence/artifact-post02-tree.json
```

## Results

### Richer graph after tasks 01 and 02

[Raw samples](evidence/artifact-post02-rich.json): three fresh normal and three
fresh traced processes per mode, eighteen processes in total. Python 3.14.4,
macOS 26.7.1 ARM64, artifact schema 5. Values are medians; timing comes only from
normal processes.

| Measurement | Compile normally | Load artifact |
| --- | ---: | ---: |
| Prepare container, including fixture imports | 11.666 s | 1.185 s |
| Process peak RSS through preparation | 132.73 MiB | 118.11 MiB |
| Current RSS after preparation and collection | 132.73 MiB | 93.92 MiB |
| Retained traced allocations after preparation | 38.43 MiB | 38.06 MiB |
| Peak traced allocations through preparation | 73.58 MiB | 66.53 MiB |
| Resolve full provider/map workload | 26.0 ms | 20.3 ms |
| RSS with all resolution results retained | 132.73 MiB | 94.19 MiB |
| Retained traced allocations with results | 39.55 MiB | 39.18 MiB |

Loading saves 10.48 seconds (89.8%) of preparation time in this workload.
Post-preparation RSS is 38.81 MiB lower (29.2%), while process peak RSS is
14.63 MiB lower (11.0%). The normal compile RSS samples range from 131.42 to
133.03 MiB; loader post-preparation RSS ranges from 92.56 to 94.28 MiB.

The retained Python allocation difference is only 0.37 MiB (1.0%). The loaded
graph preserves the same structure and sharing; loading has not made the graph
substantially smaller. The different RSS despite comparable live allocations is
consistent with avoiding compilation's temporary allocation history. It is not
evidence of a correspondingly large reduction in live Python graph data.

Export writes 29,484,007 bytes (28.12 MiB) containing 320,113 serialized objects.
In the separate exporter, compilation takes a median 11.406 seconds and writing
adds 1.679 seconds. Its process peak reaches 156.30 MiB; its traced allocation
peak reaches 85.41 MiB. Those export costs are outside the application loader.

All eighteen runs preserve 88,558 physical records, 1,765 distinct execution
steps, 116 shared component definitions, 430 retained decorator decisions and
430 template facts. They produce the same graph fingerprint and resolve 124
workers, 248 wrappers and 7,812 tree objects with 26 managed scopes and 64 async
source-map calls. All six loaders have zero template callbacks, compilation
disabled, and the exact SHA256 of their preceding export.

### Original constructor-only control

[Raw samples](evidence/artifact-post02-tree.json): another eighteen separate
processes, with the same three-normal/three-traced repetitions per mode, source
state, interpreter and host. This is the original 256-root, 65,536-object workload.

| Measurement | Compile normally | Load artifact |
| --- | ---: | ---: |
| Prepare container | 1.424 s | 0.690 s |
| Process peak RSS through preparation | 76.05 MiB | 90.47 MiB |
| Current RSS after preparation and collection | 76.05 MiB | 71.48 MiB |
| Retained traced allocations after preparation | 21.78 MiB | 21.35 MiB |
| Peak traced allocations through preparation | 31.09 MiB | 45.71 MiB |
| Resolve all 65,536 objects | 74.4 ms | 75.2 ms |

The original workload still saves less than a second (0.73 s), with similar
retained memory and higher loading peak memory. Its artifact is now 15,938,450
bytes (15.20 MiB), with 170,452 serialized objects. Export adds a median 0.918
seconds and reaches a 100.80 MiB exporter peak RSS. All eighteen samples have
matching graph fingerprints and valid resolution topology, with compilation
disabled in the six loaders.

The earlier pre-optimization result was 1.526 s compiling versus 0.911 s loading,
and 26.76 versus 26.32 MiB retained traced allocations. These historical values
come from the original schema-3 experiment, not a source-controlled A/B rerun.
The new control preserves its qualitative conclusion: modest startup savings,
nearly equal live graph memory, and a decoding peak above compilation.

### Interpretation

The richer workload now demonstrates a material local startup-time improvement
and lower loader RSS/peak RSS. Retained Python graph memory is almost unchanged.
The prototype merits further investigation but remains experimental: this is a
synthetic local ARM64 measurement with warm filesystem caches, not application
startup evidence from production.

The initial artifact experiment used a different, constructor-only workload.
There is no before-task-01/02 artifact comparison for the richer fixture, so the
new loading advantage cannot be attributed solely to those two optimizations.
The plain-tree control above provides the closer comparison to the old test.

## Verification

All 2,073 tests pass, including three new checks for full richer-graph metadata
and provider lifetime equivalence, independent export/load processes with zero
load-time template callbacks, and rejection of arbitrary predicate closures.
Ruff lint, formatting, type checks and documentation examples pass. Strict MkDocs
reproduces the same eight pre-existing links to files outside the docs directory.
The original constructor-only artifact tests remain intact. All 36 full-size
measurement processes completed with matching fingerprints and valid resolution;
the preliminary two-route six-process comparison also passed. Compiler/runtime
implementation is unchanged from the completed tasks 01 and 02. All changes and
new evidence remain local and uncommitted.
