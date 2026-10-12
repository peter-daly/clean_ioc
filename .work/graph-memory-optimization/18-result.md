# Task 18 — combined mode and compiler-memory acceptance

Status: complete — qualified **KEEP** accepted after coordinating review on 2026-10-10.
Recorded reasoning effort: high. Runtime implementation remains exactly the accepted task 17 source.

The coordinating review verified all 175 final manifest entries and all 55 prior accepted source hashes,
reviewed the task-relative tests and documentation, and checked the raw combined, inspection, lifetime and
resolution evidence. Acceptance includes the documented low-reuse and resolution costs; it does not establish
universal performance improvement or downstream deployment readiness. Tasks 10–18 are complete. The archived
manifest's pending-review decision records the agent handoff; this status records the subsequent acceptance.

## Scope, source and comparison

This accepts or rejects the **combined final implementation against accepted tasks 10/11**, before task 12.
It does not add the marginal percentages from tasks 12–17. HEAD is
`34d1ea02840afe6f23f0693b32651028ec7d9128`, branch `version2`, package `2.0.0rc4`;
the working tree contains the accepted unpublished changes and the original consumer-validation fix.
No commit, version bump, push, release, deployment or pre-compilation implementation is included.

The baseline container is the exact captured `evidence/12/container.before.py.txt`, SHA-256
`4a6c447812f7b313b96d2ce3bf09aab54207f24d88764b830a4c24010be5b683`, matching task 11's
accepted manifest. Baseline components are the task 14 before-source capture, SHA-256
`0fbadbc71772d8686d4956d96fa172ba27d4c47a2c92ebac93c8a79ec8c2bd94`, matching task 12's
accepted manifest. Tooling, selection census and fixture sources are unchanged across the comparison. Both policies use the same
current measurement runner; its task 12 change concerned only the private eager-fact CLI probe, outside this sample
path. The shared public-mode boundary is the accepted task 12 measurement boundary.
The final container SHA-256 is
`1a60386b392058ac47143b3acf4fc82b1034b95f360854dae2e98ff6cde42223`.
All 55 accepted task 17 hashes were verified before work; production sources remain unchanged.

A symmetric captured-source loader compiles both policies using original module filenames. Every raw
sample records hashes of **actually executed source**, separately from the shared runner's filesystem
provenance. Common library/evidence imports and source compilation precede timing and tracing. Main measurements
start before fixture source compilation/import and composition (identical fixture source on both policies), then include discovery, compilation, structural/build-rule validation, freezing and
retention. Collection precedes retained snapshots. Full graph validation/censuses run after the measurement.
No application constructors activate during compilation: the fixture asserts this on every build.

Three fresh normal and three separate traced processes run serially per policy/control, using BEFORE/AFTER,
AFTER/BEFORE, BEFORE/AFTER order. Controls are run at eight routes, arbitrary-rich-rule run at eight routes,
and analysis at two routes. The rich rule asserts diagnostics are available; its successful run runtime still
reports diagnostics disabled. This conservatively models arbitrary graph readers without claiming all real
rules have the same execution cost. Narrowed rules/purity inference were explicitly deferred in task 11;
there is no invented API or saving for such a control.

Current and peak RSS include earlier source compilation and allocator state. They are matched experimental
loader measurements, **not deployment capacity estimates**, and cannot be compared absolutely with prior
ordinary-import grids. Traced memory and RSS come from different processes. Separate observers reset
segment peaks only to locate phases; segment peaks and class maxima are never summed.

## Combined measured result

Values are medians, **accepted10/11 baseline → final**. [All samples and ranges](evidence/18/comparison-summary.json) derive from the [36 fresh build processes](evidence/18/build.json).

| Control | Fixture import/composition/build s | Retained traced MiB | Whole-build traced peak MiB | Current RSS MiB | Peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| run | 10.992 → 5.764 | 3.104 → 3.112 | 72.848 → 39.416 | 166.797 → 128.781 | 166.797 → 128.781 |
| rich-run | 8.432 → 8.560 | 3.103 → 3.112 | 290.183 → 254.089 | 387.234 → 347.375 | 392.234 → 349.375 |
| analysis | 0.284 → 0.282 | 6.483 → 6.438 | 7.763 → 7.588 | 91.062 → 91.281 | 91.062 → 91.281 |

Ordinary run build changes **-47.56%** and traced peak **-45.89%** (33.43 MiB lower). Rich-rule run build changes **+1.53%**, a repeatable cost, while peak changes **-12.44%** (36.09 MiB lower). Analysis build is effectively flat (-0.53%); its peak is -2.25%. Neither run control establishes a retained-memory gain: retained allocations rise by about 8 KiB. Analysis retention falls about 0.045 MiB.

| Control | Baseline / final normal build range s | Baseline / final traced peak range MiB |
| --- | --- | --- |
| run | 10.9291–11.0143 / 5.7475–5.8206 | 72.8477–72.8482 / 39.4151–39.4160 |
| rich-run | 8.4149–8.4433 / 8.5279–8.6102 | 290.1831–290.1834 / 254.0888–254.0890 |
| analysis | 0.2811–0.2979 / 0.2785–0.2865 | 7.7625–7.7630 / 7.5879–7.5883 |

All 36 processes agree on validated outputs, activation/template counts, retained graph inventory and executable graph counts. Each run control retains 8,982 physical records, 1,765 execution steps and 51 discovery entries; the analysis control retains 2,685 physical records and 1,549 logical graph visits. Representation-specific storage and definition counts are not incorrectly required to match.

## Resolution acceptance

Each fresh resolution process builds once, then records one cold and seven steady workload resolutions,
with wall and CPU time separately. Each workload's values and lifecycle are validated outside the timed
interval, and each scope is closed. Policies alternate in the same counterbalanced order as above.
This is a fixture workload including normal bookkeeping, not a pure resolver microbenchmark. It runs directly
after build without a forced collection, matching tasks 13/15. The main grid's single resolve instead follows the
prepared-memory snapshot's collection; those timings must not be treated as identical experiments.

Task 15's fixed-order run cold/steady +8.48%/+6.45%, analysis steady +3.75%, and task 16's rich-run shared
resolve +2.01% are genuine carry-forward signals. The task 15 zero-access census only rules out direct
compact-index lookup overhead in that workload; unchanged resolution code and overlapping ranges cannot
prove the absence of indirect layout/allocator effects. Final paired results and any warranted follow-up
are recorded here before acceptance.

[Raw cold/steady samples](evidence/18/resolution.json), three fresh processes per policy/control:

| Control | Cold wall ms | Steady wall ms | Cold CPU ms | Steady CPU ms |
| --- | ---: | ---: | ---: | ---: |
| run | 10.097 → 10.007 (-0.89%) | 9.792 → 9.752 (-0.41%) | 10.100 → 10.010 (-0.89%) | 9.797 → 9.754 (-0.44%) |
| rich-run | 10.271 → 10.161 (-1.08%) | 9.812 → 9.748 (-0.65%) | 10.277 → 10.166 (-1.08%) | 9.813 → 9.751 (-0.63%) |
| analysis | 2.101 → 2.199 (+4.68%) | 1.902 → 1.966 (+3.36%) | 2.104 → 2.202 (+4.66%) | 1.903 → 1.969 (+3.47%) |

The earlier run cold/steady regression does not recur in this matched combined comparison. Analysis still has a +3.36% steady signal (about 0.064 ms) despite overlapping process ranges; this warrants a targeted stage14/final control. Separately, the main grid’s post-collection rich-run resolve rises 14.955→15.351 ms (+2.65%), with nonoverlapping 14.911–15.082 / 15.288–15.735 ms ranges. A bounded prepared-memory/GC diagnostic investigates that boundary; no resolution-speedup claim is made.

The targeted [stage14/final analysis comparison](evidence/18/analysis-stage14.json) verifies both stage14 source hashes
against its accepted manifest. Three counterbalanced fresh pairs give cold 2.100→2.105 ms (+0.23%) and steady
1.903→1.973 ms (+3.68%). Cold ranges are 2.077–2.328 / 2.065–2.266 ms; steady ranges are
1.882–1.984 / 1.889–1.987 ms. With automatic GC disabled only around the workload, cold is
2.107→2.091 ms and steady 1.904→1.924 ms (+1.02%). CPU results track wall results. This repeats the small
analysis steady signal after stage14; it does not isolate task15 from task16, prove that GC alone causes it,
or establish strict non-regression. **Accept the observed roughly 3–4% analysis steady-workload cost as a
qualified tradeoff**, not a universal resolution-speed claim. There is no additional runtime tuning here.

The separate [rich prepared-memory diagnostic](evidence/18/resolution-gc.json) reproduces the exact shared
`_memory(False)` boundary (forced collection plus RSS subprocess), then measures cold and seven steady workloads.
Three fresh paired samples give cold 14.897→17.152 ms; the final range is broad, 15.370–18.013 ms.
Disabling automatic GC only during timed workloads narrows cold to 11.971→12.045 ms (+0.61%), while steady
is 10.028→9.851 ms. Separate intrusive observers report four generation-1 collections per workload on both
policies. This supports collection-state sensitivity, without proving a single cause or erasing the original
main-grid +2.65% post-collection penalty. Disabled GC is a diagnostic control, **not an application recommendation
or new build setting**. No general resolution-speedup or strict equivalence claim is made.

All normal diagnostic wall/CPU samples and ranges are in [the extras summary](evidence/18/extras-summary.json).
Observer timings are excluded from acceptance. The controlled comparisons resolve the decision by recording
these small, workload-sensitive costs alongside compiler-memory gains; they do not turn noisy timing into a
proof of absent indirect allocator/layout effects.

## Mode capabilities and behavior

| Behavior | Run (default) | Analysis |
| --- | --- | --- |
| Public roots, reached dependencies, decorators and filters | Same executable semantics | Same executable semantics |
| Discovery, including private/deferred/decorated registrations | Complete selected catalogue | Same selected catalogue |
| Providers/maps, ordinary scopes, slots, warmups, lifetimes and managed cleanup | Supported | Supported |
| Mandatory structural/boundary/lifespan checks and build rules | Executed; arbitrary rules get temporary rich evidence | Executed with retained rich evidence |
| Validation-only registration | Accepted and deferred | Accepted and deferred until `validation_report()` |
| Full validation report | Explicit unavailable-capability error | Stored build findings plus fresh validation-only findings per call |
| Inspection, explanation, census, manifests and overlays | Discarded capability; never recovered by callback replay | Supported; overlays may build either mode |
| Invalid unused dependency-only declarations | Not compiled solely for inspection | Compiled and validated without adding public roots |
| Independent failed-root aggregation | Original failure and bounded witnesses | Supported rich retries/aggregate evidence |
| Saved temporary inspection views/errors | Expired/reduced by task 11's ownership contract | Supported retained evidence |
| Detached caller-held Component snapshots | Remain caller-owned and usable | Remain caller-owned and usable |

Mode equivalence concerns the shared executable selections and behavior. Analysis may invoke extra callbacks
for unused dependency-only graphs or diagnostic failure retries; identical counts are not promised on those
extra paths. Full validation deliberately repeats validation-only callbacks, while graph inspection and
resolution do not replay selection/template callbacks. Failed builders remain retryable; successful builders
are single-use. CLI checks/inspection and matrices use fresh analysis builders; run runtimes cannot upgrade
in place. `set_provider_roots()` is a declaration separate from the only public `mode` choice.

The two new tests in `tests/test_combined_mode_acceptance.py` compose a command/saga-style bundle within a
private boundary. They preserve lazy private-handler and selected-decorator discovery, no public-root
expansion, no activation during compilation, mandatory rule execution, deferred/repeated validation-only
execution, and no selection replay. This is **application-shaped library coverage**, not downstream Bark/Cop
verification. Existing public-mode rich fixtures cover provider maps, all four provider forms, transient/scoped/
singleton identity and managed cleanup. Existing mode, lifetime, failure, overlay, profiling, warmup, slot,
selection, CLI and matrix suites provide the broader capability checks.

## Controls and ownership costs

The 2,000-unique-definition control uses the task 14 compiler-only boundary: common library imports finish
before tracing; service type creation, registration and build are included; builder release/collection precede
retained measurement. Resolution follows the memory snapshot. This separately tests low-reuse definition
pool cost rather than assuming the repeated eight-route graph generalizes.

[36 matching diversity samples](evidence/18/diversity.json), baseline → final:

| Control | Build s | Retained traced MiB | Peak traced MiB | Peak change |
| --- | ---: | ---: | ---: | ---: |
| run | 0.566 → 0.595 | 6.823 → 6.922 | 18.879 → 20.024 | +6.07% |
| rich-run | 0.615 → 0.636 | 7.337 → 7.423 | 20.715 → 22.550 | +8.86% |
| analysis | 0.572 → 0.614 | 15.526 → 15.537 | 20.597 → 22.441 | +8.95% |

Build medians increase 5.08% / 3.43% / 7.34% for run / rich-rule run / analysis. These are **combined low-reuse regressions**, not an attribution solely to task14: its earlier marginal baseline started after task13. The integrated policy remains a tradeoff favoring repeated graph structure, and this work does not claim a universal memory or CPU improvement. All 2,000 services resolve correctly in every control. Post-snapshot resolve medians are run 6.745→6.907 ms
(+2.40%, overlapping ranges), rich-rule run 7.028→7.411 ms (+5.45%, nonoverlapping ranges), and analysis
8.157→8.484 ms (+4.01%, nonoverlapping ranges). These are additional bounded costs included in qualified
acceptance; complete RSS and metric ranges remain in the summary.

Sparse-index and raw-promotion behavior reuse task 15's accepted evidence because `_compact_index.py` is
byte-identical. Sparse/tiny fallback adds 72 bytes over its native dictionary. At 100,000 dense entries, raw
promotion temporarily costs about 8.86 MiB and 23 ms; callers requesting dictionary-style views can give up
compact savings. Foreign-key hashing/equality must retain native dictionary behavior before compaction.
Those costs remain applicable; they are not hidden by a favorable whole-graph median. Public first/repeated
inspection and caller-held snapshot release are checked again on final source in separate processes.

Task 14's marginal unique-definition compiler peak cost remains a real tradeoff (0.88–1.29 MiB, 4–6%).
An adaptive bypass is outside this workstream. Task 13 only weakens activation-cache ownership for proven
scalar/key-safe values; opaque values and unknown keys stay strong. Typetoolbox's weak mapped-type keys and
strong map values are respected; no identity or release assertion assumes a fresh map per query.

The experimental artifact remains **schema 8, parked and unready**. Existing round trips are compatibility
checks only. Task 15's full-artifact load median 1.163→1.256 seconds (+7.97%) and size +18 bytes remain recorded
tradeoffs; no pre-compilation API, supported artifact expansion or production workflow is introduced.

## Separate populations, phase observers and inspection

The [final census](evidence/18/extras-summary.json) records constructors, per-class maxima, a separately observed
simultaneous draft-plus-record maximum, and retained objects across all counted graphs. It adds no counted
objects to a strong observer inventory. Each policy/control has its own process, outside performance samples.

| Population | Eight-route run and rich-run before → final | Two-route analysis before → final |
| --- | ---: | ---: |
| Drafts constructed | 90,250 → 90,250 | 2,847 → 2,847 |
| Records constructed | 194,306 → 102,490 | 12,079 → 7,463 |
| Definitions constructed | 92,104 → 304 | 4,696 → 84 |
| Maximum live drafts | 88,558 → 88,558 | 2,685 → 2,685 |
| Maximum simultaneous drafts + records | 99,232 → 90,295 | 3,289 → 3,289 |
| Records retained across all counted graphs | 8,982 → 8,982 | 2,847 → 2,847 |
| Definitions retained across all counted graphs | 116 → 116 | 80 → 80 |

Run retains one graph; analysis retains nine, including supporting graphs beyond its 2,685 primary records.
All counted drafts, records, definitions and graphs reach zero after runtime teardown. No-rule compact fact
pool/constructor evidence from task12, conservative cache ownership from task13, and compact adapter/promotion
counts from task15 remain source-backed controls; they are not added to these populations or to memory totals.

Six separate phase observers distinguish fixture import, composition (`ContainerBuilder.build` entry), template
expansion, primary compilation, finalization, warmup planning, graph retention and freezing, successful return,
and collection. Analysis additionally observes explicit `validation_report()` creation with **no application
validation-only rules in this fixture**; the bundle test separately verifies those callbacks. The large run
observer locates a shift from primary-compilation peak toward retained-graph freezing. It does not establish an
independent additional saving. Observer wrappers, log ownership, differing common-import preparation and peak
resets alter this experiment. For example, analysis maximum segment peaks reverse direction (~7.254→8.010 MiB)
while the accepted whole-build traced grid is 7.763→7.588 MiB. That sensitivity is a limitation of phase attribution;
segment maxima are never summed or substituted for whole-build acceptance.

The 24 fresh bounded snapshot samples preserve **193 saved views, 129 graphs and 194 distinct records**, one
source-filter call, 64 target predicates and 64 position callbacks in each policy/mode. Snapshots survive runtime
release, first/repeated generic and descendant inspection returns the same fields, and clearing caller-held
views releases **all graphs and records**. The baseline predates mutable definition pools; only final graphs
have the additional empty-pool assertion. Both policies must have no retained drafts or view cache.

Three fresh processes per policy perform bounded rich-rule inspection and three perform full analysis
walk/census/manifest inspection, each first and repeated. Template callbacks never replay; final compact-index
capacities remain unchanged; all manifest fingerprints match baseline. First inspection populates existing
inspection caches, and repeated calls reuse them. Detailed timings/retained/peak values are in the extras
summary; these traced inspection screens are separate from ordinary build timings and establish no universal
inspection speedup. Caller-owned inspection result lists and snapshots are retained deliberately by these
controls and are not assigned to runtime retention.

## Candidate decisions

| Task | Decision and bounded claim |
| --- | --- |
| 10 | KEEP explicit default run / analysis contract and migration; discarded capabilities fail clearly |
| 11 | KEEP view/error lifetime and validation contract; REFINE/DEFER narrower evidence contracts and inferred purity |
| 12 | KEEP direct compact facts for CPU/churn; its marginal peak increased about 0.3 MiB |
| 13 | KEEP conservative scalar/key-safe weak activation caching; retain strong opaque ownership |
| 14 | KEEP immutable shared draft definitions for repeated graphs; explicitly accept low-reuse pool overhead |
| 15 | KEEP compact origin/decorator sidecars with native fallback; DROP tuple interning, DEFER packed ranges |
| 16 | KEEP direct draft snapshot freezing for construction churn/build CPU; no independent memory gain claimed |
| 17 | KEEP narrow retained-draft transfer at the existing freeze boundary; DROP/DEFER broad streaming reclamation |
| Combined | Qualified KEEP accepted after coordinating review for repeated-graph compiler peak and default-run CPU; low-reuse and resolution tradeoffs remain explicit |

Task 04 contextual sharing remains reverted. Task 07 bonus slots are not integrated. No broader disposal rule
is inferred from the final transfer: the task 17 opaque-finalizer counterexample still forbids early disposal
of discarded drafts before selected graph freezing.

## Quality, reproducibility and limits

Full Python 3.14.4 `make ci` passes: Ruff lint/format, type checks, **2,409 tests**, executable documentation,
and BenchBro discovery. The existing Starlette warning remains. Strict MkDocs and `git diff --check` pass.
The expanded focused suite passes **739 tests** on Python 3.14 and 3.13; Python 3.12 passes **736 with three
skips**, and Python 3.11 passes **735 with four skips**. Three TypeVar-default cases require Python 3.13;
the extra 3.11 skip is the native provider-map type-alias test, which requires Python 3.12. No assertions or
supported-version expectations were weakened.

The initial isolated 3.11 collection lacked `jsonschema` for the newly included matrix tests. That harness dependency
was added and all supported-version checks rerun successfully; the original error log remains preserved. Initial
reproduction-driver lint/type issues were corrected without changing measured sample function bodies. Final lint,
format and type checks include the completed evidence scripts. Exact commands and logs are in
[final-checks.sh](evidence/18/final-checks.sh), [full CI](evidence/18/make-ci.txt),
[strict docs](evidence/18/docs-strict.txt), and the versioned focused logs under `evidence/18`.

The [final verification](evidence/18/final-verification.json) verifies all **55 prior accepted hashes unchanged**,
all captured executed-source identities, and unchanged measured sample-function ASTs. The
[175-entry manifest](evidence/18/accepted-source.json) captures final sources, raw evidence and harnesses.
[task18-source.patch](evidence/18/task18-source.patch) is relative to task17 and contains only the focused
acceptance test plus README, upgrade-guide and fixture-documentation fixes. No runtime implementation changed.
Historical evidence retains its original bytes and numbers.

Captured source files were renamed from `.py` to byte-identical `.py.txt` after all performance measurements,
so repository type/lint checks do not treat archived modules as live code. The loader suffix changed accordingly;
`compile()` still uses original module filenames. Exact measured scripts are saved as `.py.measured.txt`.
Reproduction parent commands now require an explicit output directory and refuse existing raw output files.
A separate [smoke check](evidence/18/reproduction-smoke.json) executes both archival paths, verifies actual
loaded hashes and confirms overwrite protection; its timings are excluded from all performance comparisons.

Run from the repository root, using the recorded Python/environment for comparable results. Run these serially
without competing tests or benchmarks; the temporary directory keeps accepted evidence intact:

```sh
TASK18_EVIDENCE=.work/graph-memory-optimization/evidence/18
TASK18_OUTPUT="$(mktemp -d /tmp/clean-ioc-task18.XXXXXX)"
.venv/bin/python "$TASK18_EVIDENCE/grid.py" build "$TASK18_OUTPUT"
.venv/bin/python "$TASK18_EVIDENCE/grid.py" resolution "$TASK18_OUTPUT"
.venv/bin/python "$TASK18_EVIDENCE/grid.py" diversity "$TASK18_OUTPUT"
.venv/bin/python "$TASK18_EVIDENCE/resolution_gc.py" repeat "$TASK18_OUTPUT"
.venv/bin/python "$TASK18_EVIDENCE/observers.py" "$TASK18_OUTPUT"
.venv/bin/python "$TASK18_EVIDENCE/analysis_stage14.py" repeat "$TASK18_OUTPUT"
.venv/bin/python "$TASK18_EVIDENCE/summarize.py" "$TASK18_OUTPUT"
.venv/bin/python "$TASK18_EVIDENCE/verify_extras.py" "$TASK18_OUTPUT"
```

For a single source-verified sample, `grid.py sample before|after run|rich-run|analysis normal|heap
build|resolution|diversity` prints JSON to standard output. Use a fresh file if redirecting it. The final verifier
checks accepted source/evidence identity; it is not another performance run.

Actual downstream Bark/Cop unit tests, integrations, Docker/container-memory checks and production measurements
were **not run**. They were not assigned here and no external application repositories were edited. Library and
synthetic equivalence do not establish downstream deployment readiness. ARM macOS results cannot stand in for
production x86 Datadog memory. The known experimental Python 3.15-dev `Latealias` error remains a nonblocking
historical limitation; assertions are not weakened to disguise it.
