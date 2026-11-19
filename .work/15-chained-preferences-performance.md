# Chained preferences: performance and compatibility

Status: measured and verified, 2026-09-27; independent review recorded separately.

## Baseline and method

The baseline is completed item 14, including its uncommitted `parent_precedence`
implementation, not Git HEAD alone. Its 37 production hashes exactly match the
previously verified item 14 snapshot (1008 tests passed). The complete source
snapshot and hashes were saved before item 15 production edits in
`.benchbro/chained-preferences.0uxthurn/base/` and `baseline-metadata.json`.

The same [benchmark source](../benchmarks/bench_chained_preferences.py) runs on
both versions. It detects the new API once and constructs reusable chains during
module import, outside timing. The baseline omits preference declarations.
Enabled single builds deliberately select a different registration, using the
same implementation and dependency shape. This compares behavior costs rather
than asserting identical selected IDs.

Twenty-seven cases cover:

- Four combinations of 4/16 candidates and 1/8 parents, each with no chain,
  an eight-stage consumer chain resolving at stage one, an eight-stage consumer
  chain resolving at stage eight, or per-registration chains resolving at stage
  eight: 16 builds. Unresolved prefixes alternate all-true and all-false rules.
- An injected provider with exactly one eligible target per parent. The chain
  must be skipped; old failed ambiguous builds are not latency baselines for
  new successful builds. Functional probes establish the overlap benefit.
- A collection with consumer and registration chains configured; membership
  ignores both, preserving all registrations and their order.
- Six runtime cases: direct Python control, cached root, frozen injection with
  no chain and with a chain, explicit root predicate, and collection lookup.
- Three additional [early-tail cases](../benchmarks/bench_preference_tail.py)
  with 16 candidates and 8 parents, resolving at stage one of a 1-, 8- or
  64-stage consumer chain. These probe the cost of recording skipped stages;
  chain construction is outside timing.

Build timing includes registration, compilation and closing the unused container.
Chain construction is excluded, so this is not a measurement of repeatedly
allocating new chain objects at each registration. Runtime fixture preparation,
singleton warming and teardown are excluded. Runtime cases activate frozen plans.

Environment: Python 3.14.4, BenchBro 1.0.0, macOS 26.7 arm64, same interpreter and
installed dependencies. Fixed 30 repeats, 5 warmups, 3 builds per repeat. Runtime
cases use 5,000 calls per repeat, except direct/cached controls (20,000) and
collection lookup (1,000). Cyclic GC is disabled during measurement. No CPU
affinity or power-state control is used; desktop background activity is uncontrolled.

Two sequential unchanged-baseline runs establish median drift of -5.44% to
+5.02%. Small deltas require caution. The comparisons retain raw quality
fields, outlier flags and between-run variability; no latency budget is imposed.
Agent tests are paused for the timing windows.

Raw JSON, Markdown, logs and configuration are retained in the ignored artifact
directory `.benchbro/chained-preferences.0uxthurn/`. Source hashes identify both
snapshots; repository benchmark baselines are not replaced.

## Compatibility

Final Python 3.14.4 `make ci` passes: **1072 tests**, including **64 new preference
tests**, plus lint, formatting, type checking, documentation validation and
benchmark discovery. Log: `/tmp/item15-ci.log`. The single Starlette/httpx
deprecation warning is pre-existing.

Earlier full suites passed on Python 3.11.13 (1052 passed, 8 skipped), 3.12.11
(1057 passed, 3 skipped) and 3.13.5 (1060 passed). These runs preceded the final
diagnostic corrections and additional tests. After those changes, all **282
affected tests** passed on each interpreter: preferences, existing parent
precedence, compiler tooling, compilation profiling, resolution profiling and
selection census. The final 64 preference tests are included in those reruns.
Logs are `pytest-311.log` through `pytest-313.log` and `pytest-final-311.log`
through `pytest-final-313.log` in the artifact directory. This distinguishes the
full earlier runs from the focused final verification.

## Results

Values below are the mean of the two per-run medians, not a pooled-sample estimate.
The paired deltas preserve both runs instead of hiding their variation. There are
no causal confidence claims from this uncontrolled desktop experiment.

**Assessment: keep the feature as opt-in composition policy.** The measured value
is reliable fallback selection ([use cases](15-chained-preferences-use-cases.md)),
not faster selection. At 16 candidates and 8 parents, early selection costs about
**1.23 ms (+7.35%)**; an eight-stage unresolved consumer chain costs **2.65 ms
(+16.17%)**, and registration chains cost **3.40 ms (+20.59%)**. Those late cases
perform 1024 preference callbacks, plus evidence capture, per build. These are
repeatable costs and should not be described as negligible or hidden by the
benchmark tool's broad default warning thresholds.

Absent-chain controls range from **-0.05% to +3.27%**; unique-provider and collection
build controls are **+1.38%** and **-0.13%**. No control shows a change larger than
the observed unchanged-baseline drift, although small implementation overhead
cannot be ruled out. Runtime ranges from **-2.38% to +1.88%**, consistent with
noise rather than a detected runtime penalty. Functional callback counters, not
small timing differences, establish that frozen activation does not run chains.

### Build measurements

Build values are milliseconds. Parents are dependency occurrences; candidates are
eligible registrations. `early` resolves at stage 1 of 8; `late` at stage 8 of 8.
Baseline columns omit chains entirely, rather than pretending the old API could
make the same soft choice.

| Case | Item 14 ms | Item 15 ms | Change | Paired changes |
| --- | ---: | ---: | ---: | ---: |
| 1-parent-4-candidates-absent | 2.830 | 2.829 | -0.05% | -0.07% / -0.03% |
| 1-parent-4-candidates-consumer-early-8 | 2.799 | 2.891 | +3.29% | +1.19% / +5.40% |
| 1-parent-4-candidates-consumer-late-8 | 2.934 | 2.901 | -1.11% | +1.57% / -3.70% |
| 1-parent-4-candidates-registration-late-8 | 2.810 | 2.897 | +3.10% | +4.47% / +1.75% |
| 1-parent-16-candidates-absent | 7.164 | 7.190 | +0.37% | +0.18% / +0.56% |
| 1-parent-16-candidates-consumer-early-8 | 7.104 | 7.385 | +3.95% | +3.53% / +4.37% |
| 1-parent-16-candidates-consumer-late-8 | 7.108 | 7.682 | +8.07% | +8.04% / +8.10% |
| 1-parent-16-candidates-registration-late-8 | 7.338 | 7.639 | +4.11% | +8.10% / +0.30% |
| 8-parents-4-candidates-absent | 6.642 | 6.709 | +1.00% | +0.80% / +1.21% |
| 8-parents-4-candidates-consumer-early-8 | 6.682 | 7.049 | +5.48% | +6.09% / +4.87% |
| 8-parents-4-candidates-consumer-late-8 | 6.659 | 7.532 | +13.10% | +10.82% / +15.37% |
| 8-parents-4-candidates-registration-late-8 | 6.837 | 7.513 | +9.89% | +7.23% / +12.71% |
| 8-parents-16-candidates-absent | 16.593 | 17.136 | +3.27% | +2.72% / +3.81% |
| 8-parents-16-candidates-consumer-early-8 | 16.753 | 17.983 | +7.35% | +6.00% / +8.70% |
| 8-parents-16-candidates-consumer-late-8 | 16.403 | 19.054 | +16.17% | +16.45% / +15.88% |
| 8-parents-16-candidates-registration-late-8 | 16.497 | 19.894 | +20.59% | +24.54% / +16.71% |
| provider-unique-eligible | 15.506 | 15.719 | +1.38% | +1.10% / +1.66% |
| collection-membership | 21.577 | 21.548 | -0.13% | +0.10% / -0.37% |

### Frozen runtime

Values are microseconds per invocation, including BenchBro's invocation harness.
The direct-Python row is a control, not a container speed claim.

| Case | Item 14 µs | Item 15 µs | Change | Paired changes |
| --- | ---: | ---: | ---: | ---: |
| direct-python-control | 0.578 | 0.564 | -2.38% | -2.82% / -1.96% |
| cached-root | 0.880 | 0.867 | -1.37% | -1.63% / -1.11% |
| frozen-injection-absent | 2.195 | 2.166 | -1.28% | -0.12% / -2.42% |
| frozen-injection-enabled | 2.203 | 2.181 | -0.97% | -1.69% / -0.25% |
| explicit-filter-root | 10.815 | 10.866 | +0.47% | +0.09% / +0.86% |
| collection-root | 8.081 | 8.233 | +1.88% | +1.92% / +1.84% |

### Unreachable chain tails

The reviewer found an initial implementation that allocated skipped evidence for
every configured stage. The fix represents an unreachable suffix as a compact
range and exits immediately. These builds all select a unique winner at the
first stage, with 16 candidates and 8 parents (128 actual callback calls), while
the configured chain length varies. Values are milliseconds.

| Configured stages | Item 14 ms | Item 15 run 1 ms | Item 15 run 2 ms | Item 15 mean median ms |
| --- | ---: | ---: | ---: | ---: |
| 1 | 16.863 | 18.097 | 18.012 | 18.054 |
| 8 | 16.739 | 18.251 | 18.816 | 18.534 |
| 64 | 16.831 | 17.751 | 17.688 | 17.720 |

There is no increasing build-time trend with the skipped suffix; 64 stages do not
cost more than 1 or 8 in either run. This supports removal of linear unreachable
work. It does not claim zero evidence overhead or that longer chains are faster.
Chain construction is excluded, and reached stages still incur the cost shown
in the late-chain measurements above.

### Measurement quality and artifacts

Many cases carry BenchBro noisy flags due to outliers. All samples were retained;
no manual trimming or reruns chosen for favourable results were used. The maximum
coefficient of variation is 10.69%; maximum reported relative 95% mean margin is
3.89%. Those are per-case distribution summaries, not confidence limits on the
between-version median changes. Between-run drift over the 24 main cases was
-5.44% to +5.02% for the baseline and -4.65% to +4.19% for the candidate. Tail-run
drift was -0.52% to +4.96% baseline and -0.47% to +3.09% candidate.

| Run | Cases flagged noisy | Outliers | Maximum CV | Maximum relative mean margin |
| --- | ---: | ---: | ---: | ---: |
| base-1 | 18/24 | 58 | 6.43% | 2.34% |
| base-2 | 18/24 | 58 | 5.88% | 2.14% |
| current-1 | 19/24 | 66 | 9.77% | 3.56% |
| current-2 | 21/24 | 68 | 10.69% | 3.89% |
| tail-base-1 | 2/3 | 6 | 5.74% | 2.09% |
| tail-base-2 | 2/3 | 4 | 4.43% | 1.61% |
| tail-current-1 | 3/3 | 7 | 3.60% | 1.31% |
| tail-current-2 | 2/3 | 6 | 3.88% | 1.41% |

`base-1.json`, `base-2.json`, `current-1.json`, `current-2.json` and their
`tail-` counterparts retain every raw case and quality field. Matching `.md` and
`.log` files preserve tool output. `benchbro-comparisons.json` uses BenchBro's
public `compare_runs`; its default 50% warning and 100% error thresholds are not
an acceptance budget. `summary-metrics.json` retains every pair, mean of medians,
absolute difference and drift used in these tables.

`baseline-metadata.json`, `measurement-metadata.json` and `current-metadata.json`
record provenance. All 38 current production files plus the two benchmark files
still matched the frozen current snapshot after measurement. Both benchmark
files match their corresponding baseline copy byte for byte. Production source
was frozen before timing; documentation-only edits continued. The repository's
committed benchmark baseline JSON was not modified.

A larger application with costly predicates, deeper graphs or many more ties can
have different startup costs. This benchmark covers one explicit workload range;
it does not measure peak memory, chain construction, every boundary combination,
or all production application sizes. No runtime ranking API or specificity
inference is introduced.
