# Minimal entrypoint histories and deferred reachability advisories

Ordinary builds now select marked entrypoints without creating diagnostic-only
`CompilationExplanation` and `CandidateDecision` histories. With
`diagnostics=False`, the graph retains no known-selection or census-entrypoint
histories. Eligibility, filter invocation order/count, fallback suppression,
provider target selection, decorator semantics and selected entrypoints remain
unchanged. With diagnostics enabled, the existing full capture path remains.

`graph.explain(component).selected` still exposes the compiled identity,
origin/layer and fallback facts needed by application safety rules. Decorator
and template semantic evidence, graph traversal, boundary contracts, manifests
and selected registration catalogues remain available. Service/filter
explanations and selection census continue to require `diagnostics=True`.
The executable graph shape is unchanged by this step.

Both `ContainerBuilder.build()` and `ScopeBuilder.build()` accept
`check_unreachable: bool = True`. The compatibility default keeps the built-in
`unreachable-component` advisory scan in startup. Production composition can
pass `False` to defer that scan to `validation_report()` or CLI `check`.

```python
from clean_ioc import ContainerBuilder

builder = ContainerBuilder()
builder.register(str, instance="ready")
builder.register(int, instance=1)
builder.mark_entrypoint(str)
with builder.build(check_unreachable=False, provider_roots=(), allow_scope_builders=False) as scope:
    assert not scope.build_report.warnings
    assert [issue.code for issue in scope.validation_report().warnings] == ["unreachable-component"]
    assert scope.resolve(str) == "ready"
```

The deferred runtime's immutable `build_report` omits unreachable-component
warnings. `validation_report()` recovers the same findings, order and
first-occurrence deduplication as an eager report, including custom build-rule
findings that duplicate a built-in advisory. The plan retains only a boolean
and scalar insertion position for this purpose. Reachability is reconstructed
from frozen graph roots and selected entrypoints, traversing dependencies,
pre-configurations and decorators. It does not replay selectors, constructors,
factories, template callbacks or discovery. Each deferred validation request
performs a fresh reachability scan; custom validation-only rules retain their
existing fresh-call behavior.

Missing entrypoints, boundary contracts, missing dependencies, cycles,
lifespans/ownership, sync-provider admission, other built-in findings and all
build-mode application validation rules still run during startup. Compilation
callback budgets apply in both history modes. An invalid flag is rejected
before discovery, profiling or builder consumption. Failed builds retain the
same essential errors and builder reuse behavior; no runtime exists on which
to request deferred advisories after failure.

Ordinary nested scopes reuse the frozen graph and policy. A compiled overlay
chooses its own flag, defaulting to eager compatibility behavior. Both retained
composition and compact runtimes support deferred validation; the latter do
not retain a blueprint merely to recover advisories. Strict CLI checks still
fail for deferred unreachable warnings unless their code is explicitly ignored.
All five pinned Cop composition roots and its worker/response foundation tests
now explicitly pass `check_unreachable=False` alongside the earlier production
options.

## Verification

`tests/test_deferred_advisories.py` adds 18 regression cases covering callback
counts, fallback/provider/decorator selection, optional history gating, exact
warning recovery and ordering/deduplication, built-in and custom build errors,
validation-only rule freshness, callback-budget refusal with earlier findings,
invalid flags and builder reuse, boundaries, compact overlays, ordinary scopes,
minimal component origin facts, manifests/catalogues and strict CLI validation.
Validation is checked after compilation and activation are replaced with test
failures, proving that the deferred scan uses immutable plans.

Final full Clean `make ci` passed: 1,974 tests, Ruff lint/format, typing,
documentation examples and benchmark discovery. No package versions or lock
files were changed. Actual Cop measurements and downstream suites use the
frozen wheel separately from the synthetic fixture below.

## Reproducible synthetic comparison

`benchmarks/deferred_advisories_evidence.py` uses the same Bark five-family route
fixture as earlier steps: 24 commands, queries, events, replies and query
results, with 48 sagas. Compare three modes in fresh processes: frozen step-4
`baseline`, step-5 `eager`, and step-5 production `deferred`. All modes use
`provider_roots=()` and `allow_scope_builders=False`; both diagnostic settings
are measured. This separates removal of optional history from advisory scan
deferral.

Use separate Python 3.14.4 environments with the same support requirements and
installed wheels, with no dependency source path overrides. The baseline uses
the frozen step-4 Clean wheel; the other modes use the step-5 wheel. Each uses
the unchanged step-3 Bark wheel installed separately with `--no-deps`. Run each
command three times in alternating mode order, from outside either repository:

```sh
<baseline-python> <clean-repo>/benchmarks/deferred_advisories_evidence.py --routes 24 --mode baseline
<step5-python> <clean-repo>/benchmarks/deferred_advisories_evidence.py --routes 24 --mode eager
<step5-python> <clean-repo>/benchmarks/deferred_advisories_evidence.py --routes 24 --mode deferred
```

Repeat with `--heap`, `--diagnostics`, and both options together. Imports are
warmed before measurement; tracing begins before composition. Reported timing
surrounds only build. The builder is released and garbage collected before
retained memory sampling, with the runtime and identical dynamic message types
still live. Validation, manifest generation and consumer discovery occur after
sampling, and deferred validation time is reported separately. Peak RSS covers
the complete process, including imports. Traced timing is excluded from normal
time comparisons. Raw sanitized results are in
`benchmarks/deferred_advisories_results.json`.

Frozen wheel SHA256:

- Step 4 Clean `clean_ioc-2.0.0rc2-py3-none-any.whl`:
  `0d95a134c793af7d88b22621fd222b73a40ba81dbd6d8e7ea814ca4f54b5f27b`
- Step 5 Clean `clean_ioc-2.0.0rc2-py3-none-any.whl`:
  `8e35ee7c5a34e0db3db0c5b7417f9f528fa281f0171a3e3546a663f30fe6adb9`
- Unchanged step 3 Bark `bark_core-1.0.0b1-py3-none-any.whl`:
  `c48697d371ac93d97f462235e64330f25dc11e7b64be46e6d6150585379550eb`

Installed source fingerprints (relative Python paths and bytes, sorted,
NUL-delimited SHA256):

- Step 4 Clean: `006f20abf67383a9261344d6a7702301b81fd00d3b1391833825bf02c91c05df`
- Step 5 Clean: `7537fb789dddebe9c8520110a553efea055a8629f7f2d3ea2acf10e3337807fd`
- Bark: `caf579f9fa1713dad3838f6ebe2eb50014dbfda84ec9fbdd747817814c114213`

On macOS 26.7.1 ARM64, Python 3.14.4, three samples per mode/setting gave
these medians (bytes are raw measured counts):

| Diagnostics | Mode | Build seconds, untraced | Peak RSS, untraced | Traced retained bytes | Traced peak bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| False | Baseline | 0.72332 | 144,982,016 | 10,740,457 | 21,498,602 |
| False | Eager | 0.72528 | 144,523,264 | 10,633,068 | 21,391,414 |
| False | Deferred | 0.74053 | 145,457,152 | 10,638,961 | 21,397,661 |
| True | Baseline | 0.85473 | 153,845,760 | 19,909,170 | 28,498,165 |
| True | Eager | 0.84317 | 153,108,480 | 19,903,400 | 28,493,396 |
| True | Deferred | 0.84024 | 153,550,848 | 19,908,079 | 28,497,105 |

Without diagnostics, removing entrypoint histories in eager mode saved 107,389
traced retained bytes (1.0%). Production deferral saved 101,496 bytes (0.9%)
against step 4. The roughly 6 KB difference between eager and deferred retention
falls within the traced sample variation; the scan does not retain additional
runtime graph records. Traced compilation peak was 100,941 bytes (0.5%) lower for production
deferral, a small difference that does not establish a broad peak-memory
improvement. Diagnostic-mode retention and peaks were effectively unchanged.
Normal timing and RSS results establish no improvement: the lean production
median increased by about 0.017 seconds, while richer timings moved slightly
in the other direction. No startup-time or RSS reduction is claimed.

Deferred validation medians were 0.01631 seconds without diagnostics and
0.01653 seconds with diagnostics. Eager medians were 0.01004 and 0.01041 seconds,
respectively; these include the fixture's custom validation-only rules. The
roughly 6 ms reachability work moves from build to an explicit validation call.
This fixture has no unreachable findings; nonempty recovery is established by
the regressions above.

All 36 processes produced the same complete manifest fingerprint:
`c3b8d85ebbf479cafe886e8f11dc56a3142851a561792069f11adfcf65947945`.
Each retained 8,735 physical records, zero provider views, 396 public roots,
125 entrypoint roots and 780 catalogue entries, and discovered all 24 command
and 24 reply consumers. Validation findings were identical in every mode.
With diagnostics disabled, known/census entrypoint history counts dropped from
125/125 to 0/0. With diagnostics enabled they remained 125/125. The common
validation fingerprint was
`4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.

One-off interpreter-shutdown WeakMethod callback messages are preserved in the
artifact stderr log; every measured process completed successfully. The
synthetic results demonstrate a modest reduction in retained presentation data
and coherent advisory deferral. Actual Cop results, downstream application
suites and Linux startup-budget validation remain separate evidence.

## Paired Cop application measurements

The pinned Cop revision `97011b424a439297eaf7e90c73023e2a7f89573c` was
measured in fresh Python 3.14.4 processes on macOS 26.7.1 ARM64, alternating
frozen step-4 and step-5 application snapshots and installed wheels. Both
stages use the same Bark wheel, `provider_roots=()`,
`allow_scope_builders=False` and disabled diagnostics. Step 5 additionally
passes `check_unreachable=False` at the actual composition roots.

Application imports, configuration construction and garbage collection
complete before measurement begins. Timing/tracing surrounds the actual
`get_container(config)` call, including composition and compilation. Retained
memory is sampled after garbage collection with the container still live.
Process peak RSS includes earlier imports and configuration. There are three
normal samples per application/stage, plus one separately traced worker sample
per stage. Traced timing is excluded from normal timing medians.

| Application | Metric | Step 4 | Step 5 |
| --- | --- | ---: | ---: |
| API | Median seconds, untraced | 0.351712 | 0.349626 |
| API | Peak RSS range, MiB, untraced | 216.09–218.89 | 217.67–222.03 |
| API | Physical records | 3,528 | 3,528 |
| Worker | Median seconds, untraced | 3.914153 | 3.976732 |
| Worker | Peak RSS range, MiB, untraced | 380.84–386.03 | 387.55–439.17 |
| Worker | Physical records | 51,827 | 51,827 |
| Worker | Traced retained bytes after GC | 38,523,889 | 38,473,328 |
| Worker | Traced peak bytes | 187,135,460 | 187,136,683 |

The worker retained 50,561 fewer traced bytes after garbage collection (0.13%).
Its traced compilation peak increased by 1,223 bytes and was effectively
unchanged. API timing medians were similar; the worker median increased by
about 0.063 seconds. The measured step-5 worker RSS range was higher and
reached 439.17 MiB. These samples establish no startup-time,
RSS or compilation-peak improvement. The observed benefit is a small reduction
in retained entrypoint presentation data, with unchanged execution graph
counts: 3,528 for the API and 51,827 for the worker. Every application sample
retained zero provider views and zero optional occurrence/parameter/generic
explanation sidecars.

Sanitized raw samples and frozen source/wheel provenance are preserved in
`benchmarks/deferred_advisories_application_results.json`, including the SHA256
of its source artifact `step5-comparison.json`. Absolute local paths and all
configuration/settings content are excluded. Downstream suites and Linux
startup-budget validation are separate from these macOS paired results.

## Downstream verification

The frozen step-5 Clean IoC wheel with the unchanged step-3 Bark wheel passed
5,946 Bark unit tests (26 skipped), all 494 Cop unit tests and all 64 Cop
integration tests (353.25 seconds). Every catalogue capacity assertion passed.
These runs used installed wheels with no dependency source overrides. Clean
IoC full CI passed 1,974 tests. Dependency pins are not yet updated, and Linux
resource-budget verification remains a separate acceptance check.
