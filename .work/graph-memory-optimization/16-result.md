# Task 16 — direct detached snapshot freezing

Root acceptance: scoped KEEP for CPU/churn after source, ownership, evidence and final quality review. Broader snapshot sharing remains DROP.

Status: complete — scoped KEEP for CPU/construction churn, pending root acceptance.

**KEEP** direct draft-to-snapshot freezing as a small construction/build-time
improvement. **DROP** broader frozen-record reuse and persistent snapshot
structures for this workstream: task 14 already shares definitions, memory peaks
are unchanged, and additional cache/ownership complexity has no demonstrated
benefit. The scoped candidate constructs each draft-backed callback record directly with
its decorator pipeline hidden. Previously it froze a record then immediately
copied that unpublished record to clear `decorator_ids`. This avoids one temporary
record per connected draft visited without changing the published snapshot.

[The inventory](16-inventory.md) records source snapshots, generated target views,
position previews, generic caches and escape/last-owner paths. Existing frozen
records and contextual projections retain their previous copying behavior. Task
14 already provides immutable definition sharing, so there is no new definition
memo, persistent snapshot dictionary, graph back reference or lifetime policy.

Only `clean_ioc/components.py` changes in production. The default freeze path
retains decorator pipelines, including final runtime/analysis graphs. Generated
target snapshots remain detached, complete connected views with hidden pipelines.
All callback invocation, failure/retry, boundaries, provider projection and
transient sharing semantics remain unchanged. No task 17 pruning, task 04 subtree
sharing, task 07 slots, artifact representation change or precompilation feature
is included.

## Evidence boundaries

All 45 task 15 accepted source/harness hashes matched before editing. The initial
dirty diff, original components/container/fixture/runner copies and source identity
are saved under `evidence/16/`. Prior accepted tasks and the consumer validation
fix remain intact. HEAD is `34d1ea0`, branch `version2`, version `2.0.0rc4`.

The unchanged task 12 harness runs public run and rich-rule run at eight routes,
analysis at two routes, three fresh normal and three separate traced processes
each. Verified task 15 AFTER is the baseline; it is an earlier measurement, not
an interleaved contemporary control. Runtime source, fixtures and harness stay
frozen during the exclusive serial interval. Platform: Python 3.14.4, macOS ARM64.
No caller-held builder or callback snapshots exist in the main controls.

Bounded retained-snapshot comparisons use symmetric captured/current source
loaders before measurement and identical imports, three normal plus three traced
processes per policy and mode. Per-repeat order alternates BEFORE/AFTER then
AFTER/BEFORE. Constructor/live censuses and phase observers are separate from both
measurement grids. No instrumented census timing is treated as an optimization.

## Main marginal measurements

[Raw AFTER](evidence/16/after.json), [medians and ranges](evidence/16/comparison-summary.json)
and [verification](evidence/16/evidence-validation.json) preserve the complete results.

| Control | Build seconds, before → after | Retained traced MiB | Peak traced MiB | Current / peak RSS MiB |
| --- | ---: | ---: | ---: | ---: |
| Run, 8 routes | 6.1647 → 5.7548 | 3.1113 → 3.1103 | 40.8139 → 40.8126 | 90.172 / 90.172 → 90.438 / 90.438 |
| Rich-rule run, 8 routes | 9.0308 → 8.5683 | 3.1106 → 3.1105 | 254.0879 → 254.0876 | 312.266 / 314.938 → 308.031 / 312.031 |
| Analysis, 2 routes | 0.2967 → 0.2749 | 6.4373 → 6.4376 | 7.5880 → 7.5877 | 49.500 / 49.500 → 49.391 / 49.391 |

Build medians decrease **6.65%, 5.12% and 7.33%** respectively. Before/after build
ranges are 6.148–6.203 / 5.717–5.805 s; 8.961–9.034 / 8.523–8.811 s; and
0.2926–0.2996 / 0.2741–0.2777 s. Traced peak changes are only −1,344, −336 and
−337 bytes. **There is no meaningful demonstrated peak or retained-memory
reduction.** The RSS changes do not establish a general process-memory saving.
These synthetic local measurements are a construction-churn/build-time result.

Every sample matches callback/activation results, discovery, retained graph
inventory and execution/topology counts. Both run controls retain 8,982 physical
records, 116 definitions, 1,765 execution steps and 51 selected registrations.
Analysis retains 2,685 physical runtime records; its separately retained source
graphs are included in the all-live census below.

Resolution workload medians are 14.158→14.205 ms (+0.33%) in run,
14.728→15.024 ms (+2.01%) in rich-rule run and 2.676→2.643 ms (−1.23%) in
analysis. Rich-rule ranges are 14.683–14.852→14.912–16.367 ms, which do not
overlap. This additional signal must carry into task 18's alternated fresh-process
cold/steady checks; absence of a resolution code change does not dismiss it.

## Created, live and retained populations

The [separate census](evidence/16/census-summary.json) observes constructors and
destructors without retaining their objects. Its instrumentation is excluded from
all measured timing and byte totals above.

| Population | Run/rich before | Run/rich after | Analysis before | Analysis after |
| --- | ---: | ---: | ---: | ---: |
| Records created | 194,306 | 102,490 | 12,079 | 7,463 |
| Maximum live records | 10,674 | 10,674 | 2,847 | 2,847 |
| Records live after build + GC, all graphs | 8,982 | 8,982 | 2,847 | 2,847 |
| Generated-target snapshots created | 400 | 400 | 30 | 30 |
| Maximum live target snapshots | 2 | 2 | 2 | 2 |
| Target snapshots retained after build | 0 | 0 | 0 | 0 |
| All graphs created / maximum live | 427 / 29 | 427 / 29 | 39 / 11 | 39 / 11 |
| All graphs retained after build | 1 | 1 | 9 | 9 |

The large controls avoid **91,816 record constructors (47.25%)**, exactly one for
each of their 91,816 published connected-snapshot records. Analysis avoids 4,616
(38.22%). No published records or graph walks are removed. Drafts, definitions
and final execution carriers are unchanged: large builds create 90,250 drafts
(maximum 88,558 live) and 304 definitions (maximum 288 live, 116 retained).
Small analysis creates 2,847 drafts and 84 definitions, retaining 80 definitions
across all nine graphs. Its extra eight source graphs contain 162 records.
All observed graph, draft, definition and record populations release after runtime
teardown in the census. This is cumulative construction avoidance, not recovery of
91,816 simultaneously live objects.

The [phase observer before](evidence/16/phases-before.json) and
[after](evidence/16/phases-after.json) identify the same peak-bearing phases.
Primary compilation's preceding segment peak is 39,791,672→39,791,165 bytes;
runtime-closure freezing within the first retention pass is higher, at
42,572,231→42,571,732 bytes.
Unlike the older task 06 source, this current optimized source's primary segment
is no longer the largest observed segment. Segment high-water marks are separate
and never summed. This observer has its own import/instrumentation boundary, so
its absolute peaks do not replace the unchanged shared harness's whole-build
measurements. It shows no meaningful phase peak reduction from task 16.

## Escaped views and later inspection

[The bounded comparison](evidence/16/escaped.json) and
[summary](evidence/16/escaped-summary.json) retain **193 views, 129 graphs,
194 distinct records and 131 definitions** in every sample. The views comprise
one source, 64 target snapshots, 64 position previews and 64 position target
Components. Preview graphs already share their target records; summed dictionary
entries would double-count them. All modes/policies invoke one source filter,
64 target predicates and 64 position callbacks.

| Bounded control | Run before → after | Analysis before → after |
| --- | ---: | ---: |
| Build median ms | 31.871 → 31.392 | 32.664 → 32.192 |
| First late inspection median ms | 0.726 → 0.698 | 0.731 → 0.709 |
| Repeated inspection median ms | 0.567 → 0.571 | 0.582 → 0.570 |
| Retained bytes after build | 362,570 → 362,688 | 788,907 → 788,529 |
| Whole-build traced peak bytes | 1,700,890 → 1,701,016 | 1,813,752 → 1,813,059 |
| Retained bytes after runtime release, snapshots held | 253,398 → 253,516 | 239,433 → 239,181 |

First/repeated inspection result lists each contribute about 60.5 KB to measured
retention on both policies; they are deliberate caller-owned outputs. Neither
inspection raises the build high-water mark, and no callback replays. Differences
of hundreds of bytes and microseconds in this small fixture are not meaningful
memory or latency gains. Saved views still work after runtime release; clearing
them releases **all graphs and records** in all 24 processes. This establishes
bounded ownership and no retained graph-history chain or delayed allocation burst.

## Verification and final source

- Full Python 3.14.4 `make ci` passes: lint, formatting, type checks, **2,401 tests**,
  executable documentation and benchmark discovery. The existing Starlette warning
  remains. Strict MkDocs and `git diff --check` pass.
- **15 new tests** cover every captured field, single-record draft snapshots,
  subsequent draft/parent mutation, frozen/projection generic-cache states and
  bindings, public run/analysis source/target/position escapes, callback exceptions,
  failed builder retries, boundary and inherited singleton overlay context.
- **248 focused tests** pass on Python 3.14 and 3.13. Python 3.11 and 3.12 each
  pass **245**, with the existing three TypeVar-default cases correctly skipped
  because they require 3.13. No assertion was weakened. Existing task 14 hostile
  values, exact tag identity, definition/pool owner and release tests are included.
- The focused suite includes all 18 parked artifact tests. Record representation
  and codec source/schema are unchanged; no artifact performance rerun or public
  artifact surface expansion is warranted by this record-construction-only change.
- Main outputs/source identity, all 24 bounded samples, six constructor censuses
  and both phase samples are preserved and checked. Runtime and shared harness
  still match their frozen measurement manifest.

Initial failed checks are retained: a generic identity assertion incorrectly
assumed typetoolbox returned distinct maps, and the first bounded harness used
an unsupported `Container.close()` spelling. Corrected checks assert independent
cache-slot population plus exact binding/reference behavior and use the context
manager teardown API. That first incomplete bounded attempt was excluded and the
entire bounded grid rerun. Initial typing diagnostics were resolved; measured
probe copies retain the exact executed code before comment-only typing fixes.

[Accepted-source manifest](evidence/16/accepted-source.json),
[task-15-relative patch](evidence/16/task16-source.patch) and
[final verification](evidence/16/final-verification.json) capture the complete state.
Only the components implementation and the new test file belong to the source
patch; the full initial dirty diff and original source copies preserve prior work.
The exclusive measurement interval and all editing are complete.

## Carry-forward and handoff

Task 18 still owns combined, alternated cold/steady resolution acceptance, including
task 15's unresolved run/analysis timing signal and zero direct index accesses.
Task 14's 2,000-unique-definition compiler-peak regression remains: this task does
not offset or remeasure it. Stage percentages must not be added. The parked
artifact retains schema 8 and its existing supported subset; its task 15 load
cost remains applicable. Existing Python 3.15-dev `Latealias` limitations are not
weakened or silently converted into successful checks.

Task 17 must preserve caller-owned detached snapshots and existing opaque-value
owners while auditing internal last consumers. This change reduces construction
churn only; it does not establish that a source graph or draft can be released
earlier. No commit, version change, push, release, deployment or task 17/18
implementation was performed.
