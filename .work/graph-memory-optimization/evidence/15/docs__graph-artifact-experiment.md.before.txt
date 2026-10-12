# Local compiled graph artifact experiment

**Status: unfinished experiment, not ready for production; may be dropped.**

Retained as a local proof of concept and benchmark only. The initial constructor-only
experiment saved about 0.62 seconds, with similar retained memory and higher startup
peak memory. A subsequent retest after graph-memory tasks 01 and 02 includes the
richer template/provider workload; see `.work/graph-memory-optimization/artifact-retest.md`
in the repository. There is no commitment to shipping an artifact-loading API or
maintaining this artifact format.

The retest after task 05 adds reduced-metadata artifacts. Its results are recorded
in `.work/graph-memory-optimization/artifact-retest-post05.md`. The local schema-7
codec supports both full and reduced fixture plans; it does not change production
compiler or runtime code.

For the subsequent memory investigation with decorator/registration templates,
providers and maps, see the [richer graph fixture](graph-memory-fixture.md).
The historical measurements below remain specific to the original constructor-only
fixture before those optimizations.

This prototype exports an unresolved Clean IoC compiled plan, then loads it into a
real `Container` in a fresh Python process. It lives under `benchmarks/`; it adds
no public Clean IoC API and does not change the compiler or runtime.

The question is whether moving compilation out of the application process reduces
startup time and peak memory **while preserving the existing compiled graph**.
This first experiment does not try to design a smaller runtime representation.

## Local results, 8 October 2026

The separate-process round trip works, including imports, shared identities,
resolution, and graph inspection. For this workload loading is faster, with
similar retained memory, but **higher startup peak memory** in the current JSON
format. Moving compilation out of the application process has not yet delivered
the hoped-for peak-memory reduction.

Measured on macOS 26.7.1, ARM64, CPython 3.14.4, using artifact schema 3. Values
below are medians of three fresh-process runs per mode; Python allocation figures
come from three additional instrumented runs per mode.

| Measurement | Compile normally | Load artifact |
| --- | ---: | ---: |
| Prepare the container | 1.526 s | 0.911 s |
| Process peak RSS through preparation | 81.95 MiB | 95.75 MiB |
| Current RSS after preparation and collection | 78.95 MiB | 76.77 MiB |
| Retained traced allocations after preparation | 26.76 MiB | 26.32 MiB |
| Peak traced allocations through preparation | 36.04 MiB | 50.68 MiB |
| Resolve all 65,536 objects | 0.079 s | 0.081 s |
| Current RSS with all resolved objects retained | 85.00 MiB | 83.42 MiB |
| Retained traced allocations with resolved objects | 35.34 MiB | 34.91 MiB |

Export writes a 17.98 MiB artifact containing 170,188 serialized objects. It adds
1.122 seconds after compilation and reaches a median 108.62 MiB process peak in
the exporter. That cost belongs to the build process, not the separate loader.

All 18 runs passed topology, activation-count, and graph-fingerprint checks.
Loading ran with compilation and dependency inspection disabled. This demonstrates
technical feasibility, but does not establish a compelling production benefit:
the full runtime graph still occupies memory and decoding creates temporary
structures. Reducing that decoding peak or exploring a smaller runtime
representation remain possible investigations, not committed follow-up work.

Raw samples: [graph_artifact_results.json](https://github.com/peter-daly/clean_ioc/blob/version2/benchmarks/graph_artifact_results.json).

## Run locally

From the repository root, export and then load in separate processes:

```sh
.venv/bin/python -m benchmarks.graph_artifact_evidence export --roots 256
.venv/bin/python -m benchmarks.graph_artifact_evidence load --roots 256
```

The default artifact is `.cache/graph-artifact/graph.jsonl`, in an already ignored
directory. Both commands also resolve all roots and validate the resulting
objects. The export happens **before** those objects are constructed, so no
application instances are saved in the artifact.

Run the repeatable comparison:

```sh
.venv/bin/python -m benchmarks.graph_artifact_evidence compare --roots 256 --repeats 3 --output benchmarks/graph_artifact_results.json
```

This launches 18 fresh processes: three repetitions of compile-only, compile plus
export, and load, first without instrumentation and then with `tracemalloc`.
Each export is immediately followed by loading that artifact. The runner requires
matching graph fingerprints and validates the resolved object topology. Normal
timing/RSS and traced allocation results are kept separate.

Use `--roots 512` for 131,072 component records. Use `--artifact PATH` to keep a
different artifact, and `--heap` on an individual command for traced allocations.

## Workload

`benchmarks/graph_artifact_fixture.py` defines importable classes at module import.
It does not register services or create service instances until explicitly asked.
There are seven binary branching levels over a leaf, plus a root: 256 component
occurrences per root. With 256 roots this gives:

- 65,536 frozen component records.
- 65,536 service objects when every root is resolved (all are transient).
- 32,768 leaf objects, each allocating a 128-byte payload, totalling 4 MiB of
  payload data plus Python object and allocation overhead.

Only 264 types are registered for this case. Repeated subtrees exercise the
compiler's existing plan sharing; the larger occurrence graph remains present.
This is a controlled synthetic workload, not a simulation of every feature or
import in data-protection-cop or Polaris.

Compilation uses `diagnostics=False`, `provider_roots=()`,
`allow_scope_builders=False`, `check_unreachable=False`, and
`aggregate_errors=False`. Both paths retain the same fields, including component
records, executable steps, registration dependency metadata, root selection maps,
and available inspection metadata.

## Artifact and imports

`benchmarks/graph_artifact.py` writes an object table as JSON Lines, preserving
shared references. Each record refers only to objects written earlier. Loading
streams these records and reconstructs the allowlisted internal objects without
calling their compiler constructors. The reference table is released when loading
returns. Large individual dictionaries still have a temporary JSON representation;
this is not a zero-allocation or memory-mapped format.

Numeric occurrence IDs also use shared references. Treating them as inline JSON
numbers creates a new Python integer at each use on load, needlessly increasing
retained memory across the many maps, parent links, and dependency links.
Read-only mapping views preserve their shared backing dictionaries too. The
experimental exporter uses `gc.get_referents` to find that dictionary, and rejects
views for which this shape is unavailable; this has been verified on CPython.

Classes and supported functions are stored as module and qualified-name references.
Loading eagerly imports those modules and reconnects the Python objects. No Python
bytecode, live container caches, service instances, or pickle payloads are stored.
The synthetic classes are generated deterministically when their module imports;
they have stable module attributes that the loader can find.

The artifact records the schema, Python implementation and exact version, and a
hash of the current Clean IoC Python sources, codec source, and dependency lockfile.
Referenced modules also have source hashes. This intentionally couples artifacts
to the local build; regenerate them after relevant changes. It is not a portable
or supported release format. Load only trusted build outputs: importing their
referenced modules runs normal Python import code. The artifact and these checks
are not a security boundary or a complete transitive dependency fingerprint.

The first supported subset is constructor registrations with the four ordinary
lifetimes. The schema-5 local retest extends this to the richer fixture's compiled
decorator pipelines, captured template decisions, literal value steps, four provider
forms, provider-map steps, provider view contexts and shared component definitions.
Provider and `Mapping` type aliases reconnect through their imported origins and
arguments. The two built-in `with_id`/`with_name` predicates used by retained
metadata have explicit data encodings; arbitrary closures remain unsupported.
Template factories do not run on load, and no executable closure or bytecode is saved.

Instance registrations, slots, warmups, boundaries, pre-configurations, arbitrary
factories/callbacks and general generic-alias support remain outside this experiment.
Unsupported values fail export rather than falling back to rebuilding a registry.
The extension is scoped to these local fixtures, not a general persistence contract.

The richer fixture can be compiled/exported and loaded in separate processes:

```sh
.venv/bin/python -m benchmarks.graph_memory_artifact_evidence export --routes 8 --artifact .cache/graph-artifact/rich-graph.jsonl
.venv/bin/python -m benchmarks.graph_memory_artifact_evidence load --routes 8 --artifact .cache/graph-artifact/rich-graph.jsonl
```

Its `compare` mode performs three repetitions of compile/export/load in fresh
processes, then repeats separately with allocation tracing. It verifies matching
artifact hashes for every export/load pair, graph fingerprints, metadata-sharing
counts and the complete provider/map resolution workload. Compilation and dependency
inspection are disabled during loading; template callback counts must remain zero.

## What is measured

- `prepare_seconds`: compile or load, including fixture imports, after common
  Clean IoC/measurement module imports. This is not total interpreter startup.
- `prepared`: current RSS and process peak RSS after preparation and collection.
- `export_seconds` and `exported`: additional artifact-writing cost, recorded only
  in export runs.
- `resolved`: memory after all roots are resolved and all returned objects are
  retained. Resolution time is recorded separately.
- `traced_retained_bytes` and `traced_peak_bytes`: allocation measurements from
  separate instrumented runs, beginning before fixture import and preparation.

RSS is the entire Python process, not container/cgroup memory. Peak RSS is the
process high-water mark up to that observation, and cannot be reset between phases.
Garbage collection does not guarantee that Python returns freed pages to the OS.
Validation of the object topology and generation of graph manifests run after
memory/timing observations to avoid including their extra allocations.

## Verification

```sh
.venv/bin/pytest -q tests/test_graph_artifact_experiment.py
```

The tests cover importable graph reconstruction, complete manifest equality,
shared registration/root/graph identity, the four lifetimes across scopes and
resolutions, asynchronous resolution, and no construction during loading. They
also cover unsupported instances/local classes, stale and incomplete artifacts,
invalid references, and independent export/load processes. Loading is tested with
builder, compiler, and dependency-inspection entry points replaced by functions
that raise if called. The evidence runner applies the same guard to its load path.

Repository validation: all 2,043 tests pass, along with Ruff lint/format checks,
type checking, documentation example validation, and existing benchmark discovery.

Task 04's schema-6 subtree representation was reverted. Schema 7 extends the
restored schema-5 codec with task 05's compact runtime registration carriers and
permits `explain_metadata=False`. Reduced graphs are pruned during compilation
before export; loading reconstructs that smaller plan directly. Compilation,
dependency inspection and runtime-pruning entry points are disabled in the
fresh-process load checks. Existing exclusions remain, including diagnostics,
future scope builders, slots and warmups.

Run the reduced eight-route comparison with:

```sh
.venv/bin/python -m benchmarks.graph_memory_artifact_evidence compare --routes 8 --repeats 3 --no-explain-metadata --artifact .cache/graph-artifact/post-task05-reduced.jsonl --output .work/graph-memory-optimization/evidence/artifact-post05-reduced.json
```

Use `export` and then `load` instead of `compare` for the two independent steps;
pass `--no-explain-metadata` to both. Omit the flag for the full-metadata control.
Reduced mode has no public graph manifest. The runner verifies the stored runtime
links, sharing/census counts and complete resolution workload instead, and checks
that inspection remains disabled without reconstructing metadata. It verifies
the exported artifact hash in every separate loader process.
