# 20 — Compilation budgets

Created: 2026-10-04\
Status: Implemented; independent Sol High APPROVE / KEEP; required checks and final evidence complete\
Priority: P2\
Baseline: Clean IoC 2.0.0b30 at `eacdf70` on `codex/compiler-optimization`\
Dependencies: Existing compiler work counters, structured failures, and partial diagnostic graphs\
Related work: [Compilation profiler](11-compilation-profiler.md),
[failed-build diagnostics](05-failed-build-diagnostic-graphs.md), and
[build-error triage](09-build-error-triage.md)

## Outcome

Allow applications to set explicit limits on compiler work and receive a useful build diagnostic when a composition
exceeds them. This prevents unexpectedly large occurrence expansion or template/specialization work from producing
an uncontrolled build, without changing ordinary compilation when no budget is configured.

The feature enforces deterministic work-count limits. It is not a timeout mechanism that can interrupt arbitrary
application callbacks, and it does not activate components to estimate their runtime cost.

## Accepted surface

The immutable `CompilationBudget` is supplied through a separate optional `budget=` argument on root and scope
builder `build()` methods. The accepted fields are `graph_occurrences`, `active_dependency_depth`,
`specialization_materializations`, `generated_template_outputs`, `diagnostic_attempts` and `preparation_operations`.
`BuildVariant.budget` supplies a fresh independent allowance to each matrix variant.

Do not put compiler control in magic `build_args` keys. Define legal values, counting units, exact threshold behavior,
and default-unlimited semantics before accepting the API. A configured limit of zero must have an explicit meaning;
do not silently interpret it as unlimited. Budget configuration and outcomes do not alter graph fingerprints.

## Counting and failure contract

1. Count real compiler operations with explicit units. Occurrences, candidate attempts, specialized registrations,
   templates, and executable steps are different quantities. Reuse item 11's operation boundaries rather than sampling
   profiler detail or inferring work from the final graph alone.
2. Cover the full build, including discovery/preparation, source-inspection compilers, recursive expansion, primary
   compilation, and diagnostic retries where applicable. Specify per-phase versus whole-build accounting. Dependency
   depth describes one active path; it is not summed across independent roots.
3. Existing structural-pattern non-termination checks remain mandatory and distinct. An optional general budget must
   not relax those checks or turn a bounded-depth diagnostic into a generic Python recursion error.
4. Stop before performing the operation that would exceed its configured limit. Produce a stable structured error
   with the limit kind, configured maximum, observed work, phase, and best available declaration/root/path evidence.
   Never report a partially compiled graph as a usable runtime.
5. Budget exhaustion must not trigger unbounded recovery compilation. Carry the budget through retries, retain the
   original exhaustion finding, and label omitted/truncated diagnostic evidence honestly. Do not replay composition
   callbacks merely to reconstruct information that the budget already prevents collecting.
6. Failed builders remain repairable. A fresh explicit build starts fresh counters; diagnostic retries within that
   build do not replenish its work allowance. Overlay builds count work they actually perform, with existing anchored
   reuse distinguished from fresh materialization.
7. `BuildMatrix` budgets, if exposed there, apply to each variant build and aggregate through existing failure reports.
   Do not quietly create a matrix-wide budget or require caller-owned parents to be rebuilt.
8. Reports never include private build/provision values, owner tokens, or arbitrary callback/exception representations.
   Timing information from an optional profiler stays separate from deterministic limit enforcement.
9. Normal runtime resolution, provider invocation, and scope creation gain no budget work. Unconfigured compilation
   overhead must be measured and kept small; runtime component activation is outside these counters.

## Diagnostics and tooling

The stable code is `compilation-budget-exceeded`, with a structured limit kind rather than interchangeable names
for different counters. These failures remain errors and cannot be ignored into a successful build.

Integrate text/JSON, source-linked SARIF, partial-graph/triage reporting, and compilation profiles. Explain which
operations were counted and which diagnostics could not be collected after exhaustion. No standalone web UI is needed.

## Implementation stages

1. Inventory existing count/recursion/retry limits and define precise deterministic units and threshold semantics.
2. Add the optional immutable budget and propagate one build-owned counter state through relevant phases.
3. Integrate safe exhaustion diagnostics, bounded recovery, builder repairability, and tooling exports.
4. Verify boundary cases, no-activation behavior, supported Python, and configured/unconfigured overhead; obtain review.

## Acceptance criteria

- Small controlled graphs stop at the documented limit, with useful phase/path/source evidence and no usable partial
  runtime. Disabled limits preserve existing behavior.
- Generic expansion, source/template work, overlays, and failed-build retries obey their defined counting rules.
- Budget exhaustion cannot cause unbounded diagnostic work, secret leakage, or repeated resets within one build.
- Failed builders can be repaired and rebuilt; reports and matrix aggregation remain deterministic and source linked.
- CI/docs and focused measurements validate the contract without introducing wall-clock-dependent tests.

## Scheduling

Pre-change timing, allocation and compilation profiles are recorded in
[the compiler baseline](compiler-optimization-baseline.md). Its compiler draft counts include synthesized provider
expansion and differ substantially from public graph visits; budgets must use real operation boundaries.

The maintainer prioritized this item on 2026-10-04, scheduled after implementation and independent review of item 19.
Sol High implements it and a separate Sol High agent reviews it. Preserve the pre-change baseline and compare the
completed item 19 state to isolate configured/unconfigured budget overhead. Incremental compilation and plan
optimization are not prerequisites for defining deterministic work limits.


## Implementation and proof

The public API and exact six-unit operation table are documented in
[Compilation budgets](../docs/compilation-budgets.md). Every limit accepts an exact built-in non-negative integer;
`None` means unlimited and zero refuses the first unit. Configuration is immutable and validated before build work.
No allowance state is created for `budget=None`. All-unlimited configuration deliberately counts work.

Allowance counts **admitted operation starts**, including operations that later fail; it never counts a refused
next operation. Depth is the maximum active component parent path, including provider/collection/clone metadata,
not a sum across roots. Occurrence/depth and template-output/factory-entry admissions are atomic. One allowance
survives preparation, source and visibility inspection, primary/provider compilation, finalization and diagnostic
retries. Preparation charges imports, candidate/iterator examination and the documented compiler-controlled
callback entries; specialization and output counters charge new construction, excluding cache/no-op reuse.

A private sticky `BaseException` control signal crosses existing callback `Exception` wrappers without being
misclassified. The public boundary converts it to a structured immutable exhaustion sidecar on an ERROR finding;
checks after compiler-controlled callback return and at the public exception boundary preserve first exhaustion
if user code catches the signal. Recovery stops, retains already captured compiler/source/finalization findings,
and exports honestly truncated evidence. No usable partial runtime or graph is exposed. Captured automatic
validation callback errors are sanitized using provenance; explicit user-authored findings remain public.
Matrix safe reports retain the sidecar, and SARIF carries source/root/path evidence where available.

Configured compile state is detached before return/error delivery. GC-disabled weak-reference tests prove that a
live successful runtime and a retained direct-exhaustion error do not retain `_Compiler`; both match the disabled
case. This avoids hiding repeated configured builds behind cyclic collection during BenchBro measurements.
Normal exception/report lifetime still applies. Runtime callbacks and activation are outside the allowance.

Small exact-boundary tests establish leaf=45 occurrences/depth3, wide24=1080 occurrences/depth3, zero limits,
thresholds, preparation/source/visibility/template/generic/provider-map/warm-up boundaries, failed builder repair,
retry carry/zero retries, no replay, ignored errors, overlays, per-variant matrices, safe deterministic exports,
partial-attempt totals, prior finding retention and private exception redaction. The existing structural-pattern
nontermination limits remain mandatory. All-unlimited-vs-disabled full graph/step/report equivalence was independently
checked across six stable fixture shapes and an anchored overlay.

A source-backed AST comparison against `9b4b053` proves all 52 selected runtime definitions unchanged, including
all execution/observed step classes, runtime owners, resolution contexts, `Scope`, `Container`, frozen providers,
and the shared selection/validation helpers. The original compiler benchmark, evidence helper and managed-runtime
control source are byte-identical. Raw proof: `/tmp/item20-runtime-proof.json`.

## Required validation

- `make ci > /tmp/item20-ci-final.log 2>&1`: Ruff format/lint, type checks, 1711 tests, executable documentation
  examples and ordinary BenchBro discovery passed. One pre-existing FastAPI/Starlette warning remains.
- `uv run mkdocs build --strict --site-dir /tmp/item20-docs > /tmp/item20-docs.log 2>&1`: passed.
- `/tmp/clean-ioc-warmup-py311/bin/python -m pytest -q`: 1703 passed, 8 existing language-feature skips.
- `/tmp/clean-ioc-warmup-py312/bin/python -m pytest -q`: 1708 passed, 3 existing language-feature skips.
- `/tmp/clean-ioc-warmup-py313/bin/python -m pytest -q` and the py314 equivalent: 1711 passed each.
  Logs: `/tmp/item20-python{311,312,313,314}.log`; all four retain the same known warning.
- Executable docs and ordinary discovery additionally passed in every isolated supported environment:
  `/tmp/clean-ioc-warmup-py{311,312,313,314}/bin/python scripts/validate_docs_examples.py` and each matching
  `bin/benchbro list --verbose`. Logs: `/tmp/item20-python{311,312,313,314}-{docs,discovery}.log`.
- Independent reviewer: 660 focused checks, including budget cases, plus a final 69-case budget rerun passed.
  Final independent Sol High review is APPROVE / KEEP; all findings are resolved.

## Measurement boundary

Post-item-19/pre-item-20 timing was captured before production edits using the original six `compiler-build-only`
fixtures in `/tmp/item20-before-{1,2}.{json,md}`. These isolate this item's disabled overhead from item19 and preserve
the release baseline and item19 artifacts. Fixed25 repeats/warmup5, eight builds per repeat, declarations and normal
close excluded; CPython3.14.4/macOS ARM64 and original lock/control sources are unchanged.

Final unprofiled runs use the same controls. The isolated `compilation_budget_experiment.py` stays outside ordinary
`bench_*.py` discovery and requires `--case compilation-budgets` because it imports the decorated stable fixture module.
It compares None, all-unlimited, generous finite allowances, and occurrence100 bounded failure on wide/generic/
collection/template builds plus an overlay whose parent build and close are excluded. The bounded operation includes
safe failure-report capture. Budgets are created outside measurement. Failed compiler cleanup is proved with GC disabled.

Separate `compilation_budget_evidence.py` records five independent Python-traced allocation samples (fresh declarations
before tracing; unactivated runtime or failure report retained), one full compiler profile and five cProfile builds per
shape/mode. Normal close/declarations are excluded from profiling. Instrumented duration is never a latency result;
traced bytes are not RSS. It verifies unchanged source digests and zero application activations.

Limits do not interrupt arbitrary code inside an admitted callback/import/iterator advance. Hash/equality and custom
reflection protocol internals are not separately metered; snapshot copying, inventory scans, alias validation, freezing,
indexing and rendering have no separate units. This is neither a wall-time limit, total instruction/byte bound, memory
cap nor sandbox. The guide states these limits explicitly. Budget units do not depend on signature calls or public graph size.


## Unprofiled latency and uncertainty

All values below are per-build medians in milliseconds, shown as run1/run2; each run has fixed25 repeats,
warmup5 and eight iterations per repeat. These are fresh build-only fixtures, excluding declarations/normal close.

| Shape | Post19 before20 ms | After20 disabled ms | Repeat CV before range | Repeat CV after range |
| --- | ---: | ---: | ---: | ---: |
| wide-24 | 45.169/58.070 | 40.070/43.393 | 10.0–17.6% | 7.5–10.5% |
| diamond-depth-5 | 46.139/66.366 | 53.571/51.813 | 8.4–18.5% | 13.4–14.8% |
| generic-8-roots | 63.596/88.444 | 76.658/74.186 | 6.9–14.1% | 9.1–10.2% |
| collection-12 | 29.806/28.429 | 29.855/30.540 | 8.7–15.0% | 10.8–14.2% |
| template-12 | 41.241/36.100 | 39.675/35.739 | 12.1–16.1% | 13.8–16.2% |
| managed-warmup | 5.981/5.437 | 6.184/5.264 | 17.8–22.1% | 19.9–21.6% |

The unchanged pre20 code itself shifts wide45.169→58.070ms, diamond46.139→66.366ms and generic63.596→88.444ms
between runs. Final disabled results are mixed against that spread; there is no consistent six-shape slowdown and
no defensible small percentage effect estimate. These measurements cannot rule out small overhead/regression.
No disabled speedup claim is made. The implementation avoids allowance creation, callback wrappers and ancestry
walking when disabled; it adds compiler-only configuration/guard branches and never branches on budget in runtime paths.

The isolated mode experiment uses the same broad fixtures, plus a separate anchored managed-warmup overlay whose
parent compilation/close is excluded. Modes are pre-created None, all-unlimited, generous finite limits
(occurrence100000/depth100/specialization10000/output10000/retry100/preparation100000), and occurrence100.
Again values are run1/run2 median milliseconds; bounded operation includes safe exception/report capture.

| Shape | None | All-unlimited | Generous finite | Occurrence100 |
| --- | ---: | ---: | ---: | ---: |
| wide-24 | 53.614/42.696 | 47.652/45.470 | 49.541/45.324 | 6.917/6.844 |
| generic-8-roots | 78.803/68.951 | 66.907/79.702 | 85.290/77.658 | 18.369/19.575 |
| collection-12 | 32.140/34.686 | 36.486/31.835 | 36.089/31.866 | 11.503/10.850 |
| template-12 | 35.596/36.077 | 41.984/37.117 | 41.230/35.461 | 14.571/12.212 |
| overlay | 6.457/5.194 | 6.392/5.238 | 7.400/6.750 | 6.586/4.949 |

Mode repeat CV ranges8.3–22.8%. Ordered cells and between-run drift prevent attributing their differences solely
to budget counting: all-unlimited is sometimes faster than None despite doing additional admitted-operation work.
The budget unit/stop proof comes from deterministic profiles and threshold tests. Occurrence100 truncates all five
fixture builds, including the overlay; its failure latency is close to full overlay latency because substantial inspection/
clone work has already been admitted before the refusal.
Configured limits are opt-in and add accounting/callback-entry overhead; these runs give observed latency ranges,
not a reliable causal overhead percentage or performance guarantee. Both raw runs and their confidence/variation
metrics are retained in `/tmp/item20-measurement-summary.json` and the original BenchBro JSON.

Unchanged runtime controls below are microseconds per batch of100 operations, fixed25 repeats/warmup5,
1000 batches per repeat (the original control setting). Composition/activation setup is excluded.

| Path | Post19 controls run1/run2 µs | Final controls run1/run2 µs | Final repeat CV range |
| --- | ---: | ---: | ---: |
| batch-of-100[resolve] | 40.446/46.455 | 42.294/44.946 | 15.6–19.1% |
| batch-of-100[provider] | 63.682/58.746 | 60.640/66.350 | 14.3–15.7% |
| batch-of-100[scope] | 171.435/178.203 | 163.049/174.717 | 7.1–19.1% |
| batch-of-100[per-call] | 1622.260/1404.717 | 1337.087/1313.462 | 7.2–9.2% |

These controls also drift with unchanged source and frozen executable semantics. No runtime speedup claim is made;
small regressions are not statistically ruled out. The52-definition AST proof and independent full-plan/graph
comparison establish absence of runtime budget work/branches rather than treating noise as evidence of causality.


## Deterministic work, allocation and profiling evidence

Command (run after every unprofiled capture, with no CI/check overlap):
`TMPDIR=/tmp uv run python -m benchmarks.compilation_budget_evidence > /tmp/item20-evidence.log 2>&1`.
The temporary directory is explicit on macOS. A separate four-mode overlay profile used the exact experiment fixture
and wrote `/tmp/item20-overlay-evidence.json` and `/tmp/item20-overlay-*-compilation-profile.json`.

| Shape | Full admitted occurrences / profiler drafts | Depth peak | Specializations | New outputs | Preparation | Bounded admitted occurrences / profiler drafts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wide-24 | 1080/1080 | 3 | 0 | 0 | 24 | 100/100 |
| generic-8-roots | 1568/1568 | 5 | 4 | 0 | 132 | 100/100 |
| collection-12 | 650/650 | 6 | 0 | 0 | 313 | 100/100 |
| template-12 | 662/650 | 6 | 0 | 12 | 349 | 100/88 |
| anchored overlay | 141/141 | 5 | 0 | 0 | 8 | 100/100 |

None/all-unlimited/generous successful profile counters are identical. Template12 has12 additional source metadata
occurrences outside `_draft`, so its allowance662 differs from profiler650; bounded100 includes these12 and only88
primary drafts. Generic8 has16 specialization requests but only4 new materializations. Every occurrence100 refusal
records admitted100, attempted101, then stops without recovery or usable graph. All20 compiler profiles have zero
omitted records; detail truncation was not used to enforce limits. All20 profile cells observe zero application activations.
Overlay profiles show3 anchored parent plan reuses in each mode, including bounded failure, without recompiling the parent.

Five cProfile builds per cell preserve successful `_draft`/clone/provider work counts. `_draft` entries are5400 for
wide,7840 generic,3250 collection/template in full builds; configured usage does not change those operation counts.
For bounded builds cProfile observes505 draft/preflight entries for wide/generic/collection and445 template entries:
these include the five refused preflights. The deterministic compiler profiler records only admitted work
(100 drafts per bounded wide/generic/collection build,88 template drafts +12 metadata). Refused work is not passed off
as a successful graph allocation. Additional `admit`/`occurrence` calls prove configured accounting exists; self/cumulative
times in the raw `.prof` files are instrumented diagnostics and are not latency comparisons.

Independent traced allocation medians below are KiB (1024bytes), peak / retained. Five samples are retained in rawJSON
for each cell. Runtime rows retain an unactivated runtime after deleting the explicit builder and collecting; bounded
rows retain the actual safe `ContainerBuildError` and its evidence, including normal exception-frame lifetime, rather
than a usable partial runtime. Declarations precede tracing. This is current-state allocation evidence, not a matched
pre19/pre20 allocation effect estimate and not RSS. Budget configuration itself precedes measurement.

| Shape | None peak/retained KiB | Unlimited peak/retained KiB | Generous peak/retained KiB | Bounded failure peak/retained KiB |
| --- | ---: | ---: | ---: | ---: |
| wide-24 | 1877.4/1668.9 | 1879.3/1669.3 | 1878.8/1668.8 | 378.2/137.1 |
| generic-8-roots | 2832.3/2430.5 | 2850.1/2447.3 | 2847.7/2444.6 | 519.9/180.9 |
| collection-12 | 839.9/706.7 | 841.1/706.8 | 840.9/706.6 | 287.5/96.4 |
| template-12 | 1021.2/734.5 | 1022.1/734.3 | 1022.2/734.5 | 451.8/84.2 |

Full-build allocations/retained metadata are close in three shapes; generic configured rows retain about17KiB more
traced bytes in these samples. The bounded rows retain much less traced data because broad occurrence expansion
stops, but the compiler may already have performed preparation/materialization (generic retains all4 specializations;
template has produced12 outputs before the occurrence stop). No byte bound or leak/RSS guarantee follows from a work
budget. Compiler lifetime correctness is established separately by the GC-disabled weak-reference tests; these samples
explicitly collect at retention checkpoints and therefore are not the cleanup proof.


## Source and artifact audit

Production and benchmark source was frozen before final latency and verified unchanged after all unprofiled and
instrumented captures. Only the measurement README/work note changed after checks; no production/test/guide source
changed. The50-file initial freeze manifest covers all production Python plus original/new timing helpers/control;
the final review source manifest adds public docs/tests/config/evidence/README. Mutable work-status notes and parent-owned
README status are excluded from source manifests. The artifact manifest hashes raw captures, every profile/cProfile,
summary, proof, required logs, discovery logs and strict-built site files; the manifest itself is excluded to avoid self-hashing.

| Source/artifact | SHA256 |
| --- | --- |
| `/tmp/item20-final-source-digests.json` | `6dd682872fe0b6e461ce819ec4abb0151f11139828fa71a0736a26b551eb497c` |
| `/tmp/item20-final-review-source-digests.json` | `47af6c2fd764902031df1975af52c7d80fe633c3a59926c4e3f945dd857baa57` |
| `/tmp/item20-final-artifact-digests.json` | `1b85c94eb75bf8700e96055ac31e54973fedf2f5beac5ed3e679572b30bf5673` |
| `/tmp/item20-runtime-proof.json` | `6b74af2b66dae3902207a82b62128ae6d473739ee299724219271167c4d70bb0` |
| `/tmp/item20-before-1.json` | `fb6b627a3ca74da76a59b792277f474d8443992f9cd3cc29637d90b12137d6d6` |
| `/tmp/item20-before-2.json` | `0cc482735e4d7cad2605bc93866d9d94ccd0b58e960c312871579fef0035c02c` |
| `/tmp/item20-after-1.json` | `c35d800e20972aa9d9fac2187f94afc847ba864a21bb7728c279d6196fa1cbae` |
| `/tmp/item20-after-2.json` | `b791e4bccb5af7165989266ea56be6335e3b22ec0964c16764c7421dff7722b9` |
| `/tmp/item20-budget-modes-1.json` | `edfd5603625eccdab025b4f51a206d898f2a6cf904143db91c7a3374981e043c` |
| `/tmp/item20-budget-modes-2.json` | `2cead2199e307f6d5fab2ea21c31ca6b3b6aa98eaf096cbbb13a7a331d5eb9b4` |
| `/tmp/item20-runtime-after-1.json` | `f51d2cdcd31affbad8bcd7eb8199bbb10e98e8011e6d17fe08e4d22987052c53` |
| `/tmp/item20-runtime-after-2.json` | `76fcd4da0e5946c2a9eff97ebaced9656d2808778a2c7582447ecbe1dc555c67` |
| `/tmp/item20-evidence.json` | `2516547e712ff30ccc215c91cdcb68be8904bc6581b4b92608a3e5b33bd8e75b` |
| `/tmp/item20-overlay-evidence.json` | `29e2a7a9a1dd5f684f8395c2ea53618763b890bad388541de77c5cf23d41d29a` |
| `/tmp/item20-ci-final.log` | `a34b46b8348e027479aad92d7bcddc34acd90c8350fa4dd90ea15f923f037518` |
| `/tmp/item20-docs.log` | `47da25d5a7760df368fb98a520d7007b2a28818df6c95c81cd4c0ac9239054c5` |

Exact reproduction commands are in [benchmarks/README](../benchmarks/README.md#compilation-budgets-item-20).
Disabled final runs use `--baseline item20-final`, before runs `item20-post19`, mode runs `item20-final-modes`, and
runtime controls `item20-runtime`, all `--no-compare`, fixed25/warmup5 and explicitly named `/tmp` outputs.
No existing release baseline, item19 artifact or default baseline was overwritten. Instrumentation and supported checks
ran in separate windows from latency capture; no parent/reviewer jobs overlapped the final capture window.

## Review decision

Independent Sol High review: **APPROVE / KEEP**. All findings are resolved. The reviewer verified all50 frozen-source,
56 review-source and203 artifact hashes, runtime/control-source equivalence, required CI/docs/supported-Python logs,
operation/allocation evidence and the limitations of noisy timing samples. No causal small-overhead guarantee follows
from these samples. No production source changed after passing checks and final captures.

No commit, push, version bump or release has been performed by the implementer. The parent owns the final local
commit/status update after review.
