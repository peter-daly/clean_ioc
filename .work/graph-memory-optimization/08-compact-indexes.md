# 08 — Investigate compact indexes

Created: 2026-10-09\
Status: Complete — investigation only; REFINE\
Assignment: GPT-6.1 Sol (`gpt-6.1-sol`), high reasoning\
Agent: `/root/graph_memory_task_08`\
Starting revision: `7b9a841`\
Prerequisites: Task 07's compact-index probe, measurements and compatibility findings\
Implementation readiness: Not ready — native mapping delegation needs integration and remeasurement; artifact failures resolved

## Outcome and scope

Determine whether compact origin and decorator-explanation indexes can retain
task 07's memory savings while preserving mapping behaviour, graph evidence and
experimental artifact round trips at an acceptable time cost. Produce a measured
retain, refine or drop recommendation and a bounded implementation proposal.

This is investigation only. Use isolated probes; leave shared production sources
unchanged at completion. The maintainer assigned GPT-6.1 Sol with high reasoning
on 2026-10-09. Production implementation and commits remain outside this
assignment. Do not combine this work with task 06's cache changes or task
07's slots proposal, or expand the parked pre-compilation feature work.

Read the [shared plan](README.md), [task 07 result](07-result.md) and
[inventory](07-inventory.md). The starting revision records those investigations;
production sources still match their `d51b6f5` baseline.

## Starting evidence

Task 07 used five fresh normal processes and three separately traced processes
on Python 3.14.4, macOS ARM64, with the rich eight-route fixture. Diagnostics,
explanation metadata, scope builders and profiling were disabled; callers retained
no inspection views. Its index probe produced these medians:

| Measurement | Baseline | Compact-index probe |
| --- | ---: | ---: |
| Build time | 12.248 s | 12.503 s |
| Retained traced Python memory | 3.099 MiB | 3.099 MiB |
| Traced build peak | 72.844 MiB | 67.851 MiB |
| Current / peak process RSS | 130.578 MiB | 121.031 MiB |
| Final records / execution steps | 8,982 / 1,765 | 8,982 / 1,765 |

The observed savings are compilation savings: 4.993 MiB traced peak and
9.547 MiB RSS, with about 2.1% longer builds. Reduced-mode runtime retention did
not improve because these metadata indexes are already released after building.
These synthetic measurements do not establish production application savings.

- The origin dictionary contains 88,558 keys but only 45 distinct origin values;
  its shallow backing storage is 5,242,960 bytes. Sharing values further is not
  equivalent to removing index overhead.
- The decorator-explanation dictionary has 56,522 keys spanning IDs 1–88,507,
  inserted out of numeric order; its backing storage is 2,621,528 bytes.
- The prototype uses a positive-ID reference list, an insertion-order key list
  and a sparse fallback dictionary. Offline storage accounting is promising,
  but conversion temporarily retains both representations.
- Eight artifact tests fail because the experimental codec requires read-only
  mapping proxies to be backed by dictionaries. Other semantic checks passing
  does not remove this incompatibility.
- Numeric-equivalent keys differ: a dictionary populated with key `1` can be
  read with `1.0`, while the prototype misses that lookup. Mutation during
  iteration and deletion behaviour also need review.
- Isolated `.get` measurements were roughly five times slower. Those are narrow
  microbenchmarks; the integrated build cost above is the relevant starting
  observation, not a prediction that every operation becomes five times slower.

## Investigation areas

### 1. Establish the mapping contract and its readers

- Trace all writers, readers and read-only wrappers of the two indexes through
  compilation, finalization, failed builds, inspection and artifact export/load.
  Distinguish private usage from publicly observable mapping behaviour.
- Compare missing-key handling, `get`, membership, equality, iteration order,
  updates, deletion/reinsertion, keys/values/items views, live versus snapshot
  wrappers and mutation during iteration. Cover equivalent numeric keys such as
  `1`, `True` and `1.0`, and relevant subclasses/custom keys.
- Preserve the existing observable contract. An integer-only internal API may
  be explored, but must have an explicit boundary and adapter design; silently
  narrowing a mapping's supported behaviour is not a compatible optimization.
- Preserve source attribution, callback-visible components, build-rule evidence,
  manifests, census, fingerprints, explanations and budget/failure witnesses.
  Origin cannot simply be inferred from a shared definition: aliases, boundaries
  and graph layers can give otherwise shared content different provenance.

### 2. Compare bounded storage representations

- Refine the prototype or compare alternatives, measuring origins alone,
  decorator explanations alone and both where useful to isolate costs.
- Cover dense and gapped positive IDs, out-of-order insertion, negative provider
  IDs, very large IDs, inherited graphs and separate graph namespaces. Bound
  sparse-array growth and account for fallback storage and retained capacity
  after deletion. Do not renumber occurrences or merge graph identities.
- Measure direct construction, conversion overlap, lookup and iteration costs.
  Preserve sharing of origin values and count each shared referent once. Report
  shallow storage as accounting evidence, not as total recoverable RSS.

### 3. Restore experimental artifact compatibility

- Identify and resolve all eight task 07 artifact failures. Audit the codec's
  dictionary-backed `MappingProxyType` assumption and preserve shared backing
  identity when several wrappers refer to one index.
- Avoid solving export by retaining duplicate full dictionaries throughout
  compilation or loading. Measure any materialization/conversion peak as well
  as artifact size, export time and fresh-process load time/memory.
- Check full and reduced artifacts, inspection after loading, resolution and
  malformed/unsupported representations. Unsupported encoding should fail
  before an artifact is reported as successfully published.
- This is the existing private, source-coupled experiment, currently schema 7.
  If a candidate changes its representation, explicitly regenerate experimental
  artifacts and record compatibility limits. Do not build a production artifact
  format or migration framework as part of this investigation.

## Measurement and verification

- Capture a fresh same-source baseline and preserve the original task 07 data.
  Use new `08-*` evidence files with source/probe hashes, interpreter, platform,
  fixture, flags and caller ownership recorded.
- Run at least three fresh normal and three separate traced processes per
  candidate, serially without competing workloads. For a promising candidate,
  use at least five normal runs to assess the small observed timing penalty.
  Prepare probe source/import machinery outside the measured process; task 07's
  earlier in-process source compilation materially distorted memory readings.
- Report retained Python memory after collection, traced allocation peak,
  current/peak RSS, build and cold-resolution time, physical/logical graph counts
  and index capacity separately. Report export/load measurements separately too.
- Start with the unchanged rich eight-route workload, then cover full metadata,
  diagnostics, failed builds and inspection. Add focused sparse/ordering fixtures
  and scaling checks so dense synthetic IDs do not hide a regression.
- Verify providers/maps, aliases/generics, scopes/overlays, boundaries, warmup and
  profiling wherever readers are affected. Preserve callback counts/order and
  application-value lifetimes; reuse task 06's lifetime counterexamples where
  relevant. Never replay callbacks to reconstruct omitted evidence.
- Run focused mapping counterexamples, artifact round trips and applicable
  repository checks for retained executable probes. Do not modify expectations
  merely to accept the prototype's known failures. Planning edits need no tests.

## Deliverables and acceptance

- [x] A source-backed reader/contract inventory defines the compatibility boundary.
- [x] Candidate storage is bounded for sparse, negative and very large IDs, while
  preserving occurrence identity, order and exact provenance.
- [x] Mapping counterexamples and all eight artifact failures are resolved for
  any candidate recommended for implementation; unresolved changes are marked
  not ready with concrete follow-up questions.
- [x] Repeated comparable measurements establish whether the memory benefit
  survives compatibility fixes and quantify build, lookup, inspection and
  export/load costs. No combined savings are inferred from independent probes.
- [x] A reproducible `08-result.md` records retain/refine/drop, implementation
  readiness, remaining design decisions and supported-version limitations.
- [x] Update the task index with the outcome and leave production sources
  unchanged. A negative result is an acceptable investigation outcome.

## Recorded outcome

The [result](08-result.md) and [inventory](08-inventory.md) record the completed
investigation. The measured candidate retains peak/RSS savings after numeric/view
and artifact fixes: reduced traced peak 72.844→67.851 MiB, normal RSS
130.438→119.734 MiB; full retention 38.432→33.523 MiB. All 2,132 tests,
18 artifact cases, attribution/lifetime checks and focused Python 3.11–3.13 checks
pass. However six stronger custom-hash counterexamples remain, including public
proxy equality. An unmeasured native-delegation refinement resolves those focused
cases, but is not integrated or approved. Sparse-only storage costs 15.3% more at
100,000 entries; full artifact load costs about 8% more. **REFINE; not ready for
implementation.** Acceptance is satisfied by measured evidence and explicitly
recorded unresolved compatibility/readiness, rather than adoption of a failing
candidate. Production sources and earlier evidence remain unchanged; no commit/push.

## Starting points

- [Task 07 probe](evidence/07-probe.py) and
  [mapping checks](evidence/07-mapping-checks.py).
- [Compiler and graph readers](../../clean_ioc/container.py).
- [Artifact codec](../../benchmarks/graph_artifact.py) and
  [artifact tests](../../tests/test_graph_artifact_experiment.py).
- [Memory fixture](../../benchmarks/graph_memory_fixture.py) and
  [measurement runner](../../benchmarks/graph_memory_evidence.py).
