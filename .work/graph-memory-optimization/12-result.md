# Task 12 result — direct compact decorator facts

Completed 2026-10-10 by the assigned high-effort task agent; root review accepted
the scoped change. **KEEP** the scoped
CPU/allocation-churn improvement for diagnostics-off compilation. **DEFER** a
shared payload representation for rich occurrence history. There is **no measured
memory reduction** from this task. No commit, version bump, push, release or
production action was performed.

## Change and preserved contracts

The compiler now checks a local identity-keyed pool before constructing immutable
template facts, formatting their labels or building generic-binding tuples.
Constant selector-rejected candidates are interned too. Occurrence context is
passed explicitly to the existing remapped explanation, removing the previous
construct-then-normalize copies. Callback-dependent selected/rejected decisions
continue to capture each invocation's actual outcome and description.

The [inventory](12-inventory.md) documents identity owners, consumers and lifetime.
All new keys contain only integer identities; values keep those identities alive
through that compiler's lifetime. Neither pool is retained in execution plans or
public graphs. Public dataclasses, graph/failure lifetimes, selected registration
catalogues, callback ordering and artifact representation remain unchanged.
No callback, template factory or application constructor is replayed for evidence.

Analysis and run builds with arbitrary build rules preserve their eager rich
history. Eight-route rich capture constructs 565,220 template facts with 565,220
distinct complete signatures: exact interning has no hits. Omitting occurrence
from that signature leaves 430 payloads, but changing public dataclass storage
and history ownership requires a separate design. This task does not claim the
no-rule speedup for rich-rule workloads or narrow any rule capability.

## Measurement protocol

[Before](evidence/12/before.json) and [after](evidence/12/after.json) each contain
three fresh untraced processes plus three separate traced processes for each of
three controls, run serially with no competing tests or benchmarks. Normal
samples report fixture import/composition/build time and current/peak RSS;
separate tracemalloc samples report retained allocations after collection and
whole-build peak. All samples use Python 3.14.4 on macOS ARM64, the same fixture
and explicit public build modes. The caller retains no builder or selection views.
The four provider roots are composition declarations in the fixture.

- No-rule run: eight routes, direct compact capture exercised.
- Rich-rule run: eight routes and an arbitrary build rule that asserts temporary
  diagnostics are enabled; complete rich capture is required before run reduction.
- Analysis: two routes, retaining diagnostic history and the composition. This
  bounds retained-graph cost while the eight-route rich-run control exercises the
  larger temporary diagnostics workload.

The reported run-mode `diagnostics=false` in the shared runner metadata describes
the successful runtime policy; the rich rule explicitly verifies its temporary
graph has diagnostics enabled. Intrusive constructor/finalizer censuses and
inspection measurements are separate processes, excluded from timing/RSS claims.

Values show **before → after**, medians:

| Control | Build seconds | Resolve ms | Retained traced MiB | Peak traced MiB | Current RSS MiB | Peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| No-rule run, 8 routes | 10.951 → 5.712 | 14.202 → 14.294 | 3.103 → 3.103 | 72.846 → 73.146 | 129.984 → 132.438 | 129.984 → 132.438 |
| Rich-rule run, 8 routes | 8.387 → 8.483 | 14.970 → 14.906 | 3.102 → 3.102 | 290.182 → 290.182 | 349.109 → 350.656 | 355.859 → 355.531 |
| Analysis, 2 routes | 0.280 → 0.282 | 2.566 → 2.659 | 6.482 → 6.482 | 7.762 → 7.762 | 49.781 → 49.391 | 49.781 → 49.391 |


No-rule build time falls **47.8%**. Traced peak rises by **314,638 bytes
(0.300 MiB)**, while retained allocations are unchanged within 60 bytes.
Normal RSS ranges are 128.953–131.516 MiB before and 131.094–132.844 MiB
after: they overlap slightly, and the higher median is not a demonstrated RSS
saving. The repeatable traced increase includes the new pool/key/owner cost;
RSS also reflects allocator/process variability.

Rich-rule build time changes 8.387 → 8.483 seconds (+1.1%; normal ranges
8.363–8.444 versus 8.478–8.572 seconds), with effectively identical traced
peak. Analysis changes 0.280 → 0.282 seconds. These controls show no rich-path
benefit. **Bark-like consumers with unknown mandatory build rules take that rich
path; the no-rule speedup does not automatically apply to them.**

All 36 samples agree on resolution results, template/callback counts, graph census
and retained graph inventory ([verification](evidence/12/evidence-validation.json)).
Both eight-route run controls retain 8,982 physical records, 1,765 execution steps
and 51 selected registrations; logical graph visits are unavailable under run's
inspection contract. The two-route analysis control has 2,685 physical records
and 1,549 logical visits. These figures and the separate resolution workload are
not estimates of compiler peak ownership.

## Constructor, live-object and pool evidence

| Control / fact | Constructor calls before → after | Maximum simultaneously live before → after | Retained after build before → after |
| --- | ---: | ---: | ---: |
| No-rule run (8 routes) / CandidateDecision | 1,130,498 → 1,396 | 488 → 628 | 0 → 0 |
| No-rule run (8 routes) / TemplateDecision | 1,130,440 → 570 | 460 → 570 | 0 → 0 |
| Rich-rule run (8 routes) / CandidateDecision | 653,756 → 653,756 | 652,954 → 652,954 | 0 → 0 |
| Rich-rule run (8 routes) / TemplateDecision | 565,220 → 565,220 | 565,220 → 565,220 | 0 → 0 |
| Analysis (2 routes) / CandidateDecision | 11,730 → 11,730 | 11,684 → 11,684 | 11,684 → 11,684 |
| Analysis (2 routes) / TemplateDecision | 9,076 → 9,076 | 9,076 → 9,076 | 9,076 → 9,076 |

Raw [before run census](evidence/12/before-census-run.json) and
[after run census](evidence/12/after-census-run.json); corresponding rich-run and
analysis files use the same naming pattern. Per-class live maxima occur at their
own times and must not be summed.


Counts are exact constructor/destructor observations for the two named concrete
classes within an instrumented process; they are not allocation bytes. Subclasses
are excluded. Adding finalizer observers and signature sets changes instrumentation
cost and can affect collection behavior, so no timing or memory total is taken
from these censuses. Rich/analysis history remains unchanged. All run-mode facts
are released by successful build return after collection; analysis retains its
supported history. All fact counts are zero after runtime release.

At primary compiler release, the new pools contain **570 template entries** and
**490 selector-rejection entries**. The existing 43-pattern pool is unchanged.
The new template pool has 18,512 bytes of dictionary storage, 50,160 bytes of
key tuples, 91,200 bytes of identity integers, 36,480 bytes of entry tuples and
50,160 bytes of strong-owner tuples. The rejection pool has 18,512 dictionary
bytes and 15,680 integer-key bytes. Together these newly introduced shallow
containers/keys occupy 280,704 bytes; this excludes referenced fact objects and
application/blueprint objects and is already included in the traced peak above.
It is not an additional memory total or a saving.

The rich and analysis pools remain empty (two 64-byte dictionaries). New pools
are absent in the baseline; before-census output has no owner-tuple columns.
After-census reporting adds those columns without changing constructor/liveness
observation. The retained immutable facts contain only captured diagnostic data;
pool input owners remain compiler-local. Detached caller-owned snapshots remain
valid, and the compiler weak-reference tests establish pool release.

## Inspection and verification

A separate bounded rich-rule inspection reads 64 occurrences / 256 decisions twice
([before](evidence/12/before-inspection.json), [after](evidence/12/after-inspection.json)).
First-pass time is 11.187 → 11.333 ms; repeated time is
0.966 → 0.969 ms. Both retain 321,328 bytes after the first pass
and 321,600 after the second, including observer output bookkeeping. The existing
first-read graph cache allocation is unchanged; there is no new deferred view or
retained inspection cache. These single-process bounded observations are descriptive,
not a precision timing claim. Template callback counts are unchanged.

- `make ci`: Ruff lint/format, `ty`, **2,247 tests**, executable documentation
  examples and BenchBro discovery pass. The existing Starlette/httpx warning remains.
- Strict MkDocs and `git diff --check` pass.
- **18 new public-mode tests** cover direct interning, distinct transient instances,
  boundary-local sources/targets/origins, both selector kinds, generic source
  and target bindings, actual stateful filter descriptions/outcomes, dynamic positions,
  original callback failure provenance, repeated rich inspection, saved-view
  expiration and compiler/pool release. Existing eager-reference and artifact
  tests are included in the passing suite; the focused integration run passed 159 tests.
  The broad fixture also preserves source-to-generated and generated-to-source
  registration-template paths.
- The 18 new tests also pass on isolated Python **3.11, 3.12 and 3.13**;
  Python 3.14.4 is covered by full CI. Logs are in `evidence/12/`.

Initial test failures were assumptions in the new tests: the default lifespan
shares instances, some visited occurrences have no decorator evidence, analysis
aggregates failures into its report, and boundary compilation uses distinct local
pools. The tests now explicitly request transients and assert each supported
contract. No production semantic change was made to satisfy those assumptions.
The standalone inspection harness initially used an unsupported `close` method;
it was corrected to the supported context exit before capturing baseline evidence.

## Reproduction, source identity and handoff to 13

[accepted-source.json](evidence/12/accepted-source.json) records source/fixture/harness
hashes and settings; [task12-source.patch](evidence/12/task12-source.patch) contains
only this task's production/test/harness changes relative to task 11. Starting
source copies and the complete starting working diff are retained alongside it.
HEAD remains `34d1ea02840afe6f23f0693b32651028ec7d9128`, branch `version2`, version
`2.0.0rc4`; all pre-existing working changes were preserved. Archived task 06–09
probes were neither installed nor reformatted. The `.py.txt` harness snapshots
preserve pre-format baseline census/measurement code; later edits are formatting,
parameter spelling and shallow pool-storage reporting, not measurement-policy changes.

```sh
.venv/bin/python .work/graph-memory-optimization/evidence/12/measure.py repeat OUTPUT.json
.venv/bin/python .work/graph-memory-optimization/evidence/12/census.py run
.venv/bin/python .work/graph-memory-optimization/evidence/12/census.py rich-run
.venv/bin/python .work/graph-memory-optimization/evidence/12/census.py analysis
.venv/bin/python .work/graph-memory-optimization/evidence/12/inspection.py
```

Task 13 may reuse these fresh AFTER samples as its BEFORE controls only after
verifying the accepted production/fixture/harness hashes, interpreter and options.
This avoids repeating identical expensive traces. Its cache-lifetime work must
still preserve opaque application values, callback snapshots, boundary/ownership
semantics, failure readers and task 11's rich-rule contract. The new fact pools hold
identity inputs until compiler release; they are not activation-cache values and
are not an authorization to weaken application ownership. Do not add this task's
speed change or prior standalone memory changes; task 18 must measure the actual
combined implementation. Tasks 13–18 remain queued for their assigned agents.
