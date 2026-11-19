# Parent precedence: performance and compatibility

Status: complete, 2026-09-27. Base is `63cbea4` (`2.0.0b23`); candidate is
the uncommitted `codex/parent-filter-precedence` implementation of work item 14.

A subsequent requested [30-benchmark rerun](14-parent-precedence-benchmark-rerun.md)
adds broader runtime coverage and repeats the comparison in reversed order.

## Method

The same [benchmark source](../benchmarks/bench_parent_precedence.py) runs against
an isolated archive of the base and the candidate. It detects the new registration
keyword once at module import. Base runs omit that keyword; explicit-precedence
single-dependency cases intentionally select a different winner on the candidate.
This is a cost comparison of the two behaviors, not a claim of equivalent wiring.

Build measurements include composition, compilation and closing an unused
container. They vary 4/16 candidates and 1/8 parents, with zero and nonzero
precedence. Additional builds cover an injected provider with one eligible target
per parent and a collection retaining all 16 candidates. The new overlapping
provider behavior is verified by the functional probes; an old failed build is
not a meaningful latency baseline for a successful new build.

Runtime measurements use warmed singleton plans, excluding fixture setup and
teardown. They cover a direct Python control, cached default root, named root,
an OR root filter, OR collection filter and default collection. Every named
registration declares precedence on the candidate, but runtime root selection
must ignore it.

Environment: Python 3.14.4, BenchBro 1.0.0, macOS 26.7 arm64; same interpreter and
installed dependencies for all runs. Fixed 30 repeats, 5 warmups, 3 builds per
repeat, 500 runtime calls per repeat (20,000 for the control and cached root).
Measurements are sequential, with agent test runs paused. Ordinary desktop
background load is uncontrolled. No CPU affinity or power-state control was used.
BenchBro disables cyclic garbage collection during each measurement
(`gc_control="disable_during_measure"`); these are not end-to-end GC measurements.

Two unchanged baseline passes establish local noise before comparison. Baseline
median drift ranges from -2.07% to +2.63%. Many samples have an IQR outlier and
BenchBro marks them noisy even with low coefficient of variation. Small changes
must therefore be treated as descriptive observations, not established regressions
or improvements. Runtime timings include benchmark invocation overhead.

Raw JSON, Markdown, logs, configuration and hashes are retained locally in the
ignored `.benchbro/parent-precedence.07imjvri/` directory. This does not replace
the repository's CI or default benchmark baseline. To reproduce, use the benchmark
above on both revisions with the fixed settings described here; the old revision
needs a copy of the new benchmark file.

## Results

Times below are microseconds per operation, using the arithmetic mean of the two
per-run medians for each revision. The last column shows drift between the two
candidate passes, not change against the base. These are descriptive measurements;
no statistical regression threshold was imposed.

| Case | Base µs | Candidate µs | Change | Candidate run-to-run drift |
| --- | ---: | ---: | ---: | ---: |
| single-dependency[1-parent-4-candidates-zero-defaults] | 2198.677 | 2239.327 | +1.85% | +0.30% |
| single-dependency[1-parent-4-candidates-explicit-precedence] | 2148.333 | 2220.840 | +3.38% | -0.04% |
| single-dependency[1-parent-16-candidates-zero-defaults] | 4979.896 | 5042.496 | +1.26% | -10.30% |
| single-dependency[1-parent-16-candidates-explicit-precedence] | 4819.507 | 4909.667 | +1.87% | -3.89% |
| single-dependency[8-parents-4-candidates-zero-defaults] | 6120.268 | 6129.271 | +0.15% | +0.95% |
| single-dependency[8-parents-4-candidates-explicit-precedence] | 6076.188 | 6282.681 | +3.40% | -0.57% |
| single-dependency[8-parents-16-candidates-zero-defaults] | 14846.406 | 14481.274 | -2.46% | -0.74% |
| single-dependency[8-parents-16-candidates-explicit-precedence] | 14570.694 | 15326.514 | +5.19% | +0.74% |
| provider-unique-eligible-16-candidates-8-parents | 15400.667 | 15650.701 | +1.62% | +0.67% |
| collection-16-candidates-8-parents | 19531.132 | 19430.482 | -0.52% | -0.08% |
| direct-python-control | 0.570 | 0.576 | +1.16% | -1.43% |
| default-cached-root | 0.876 | 0.894 | +2.15% | -0.56% |
| explicit-name-root | 12.783 | 13.040 | +2.01% | +4.25% |
| or-root-32-candidates | 38.077 | 37.850 | -0.60% | +0.46% |
| or-collection-32-candidates | 388.595 | 387.713 | -0.23% | -0.04% |
| default-collection | 2.515 | 2.480 | -1.37% | +1.10% |

Zero-precedence builds range from -2.46% to +1.85% by this summary. The single-parent,
16-candidate control varies substantially between candidate passes: +6.76% and
-4.24% against the mean baseline. This does not demonstrate a repeatable control-path
regression. Do not interpret the averaged decrease or increase as a speedup or slowdown.

Explicit-precedence single builds range from +1.87% to +5.19%; the largest tested
graph rises from 14.571 ms to 15.327 ms (about 0.756 ms). This is a plausible cost of
the stable maximum pass and extra captured loser evidence. Three cases repeat at
roughly +3–6%; the single-parent/16-candidate case is more variable, so its exact
cost is unresolved. The provider case is +1.62%, collection build -0.52%.

Runtime cases range from -1.37% to +2.15%, and the direct Python control is +1.16%.
These small movements do not establish a meaningful runtime effect in this noisy
local measurement. Static review confirms runtime selection/activation code was
not changed; precedence is evaluated only during compilation. This is not proof
of zero overhead for every workload or environment.

Across valid runs, per-case CV remained below 10%; IQR outliers still mark most
results noisy. The observed build cost is acceptable for the demonstrated
order-independent composition benefit; there is no evidence here for extending
scoring to roots or collections. No performance-driven production adjustment was
needed. Allocation cost and large real application graphs were not measured.

One initial candidate attempt is retained as `discarded-invalid-snapshot.*` and
excluded: a failed archive copy left baseline source in the temporary directory.
The two reported candidate passes use a verified snapshot; source hashes still
match the final production files. All four valid raw runs are `base-{1,2}.json`
and `current-{1,2}.json` in the artifact directory above.

## Compatibility and correctness

| Interpreter | Full suite | Final affected-path verification |
| --- | --- | --- |
| Python 3.11.13 | 997 passed, 8 skipped | 178 passed |
| Python 3.12.11 | 1002 passed, 3 skipped | 178 passed |
| Python 3.13.5 | 1005 passed | 178 passed |
| Python 3.14.4 | 1008 passed, final `make ci` | Included in full check |

The older-version full suites ran before the last three diagnostic regression
tests were added. After both final fixes, the complete parent-precedence,
selection-census and compiler-tooling modules passed again on each older version.
Skips are existing tests requiring newer Python type syntax or TypeVar defaults.
Each full run emits the existing Starlette/httpx deprecation warning.

The Python 3.14 full check includes lint, format, typing, executable documentation
and benchmark discovery. Logs for older versions are `pytest-{311,312,313}.log`
and `final-focused-{311,312,313}.log` in the artifact directory; the final full
check is `/tmp/clean-ioc-parent-precedence-ci.log`.

The separate Astra high reviewer passed 236 focused tests and independently
verified root, declared factory request and boundary cases. The [review](14-parent-context-registration-selection-review.md)
recommends KEEP after both findings were fixed. The reviewer also independently
recomputed every timing table row from the four raw runs and verified the final
production snapshot hashes; the cost evidence did not change that recommendation. The [actual before/after probes](14-parent-context-use-cases.md)
establish P1 1/2 → 2/2, P2 1/6 → 6/6 and a usable uniquely preferred provider;
control cases preserve the existing contracts.
