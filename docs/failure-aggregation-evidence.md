# Optional diagnostic root retries after compilation failure

Both `ContainerBuilder.build()` and `ScopeBuilder.build()` now accept
`aggregate_errors: bool = True`. The compatibility default preserves independent
root recompilation after a reportless compiler failure to aggregate additional
findings, even when `diagnostics=False`. Production can explicitly pass
`aggregate_errors=False` to avoid that diagnostic work.

This is a diagnostic-retry policy, not a claim that every compiler phase stops
on its first finding. Alias/boundary/template preparation, existing report-bearing
errors, entrypoint/warmup checks and application build rules retain their existing
collection behavior. Missing dependencies, cycles, ambiguous provider admission,
lifespan/ownership errors, boundary contracts and application safety conditions
still fail startup. No validation is disabled. The option is independent of
optional history capture and unreachable advisories.

For a reportless compiler error, no-retry mode retains the original error code,
complete error path, safe message and captured structural evidence, and associates
that evidence with `attempt:1`. Selection/eligibility callback exceptions retain a
safe request path captured only when the callback fails. Their arbitrary exception
text is never inspected. Unsupported arbitrary exceptions can lack a path or
structural evidence; the compiler does not invent evidence or replay callbacks to
obtain it. Original exceptions remain the failure cause.

With `diagnostics=True`, a no-retry failure has one primary partial-graph attempt,
including its usual bounded witness and graph capture. The complete error path in
the report is not replaced by that bounded witness. Without diagnostics there is
no optional partial graph. `BuildReport.checked_roots` and the partial graph's root
counts are zero diagnostic roots, not zero primary compilation work. The omission
of retries is intentional and is not represented as a budget exhaustion or omitted
retry attempt. A profiler reports state `failed` and has no diagnostic retry phase.

Diagnostic-attempt allowance is unused in no-retry mode. Every primary compilation
and callback allowance remains enforced, and allowance exhaustion keeps its normal
error report. Failed builders remain reusable. Successful graphs, selected
catalogues, validation findings, ownership and cleanup are unchanged; the option
is not retained in the immutable runtime. An overlay chooses its own flag, with the
same compatibility default. Ordinary scopes never compile.

CLI checks and build matrices still build with diagnostics and compatibility
aggregation. Runtime validation continues to evaluate its existing build/validation
contracts; it never silently recompiles an existing runtime or a failed builder.
Applications can request aggregate diagnosis on a reusable builder explicitly.
All five pinned Cop `get_container` roots and its worker/response foundation tests
now pass `aggregate_errors=False` alongside `provider_roots=()`,
`allow_scope_builders=False` and `check_unreachable=False`. Diagnostics remain
disabled by their existing default. Existing API inventory, saga coverage, sync
admission, progress/fanout and ownership build rules remain enabled.

## Verification

`tests/test_failure_aggregation.py` adds 39 regression cases covering both
history settings, root/overlay builders, failed-builder repair, invalid-flag
refusal before profiling/discovery, original code/path/evidence, nested arbitrary
callback redaction and request attribution, boundary identity, diagnostic and
callback allowances, profiler failure state, report-bearing application findings,
entrypoint/warmup safety, alias preparation aggregation, ambiguous providers,
captive lifespans, cycles, invalid template arguments, CLI/matrix aggregation,
long witness bounds, valid manifests/catalogues and singleton acquisition/cleanup.

Full Clean `make ci` passed: **2,013 tests**, Ruff lint/format, typing,
documentation examples and benchmark discovery. The added benchmark script also
passed lint, formatting and typing checks. The seven changed Cop files passed its
existing Ruff lint and formatting checks. No package versions, lock files, test
limits, commits, pushes or releases changed. Parent-owned actual application
measurements and downstream/Linux suites are separate acceptance evidence.

## Reproducible synthetic comparison

`benchmarks/failure_aggregation_evidence.py` models 120 independent application
roots, each with six independent dependency-only stages and a distinct missing
request. Eligibility callbacks execute on those stages before the invalid root
fails. Factories/constructors never activate on the failure path. A matching valid
fixture registers every missing service and checks the compiled manifest,
validation, catalogue, resolution and cleanup after sampling.

The aggregate diagnostic loop visits all 840 visible service keys, including the
720 dependency-only stages; those standalone retries produce no executable roots
or callbacks under the existing root policy. Alongside the original primary
attempt, this is 841 compiler attempts, 726 eligibility callbacks and 120
independent error findings. No-retry mode performs one primary attempt, six
callbacks and produces one original finding. This deliberately exercises realistic
registration volume and independent failures; it is not an actual Cop measurement.

Use separate installed-wheel Python 3.14.4 environments. The frozen step-5 wheel
runs `baseline`; the frozen step-6 wheel runs compatibility `aggregate` and
production `no-retry`. Both environments use identical support packages:
`funcie==0.2.0`, `typetoolbox==0.4.0`, `typing_extensions==4.16.0`. No source-path
or dependency overrides are used. Run from outside the source repository:

```sh
<step5-python> <clean-repo>/benchmarks/failure_aggregation_evidence.py --roots 120 --depth 6 --mode baseline
<step6-python> <clean-repo>/benchmarks/failure_aggregation_evidence.py --roots 120 --depth 6 --mode aggregate
<step6-python> <clean-repo>/benchmarks/failure_aggregation_evidence.py --roots 120 --depth 6 --mode no-retry
```

Repeat with `--diagnostics`, `--heap`, both, and each setting with `--valid`.
Run three fresh processes per mode/setting in alternating mode order. Imports and
an empty build are warmed before sampling. Tracing begins before fixture
composition; timing surrounds only build. A small wrapper counts `_Compiler.compile`
entries, and simple callback counters observe eligibility. Failed-build trace
sampling includes live diagnostic artifacts and tracebacks before disposal; it
is not retained-runtime memory. Valid runtime manifest/validation generation and
activation happen after sampling. Process peak RSS includes earlier imports.
Traced timing is excluded from normal time comparisons.

All 72 processes completed with zero stderr bytes. Sanitized raw samples and
provenance are in `benchmarks/failure_aggregation_results.json`. The source raw
artifact SHA256 is
`31a30a418eb9a45e5405c40dd65d053fa563bf7b059fe14f7f0c4034ee520caa`.
No absolute local paths or application configuration contents are recorded.

Frozen wheel SHA256:

- Step 5 Clean `clean_ioc-2.0.0rc2-py3-none-any.whl`:
  `8e35ee7c5a34e0db3db0c5b7417f9f528fa281f0171a3e3546a663f30fe6adb9`
- Step 6 Clean `clean_ioc-2.0.0rc2-py3-none-any.whl`:
  `0ee5ac2bf2573da9a4dd630bc3552f40a28e03c531d7ce4fe0406f7b2ad04cd9`
- Unchanged step 3 Bark wheel for parent-owned application runs:
  `c48697d371ac93d97f462235e64330f25dc11e7b64be46e6d6150585379550eb`

Installed Python-source fingerprints (relative paths/bytes, sorted and
NUL-delimited SHA256):

- Step 5: `7537fb789dddebe9c8520110a553efea055a8629f7f2d3ea2acf10e3337807fd`
- Step 6: `e0322e63e1975cf506ea66dff9dfcd10b9c50278837ffee742e8fedffcebe7e4`

On macOS 26.7.1 ARM64, Python 3.14.4, three samples per mode/setting gave these
medians for **invalid builds** (memory columns are raw measured byte counts):

| Diagnostics | Mode | Build seconds, untraced | Process peak RSS, untraced | Traced peak bytes |
| --- | --- | ---: | ---: | ---: |
| False | Step 5 baseline | 0.138670 | 52,477,952 | 10,707,974 |
| False | Step 6 aggregate | 0.137346 | 52,527,104 | 10,708,174 |
| False | Step 6 no-retry | 0.008692 | 49,790,976 | 8,175,582 |
| True | Step 5 baseline | 0.163226 | 53,379,072 | 11,524,577 |
| True | Step 6 aggregate | 0.166493 | 53,526,528 | 11,524,689 |
| True | Step 6 no-retry | 0.013949 | 50,511,872 | 8,493,322 |

Against step-6 compatibility aggregation, no-retry failure time decreased 93.7%
without diagnostics and 91.6% with diagnostics. Traced compilation peak decreased
23.7% and 26.3%, respectively. Process peak RSS medians were about 2.7 MB and
3.0 MB lower for this invalid fixture. These observations apply to diagnostic
work after an invalid build, not successful production startup or a live runtime.
Every invalid sample preserved the same original first path fingerprint
`583146a2e0307d8cf34b7d113abe827372d88f0c45b9e7e39cd15351fca06967`
and left the builder reusable. Compatibility aggregate diagnostics retained the
existing bounded first 101 attempts out of 841; no-retry retained its one primary
attempt when diagnostics were enabled.

The corresponding **valid build** medians were:

| Diagnostics | Mode | Build seconds, untraced | Process peak RSS, untraced | Traced peak bytes |
| --- | --- | ---: | ---: | ---: |
| False | Step 5 baseline | 0.104261 | 54,312,960 | 11,019,849 |
| False | Step 6 aggregate | 0.105447 | 54,312,960 | 11,019,985 |
| False | Step 6 no-retry | 0.103446 | 54,591,488 | 11,019,985 |
| True | Step 5 baseline | 0.129744 | 55,607,296 | 12,257,226 |
| True | Step 6 aggregate | 0.132261 | 55,836,672 | 12,262,435 |
| True | Step 6 no-retry | 0.132613 | 56,016,896 | 12,254,379 |

These valid samples establish no timing, RSS or memory improvement. All 36 valid
samples produced the identical complete manifest fingerprint
`a521578107cb88f6cf2db8331c5a91022663f84203083e52f3b2d6b53efe40d4`
and validation fingerprint
`196f254502b808aec982fa0ee62cf8a51eeae87fad243a25bec225801f674fd6`.
Every valid build compiled once, called 720 eligibility callbacks and retained
960 physical graph records, 120 public roots, 960 catalogue entries and zero
provider views. All public roots resolved after sampling. Detailed retention
columns in the raw artifact include live build artifacts, not a builder-released,
after-GC retained-runtime comparison.

## Paired Cop application measurements

The parent measured pinned Cop revision
`97011b424a439297eaf7e90c73023e2a7f89573c` in fresh Python 3.14.4
processes on macOS 26.7.1 ARM64, alternating frozen step-5 and step-6
application snapshots and installed wheels. Both stages use the unchanged Bark
wheel, disabled diagnostics, `provider_roots=()`, `allow_scope_builders=False`
and `check_unreachable=False`. Step 6 additionally passes
`aggregate_errors=False` at the actual production composition roots.

Application imports, configuration construction and garbage collection complete
before timing/tracing begins around the actual `get_container(config)` call,
including composition and compilation. Retained memory is sampled after garbage
collection with the container still live. Process peak RSS includes earlier
imports and configuration. There are three separately untraced samples per
application/stage, plus one separately traced worker sample per stage; traced
timing is excluded from normal medians.

| Application | Metric | Step 5 | Step 6 |
| --- | --- | ---: | ---: |
| API | Median seconds, untraced | 0.340447 | 0.345083 |
| API | Process peak RSS range, MiB, untraced | 217.03–222.98 | 218.80–223.39 |
| API | Physical records | 3,528 | 3,528 |
| Worker | Median seconds, untraced | 3.786948 | 3.799308 |
| Worker | Process peak RSS range, MiB, untraced | 386.08–421.97 | 381.88–424.84 |
| Worker | Physical records | 51,827 | 51,827 |
| Worker | Traced retained bytes after GC | 38,468,007 | 38,477,628 |
| Worker | Traced peak bytes | 187,137,877 | 187,138,235 |

These successful application builds establish no startup-time, RSS or memory
improvement. The API median increased about 0.0046 seconds and the worker about
0.0124 seconds. Traced worker retention increased 9,621 bytes (0.025%); its
traced compilation peak increased 358 bytes and was effectively unchanged.
The no-retry option targets failure diagnostics and does not remove work from a
successful compile. Every paired sample kept the same graph record counts,
zero provider views and zero optional occurrence/parameter/generic explanation
sidecars. Application safety rules remain enabled.

Sanitized raw samples and frozen application/wheel provenance are preserved in
`benchmarks/failure_aggregation_application_results.json`. The original
`step6-comparison.json` SHA256 is
`b3e56f5d20dfd83f0e0556b485d8e17500588ee99fb97caa3a415e323335b157`.
Absolute local paths and all configuration/settings contents are excluded.
Downstream application suites and Linux startup-budget verification remain
separate evidence. The immediately preceding frozen step-5 wheels passed all
64 Cop integration tests; the parent runs final combined integration verification
after the next separately measured compiler step.

## Downstream verification

The frozen step-6 Clean IoC wheel with the unchanged step-3 Bark wheel passed
5,946 Bark unit tests (26 skipped, 85.90 seconds) and all 494 Cop unit tests
(27.32 seconds). The immediately preceding step-5 composition passed all 64
Cop integration tests; the complete integration suite is scheduled again for
the final combined build. Step 6 changes diagnostic work after failures, and
its valid-build manifests and paired Cop graph counts remain unchanged. These
runs use installed wheels with no dependency source overrides; dependency pins
and Linux resource-budget acceptance remain separate.
