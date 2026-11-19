# Large graph memory fixture with templates and providers

This fixture extends the local memory investigation beyond the constructor-only
binary tree. It compiles and resolves templates, named services, deferred
dependencies, and provider-map fanout through the normal Clean IoC API. It does
not register instances or require scope/container slots.

The earlier [artifact experiment](graph-artifact-experiment.md) remains unfinished
and may be dropped. Its fixture and measurements remain available as a simpler
baseline; the richer fixture does not extend that experimental serialization format.

## Dependency shapes

In this table, an arrow means “depends on”, not “generates”.

| Template | Source of expansion | Resulting dependency |
| --- | --- | --- |
| Registration template | Each named `RouteSource` | Generated `Worker` → that exact source |
| Registration template | Each named `RouteSource` | Source → generated `RouteDependency`, selected by exact parent registration ID |
| Decorator template | Two singleton `Policy` registrations | Two ordered worker wrappers → their exact policies |
| Decorator template | Each generated `Worker` registration | Matching endpoint wrapper → provider for that exact worker |

The second registration template reverses the first dependency direction without
creating a cycle: `Worker → RouteSource → RouteDependency`.

Each endpoint has an injected `Provider[Worker]`, `AsyncProvider[Worker]`,
`ManagedProvider[Worker]`, and `AsyncManagedProvider[Worker]`. The fixture also
declares those four public provider root forms and invokes them through named
root selection. Managed acquisition creates a fresh scope; workers are transient,
sources and state are scoped, and policies are singletons.

There are two injected maps:

- `Mapping[str, Provider[Worker]]`, populated by generated registrations through
  a `ProviderMapGroup` contribution.
- `Mapping[str, AsyncProvider[RouteSource]]`, keyed from source registration names.

Every endpoint invokes every map key, producing fanout across routes. Acquiring
the endpoint and its maps must not construct a worker or its tree.

Each worker also owns a transient binary tree with five branching levels:
63 objects, including 32 leaves with 128-byte payloads. The tree makes retained
object memory visible while templates and providers add distinct execution and
selection paths. This remains a controlled synthetic workload, not a substitute
for an application measurement.

## Recorded results

Measured on 8 October 2026 with eight routes, Python 3.14.4, macOS 26.7.1 and
ARM64. These are medians of three fresh normal processes and three separate
allocation-traced processes. The repository file `benchmarks/graph_memory_results.json`
contains every raw sample and its graph census.

| Measurement | Result |
| --- | ---: |
| Fixture import, composition and build | 7.630 s |
| Complete resolution workload | 0.080 s |
| Process RSS before fixture import | 40.3 MiB |
| Process RSS after build | 276.2 MiB |
| Process peak RSS through build | 276.2 MiB |
| Process RSS after resolution | 276.2 MiB |
| Traced Python allocations retained after build | 187.2 MiB |
| Traced Python allocation peak through build | 222.7 MiB |
| Traced Python allocations retained after resolution | 188.3 MiB |

The untraced post-build RSS ranged from 273.1 to 276.8 MiB. Traced allocation
figures exclude the common library imports and are collected in different
processes from RSS/timing figures; they should not be subtracted from each other.
In this workload, retained build state dominates the additional allocations made
by resolving the application objects.

All six processes produced the same census and resolution checks:

- 88,558 physical graph records and 50 provider view contexts.
- 1,765 distinct execution steps, including 32 provider-map steps and 50 managed-provider steps.
- 43 distinct registration objects retained by execution steps and 240 compiled decorator helpers.
- 56,522 retained decorator-explanation entries, with diagnostics disabled.
- 124 resolved workers with 248 wrappers and 7,812 distinct tree objects.
- 26 fresh managed scopes and 64 async source-map calls, alongside one ordinary scope.

The record objects themselves occupy 21.6 MiB of shallow storage. The record
index and origin index each occupy 5.0 MiB, relationship tuples 2.5 MiB, and
occurrence integers 2.4 MiB. These figures identify structures to investigate;
they neither account for all retained allocations nor establish which structures
can safely be removed. This is a different workload from the earlier plain tree,
so its figures are not an optimization before/after comparison.

## Run locally

From the repository root:

```sh
.venv/bin/python -m benchmarks.graph_memory_evidence measure --routes 8
.venv/bin/python -m benchmarks.graph_memory_evidence measure --routes 8 --heap
.venv/bin/python -m benchmarks.graph_memory_evidence repeat --routes 8 --repeats 3 --output benchmarks/graph_memory_results.json
```

The default is eight routes. `--routes` accepts 1–128; the requested dependency
shape includes quadratic map fanout, and compilation can grow more steeply as
template candidates interact. A first 32-route run exceeded 4 GiB current RSS
before completion and was stopped. That observation is not a completed benchmark
or a claim about an application. Start small when increasing the route count.
`--diagnostics` enables full diagnostic capture for a separate comparison.
`repeat` launches separate normal and traced processes for each repetition and
requires their graph counts and resolution checks to agree.

Build options are `allow_scope_builders=False`, `check_unreachable=False`, and
`aggregate_errors=False`. Diagnostics default to false. The four worker provider
forms are explicitly requested; injected maps and providers are compiled as usual.

## Measurements and checks

Normal samples report build time, resolution time, current process RSS and process
peak RSS. Separate `tracemalloc` samples report Python allocation peaks and retained
allocations. Measurements begin before fixture import/composition, after common
library and measurement imports. Collection occurs before retained snapshots.
Compilation never activates application constructors.

The resolved snapshot retains all returned workers, endpoint objects and map
results. The ordinary scope is still open; managed acquisition scopes have closed.
These objects have no external resources or I/O. Full tree validation and graph
census run after memory/timing snapshots, so their sets and indexes do not inflate
the recorded measurements. Resolution timing includes lightweight laziness guards
and bookkeeping that keeps results alive; it is not a resolution microbenchmark.

The census counts physical graph records, provider view contexts, execution step
types, distinct compiled steps and registrations, decorator pipelines, and retained
metadata. Object identities are deduplicated when counting shared storage, including
read-only views of the same origin dictionary. Shallow structure sizes exclude
referenced objects and allocator overhead; they are neither total RSS nor a promise
of recoverable memory. View-expanded occurrences are not counted as physical records.

The integration checks exercise:

- Exact source and parent binding in both registration-template directions.
- Decorator order and singleton policy identity across ordinary and managed calls.
- Generated registrations serving as decorator-template sources.
- Lazy provider/map acquisition, all map keys, and all four provider forms.
- Scoped identity, fresh managed scopes, transient worker/tree identity, and closed-scope rejection.
- No template callback re-execution during resolution and no instance registrations.
- Ordinary and diagnostic builds, scaling, invalid sizes, and fresh-process measurement.

```sh
.venv/bin/pytest -q tests/test_graph_memory_fixture.py
```

Repository sources: `benchmarks/graph_memory_fixture.py`,
`benchmarks/graph_memory_evidence.py`, and `tests/test_graph_memory_fixture.py`.
