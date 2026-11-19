# Parent precedence: fresh benchmark comparison

Completed 2026-09-27 after the requested fresh run: 30 benchmarks, twice per
revision, 30 repeat samples each (3,600 repeat samples total). All four runs
completed successfully; production code was unchanged.

## Scope and method

Thirty benchmarks cover ten contextual builds, six root/collection runtime
checks, seven ordinary activation/scope cases, and seven existing lookup paths.
The sources are `benchmarks/bench_parent_precedence.py`,
`benchmarks/bench_clean_ioc.py` (the `compiled-runtime` case only), and
`benchmarks/bench_lookup_paths.py`. Identical sources run against both revisions.

Baseline: local `version2` at `63cbea4099ac774c2d03f62b94f7750b0cce0508`,
package 2.0.0b23. Candidate: the uncommitted `codex/parent-filter-precedence`
production files. Separate immutable snapshots prevent interference from edits.
The contextual benchmark detects API support outside timing, omitting the new
keyword on the baseline. Nonzero single-dependency cases deliberately choose a
different winner; this measures the cost of the new behavior.

Environment: Python 3.14.4, BenchBro 1.0.0, macOS 26.7 arm64, same interpreter and
dependencies. Fixed 30 repeats and 5 warmups, with each source's iteration counts:
3 builds per repeat, 20,000 calls for existing runtime paths and the two fast
contextual runtime controls, and 500 for the other contextual runtime paths.
Build timing includes registration, compilation and closing the unused container.
Runtime timing excludes fixture preparation, singleton warming and teardown.
Cyclic GC is disabled during each measurement, following the benchmark defaults.

Run order is baseline, candidate, candidate, baseline. Each is a fresh process;
all measurements are sequential. Reversing order on the second pair helps expose
time drift but cannot eliminate desktop background noise. There is no CPU affinity
or power-state control. No tests or other agent work run alongside these timings.

Raw JSON, Markdown, logs, the public-API runner and source hashes are retained in
the ignored `.benchbro/parent-precedence-rerun.tv42b0p3/` directory. The experiment
does not replace any repository or machine-local benchmark baseline. The earlier
[performance report](14-parent-precedence-performance.md) remains separate evidence.

## Results

Enabled single-dependency builds measured **+2.06% to +3.77%** against their
baseline counterparts. The largest enabled case increased from **14.401 ms to
14.909 ms**, about **0.508 ms (+3.53%)**. Default single-dependency builds ranged
from **-0.32% to +3.31%**; providers were **+2.49%** and collection builds **+0.29%**.

Runtime changes ranged from **-2.87% to +2.06%**. Cached singletons, transient
construction, five-component activation, scopes, generic lookups, providers and
collections remain close to baseline. These small local timing movements do not
establish a material runtime regression or a reliable speedup.

Times in the tables are microseconds per operation. Each revision's number is the
arithmetic mean of its two per-run medians; the change compares those means.
Pair columns retain each candidate/baseline comparison separately so averaging
does not conceal inconsistent measurements. The second pair ran candidate first.

### Build

| Benchmark | Baseline µs | Candidate µs | Change | First pair | Second pair |
| --- | ---: | ---: | ---: | ---: | ---: |
| single-dependency[1-parent-4-candidates-zero-defaults] | 2186.628 | 2234.931 | +2.21% | +2.58% | +1.84% |
| single-dependency[1-parent-4-candidates-explicit-precedence] | 2180.899 | 2255.493 | +3.42% | +4.87% | +1.93% |
| single-dependency[1-parent-16-candidates-zero-defaults] | 4984.649 | 4968.549 | -0.32% | -0.51% | -0.12% |
| single-dependency[1-parent-16-candidates-explicit-precedence] | 4784.604 | 4883.358 | +2.06% | +2.69% | +1.44% |
| single-dependency[8-parents-4-candidates-zero-defaults] | 6105.312 | 6117.764 | +0.20% | +0.42% | -0.01% |
| single-dependency[8-parents-4-candidates-explicit-precedence] | 6064.472 | 6292.875 | +3.77% | +3.12% | +4.41% |
| single-dependency[8-parents-16-candidates-zero-defaults] | 14527.757 | 15009.059 | +3.31% | +5.73% | +0.89% |
| single-dependency[8-parents-16-candidates-explicit-precedence] | 14401.139 | 14909.083 | +3.53% | +4.39% | +2.67% |
| provider-unique-eligible-16-candidates-8-parents | 15451.611 | 15835.781 | +2.49% | +3.76% | +1.23% |
| collection-16-candidates-8-parents | 19444.746 | 19501.361 | +0.29% | -0.26% | +0.85% |

### Runtime

| Benchmark | Baseline µs | Candidate µs | Change | First pair | Second pair |
| --- | ---: | ---: | ---: | ---: | ---: |
| direct-python-construction | 0.576 | 0.575 | -0.12% | +0.71% | -0.92% |
| resolve-pre-built-instance | 0.941 | 0.948 | +0.74% | -2.11% | +3.67% |
| resolve-cached-singleton | 0.885 | 0.880 | -0.57% | -2.09% | +0.95% |
| resolve-transient | 1.858 | 1.821 | -1.99% | -1.83% | -2.15% |
| resolve-five-component-plan | 6.194 | 6.143 | -0.83% | -1.85% | +0.20% |
| create-scope | 1.653 | 1.661 | +0.49% | +1.75% | -0.79% |
| resolve-request-slot-plan | 7.647 | 7.507 | -1.83% | -1.03% | -2.62% |
| cached-class-default | 0.888 | 0.869 | -2.17% | -3.54% | -0.78% |
| cached-class-filtered | 1.766 | 1.779 | +0.74% | +0.31% | +1.18% |
| cached-closed-generic | 1.838 | 1.822 | -0.90% | -0.72% | -1.08% |
| cached-union | 1.706 | 1.701 | -0.27% | -0.26% | -0.29% |
| provider-root | 2.496 | 2.505 | +0.36% | +1.28% | -0.55% |
| collection-root | 2.445 | 2.420 | -1.02% | +0.39% | -2.43% |
| has-component-class | 1.432 | 1.425 | -0.51% | +0.31% | -1.32% |
| contextual fixture / direct-python-control | 0.581 | 0.579 | -0.31% | -0.32% | -0.30% |
| contextual fixture / default-cached-root | 0.903 | 0.877 | -2.87% | -2.15% | -3.59% |
| contextual fixture / explicit-name-root | 12.853 | 13.117 | +2.06% | +0.29% | +3.81% |
| contextual fixture / or-root-32-candidates | 38.068 | 38.348 | +0.74% | -0.99% | +2.47% |
| contextual fixture / or-collection-32-candidates | 388.195 | 388.529 | +0.09% | -0.27% | +0.44% |
| contextual fixture / default-collection | 2.522 | 2.534 | +0.46% | +4.28% | -3.33% |

## Variability and limits

- All results contain 30 repeat samples. Maximum within-run CV was 8.54%, and
  maximum relative 95% confidence margin around a run's mean was 3.11%. These
  within-run bounds do not account for changes between processes.
- IQR outliers marked 17–25 of the 30 results noisy in each run, despite CV below
  10%. No outlier samples or completed runs were discarded.
- Unchanged-baseline median drift ranged from -5.14% to +2.80%; candidate drift
  ranged from -6.39% to +4.06%. The largest default build moved +5.73% in the first
  pair but +0.89% in the second. Its averaged +3.31% is not evidence of a stable
  3.31% cost. Several other control paths also change direction between pairs.
- Enabled build changes were positive in both pairs, broadly consistent with the
  earlier measured build premium. Exact percentages still vary; there is no
  universal slowdown estimate for every graph size or composition.
- Benchmark invocation overhead affects very short runtime calls. Cyclic GC is
  excluded during measurements. Allocation cost, end-to-end startup with GC,
  production workloads and other operating systems/interpreters were not measured.
- BenchBro's public comparison API accepted matching environments for both pairs.
  Its raw comparison records are saved, but the default generous warning/error
  thresholds are not being used as proof of zero regression. No new performance
  gate or threshold was introduced.

All 37 candidate production-file hashes match the workspace after the run. The
three benchmark files are byte-identical in the baseline and candidate snapshots.
Names, iteration counts, repeats and GC policy match across every result. Package
code, benchmark sources, version and Git state were not altered for the timings.

## Reproduction and artifacts

Artifacts: `.benchbro/parent-precedence-rerun.tv42b0p3/` contains `metadata.json`,
`run_selected.py`, `base-{1,2}.{json,md,log}`, `current-{1,2}.{json,md,log}`,
`comparison-{1,2}.json`, and the calculated `summary.json`.

The runner imports the three benchmark modules, selects the four named cases via
BenchBro's public `filter_cases` API, and invokes `run_cases` with 30 repeats,
5 warmups and fixed sampling. It asserts the package import path and presence or
absence of the new keyword before running. To reproduce, prepare baseline and
candidate snapshots, use the same interpreter/dependencies, set `PYTHONPATH` to
the chosen snapshot, and run the helper from it with the corresponding label.

The results support the existing assessment: a modest measured build cost for
explicit contextual precedence, without demonstrated material runtime cost. This
is evidence for the tested workloads, not a performance guarantee.
