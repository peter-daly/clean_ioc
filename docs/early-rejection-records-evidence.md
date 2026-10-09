# Early rejection record allocation evidence — 8 October 2026

This is the first sequential runtime-memory change after optional compiler diagnostics.
Ordinary `build(diagnostics=False)` now allocates no component draft, frozen record, origin
sidecar or candidate wrapper for a definition whose structured `candidate_when` policy
returns a definite early false. The excluded subtree was already skipped; this change
also removes its rejected occurrence. `diagnostics=True` retains the previous complete
rejected occurrence and decision history, including failed-build partial evidence.

The compiler still evaluates policies in declaration order, updates the invariant-subplan
safety proof before exclusion, charges preparation operations and records considered,
evaluated and excluded candidate counters. Physical occurrence counters and occurrence
budgets charge only allocations actually made. The full logical depth checks for compiled
targets and provider views are unchanged. Roots with only early exclusions retain their
automatic empty provider collections, for every public provider family and collection form.

## Fresh-process isolated comparison

`benchmarks/early_rejection_records_evidence.py` creates sender-specific transport candidates,
each using `candidate_when=cf.parent(cf.with_id(sender_id))`, plus shared infrastructure.
Builder composition precedes tracing. Retained heap is measured after compiler completion
and garbage collection; graph manifests, source fingerprints and runtime resolution follow
tracing. Each row uses fresh processes with the same Python environment. The baseline is
the prior development wheel, SHA-256
`4e0d2fd53eafcfc9d03837b58b6f2d59e0d14c88e1405a0240b22dd7174d7749`.
The candidate is the current source. Sanitized samples, Python/platform metadata, source
fingerprints and separate profiler counts are in
[`early_rejection_records_results.json`](https://github.com/peter-daly/clean_ioc/blob/version2/benchmarks/early_rejection_records_results.json).

| Senders | Baseline off records | Candidate off records | Views, both | Baseline off retained bytes | Candidate off retained bytes | Baseline off peak bytes | Candidate off peak bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 312 | 256 | 128 | 1,546,829 | 1,530,757 | 1,824,559 | 1,808,338 |
| 32 | 2,016 | 1,024 | 512 | 2,985,651 | 2,588,776 | 3,340,712 | 2,943,760 |
| 64 | 6,080 | 2,048 | 1,024 | 5,810,366 | 3,989,056 | 6,247,903 | 4,426,294 |

The 64-sender fixture saves **4,032 actual records**, **31.35% retained traced heap** and
**29.16% traced peak** in this fresh-process pair. Diagnostic mode retains 312 / 2,016 /
6,080 records in both revisions; its retained and peak allocations remain effectively equal
within ordinary measurement noise. All four mode/revision combinations have matching
semantic graph fingerprints and resolved transport types at each size. Instrumented elapsed
times and process high-water RSS are raw probe metadata, not startup acceptance evidence.

Separate 64-sender profiling verifies unchanged semantic work: 4,225 definitions considered,
4,096 early eligibility evaluations, 4,032 early exclusions, 193 candidate compilation attempts,
129 parameter processing attempts, 386 selection callback calls, 130 compiled registration
subplans and 63 invariant cache hits. Physical records fall from 6,080 to 2,048; physical
records plus view contexts fall from 7,104 to 3,072. Retained early rejection records fall
from 4,032 to zero. The comparison removes allocations rather than hiding counts.

Reproduce against any installed source or extracted wheel with that package first on
`PYTHONPATH`:

```console
PYTHONPATH=. .venv/bin/python benchmarks/early_rejection_records_evidence.py --routes 64 --heap
PYTHONPATH=. .venv/bin/python benchmarks/early_rejection_records_evidence.py --routes 64 --heap --diagnostics
PYTHONPATH=. .venv/bin/python benchmarks/early_rejection_records_evidence.py --routes 64 --profile
```

## Actual Cop application comparison

Both stages used the same Cop source snapshot and environment, with installed development
dependency wheels and no dependency source overrides. The unchanged Bark wheel SHA-256 is
`047d046561f219b331cd812feb2c52fe9883de070226e1b4ed602222012bf758`.
The step 1 Clean IoC wheel SHA-256 is
`3dd1855e4df932af7f7fb5ad79c80918462997b9e9935054a71ec8b441594947`;
the baseline wheel is identified above. The Cop source snapshot hash is
`c67f1ef4c2aed3e1af389a71060ed6f7dbd63f8d699580e215f4c64c2d4afe99`.
Sanitized provenance manifests and every raw sample are included in the
`application_comparison` section of the results JSON; local paths and settings values are omitted.

Three fresh uninstrumented processes per application/stage used alternating paired stage
order: baseline/step 1, step 1/baseline, baseline/step 1. All builds used default diagnostics.
Build elapsed time begins after imports and configuration construction; process high-water
RSS can include earlier allocations. These are Python 3.14.4 / macOS 26.7.1 ARM64 results.

| Application | Baseline records | Step 1 records | Views, both | Baseline median build | Step 1 median build | Baseline peak RSS range | Step 1 peak RSS range |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| API | 11,910 | 10,032 | 3,220 | 0.76572 s | 0.73924 s | 235.20–252.66 MiB | 234.30–236.25 MiB |
| Worker | 91,570 | 66,225 | 4,220 | 5.40759 s | 5.21569 s | 408.75–437.05 MiB | 396.125–496.031 MiB |

The worker removes **25,345 physical records** and the API removes **1,878**. The worker
RSS ranges overlap and the candidate's worst observed peak is higher: these samples
**do not establish a reliable Cop RSS reduction**. The separate retained-heap comparison
below provides direct allocation evidence.

A separate fresh worker process per stage started tracing after imports and configuration
construction and included builder composition plus compilation. Retained heap was measured
after garbage collection. This scope differs from the synthetic fixture, whose builder was
composed before tracing.

| Worker allocation measurement | Baseline | Step 1 | Saved | Reduction |
| --- | ---: | ---: | ---: | ---: |
| Traced retained after GC | 68,233,327 bytes | 53,074,157 bytes | 15,159,170 bytes | 22.217% |
| Traced peak | 199,227,060 bytes | 187,140,166 bytes | 12,086,894 bytes | 6.067% |

Instrumented elapsed times and process RSS remain raw probe metadata and are not ordinary
build performance measurements. These development-wheel checks do not change releases,
dependency pins, locks, deployment limits or timeouts. Full installed-wheel Bark unit checks
passed 5,941 tests with 26 existing skips in 96.27 seconds; Cop unit checks passed 494 tests
in 38.00 seconds. This step has no new Cop
integration or constrained Linux startup acceptance result.

## Deliberate compaction boundary

Late-rejected and intermediate occurrences remain retained in both modes. A late `when`,
request filter or preference callback can inspect the completed subtree and retain its
immutable `Component`; deleting that record would invalidate the escaped component and
its relationships after a successful build. Shared executable registration steps and
runtime argument providers also retain occurrence-specific `Component` or `DependencyContext`
references which need not match the selected occurrence shown in a graph traversal. Parent
singleton anchors, overlay clones, decorator cores and ownership links add further executable
relationships. Selecting only visible graph roots is therefore not a proof that other
records are unreferenced. This step makes no general late/intermediate reclamation claim;
a future change needs an explicit escape/reference proof and complete executable closure.

## Verification

Focused tests bound actual `_draft` calls and frozen physical records at 2 / 4 / 8 / 16 / 32
senders in both modes, and bound retained/peak allocation savings. Additional regressions
cover empty automatic provider collections after all early exclusions, rejected contextual
alternatives invalidating unsafe invariant reuse, escaped late-rejected components, full
failed-build evidence, and truthful occurrence-budget admission. Existing focused suites
cover required root validation, unknown/opaque callback order, generic fallbacks, aliases,
boundaries, all provider forms, ownership, cleanup and overlays.

The complete `make ci` passed: **1,858 tests**, the existing FastAPI deprecation
warning, Ruff lint/format checks, type checks, documentation examples and benchmark
discovery. The four focused suites passed **186 tests** before that full check.

Application measurements and constrained Linux startup are separate downstream checks;
this synthetic evidence does not establish either application acceptance or deployment limits.
