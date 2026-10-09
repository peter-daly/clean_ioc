# Selected registration catalogue evidence

Actual application verification for the frozen step 3 wheels: Bark 5,946 unit
tests pass (26 skips); Cop 494 unit tests and all 64 integration tests pass
(373.88 seconds). All four shared-process catalogue memory assertions remain
unchanged and pass. Subsequent test-only typing fixes pass 76 focused tests;
selected-file type checks and repository lint/format checks pass. The full Bark
type check still reports three pre-existing errors in the unchanged DynamoDB
serialization test and the existing saga protocol variance warning.

Step 3 separates runtime discovery metadata from public resolution roots.
`Scope.selected_registrations` (also available on `Container`) returns one frozen
`tuple[RegistrationInfo, ...]` for the scope's retained executable plans. Bark's
command and reply consumer registries use this catalogue; all five internal route
contribution families now use `root_policy="dependency_only"`. Handler entrypoints
and other applications of `scope.components` retain their existing contracts.

The catalogue traverses selected root, public provider, private managed-target
and warmup component trees after validation. It does not compile new dependency
trees, scan raw graph records as selected definitions, or enumerate the builder
blueprint. Provider views reuse their selected source subtree. Entries contain
only IDs, canonical visible service types, static implementation types, names and
tags. Explicitly closed constructor/factory aliases remain closed; unknown or
uninspectable factory result evidence becomes `None` without rejecting a valid
build. Instance values and occurrence/graph/blueprint references are not captured.

Deduplication uses registration ID plus canonical visible service type, preserving
closed requests and exposed aliases without requiring hashable factories.
Root/dependency depth-first order is deterministic. Rejected/dead dependency-only
registrations, synthetic components and unexposed architecture-only boundary roots
are excluded. Selected dependencies of exposed boundary plans remain discoverable.
Ordinary scopes share their parent's tuple; compiled overlays capture their own
selections, including anchored parent singleton dependencies. Capture works with
`diagnostics=False` and does not rerun eligibility callbacks or activate factories.

The catalogue also remains available with `explain_metadata=False`, independently
of `allow_scope_builders`. This corrects the RC3 restriction: successful reduction
keeps the frozen discovery tuple while still releasing explanation indexes and
unneeded occurrence records. The historical measurements below predate that fix;
they do not establish downstream application verification of reduced-metadata mode.

## Verification

- Clean IoC `make ci`: **1,930 tests passed**, including ten new catalogue cases;
  Ruff, formatting, type checking, documentation examples and benchmark discovery
  passed. The existing single pytest warning remains.
- Bark focused route, messaging, saga and command-messaging suites: **162 passed**.
  Changed production/test files passed Ruff and formatting. Public API generation
  `--check` passed with the environment's Ruff available on `PATH`.
- Five-family route tests prove no public contribution roots, catalogue discovery,
  deferred handler validation before activation, and actual dispatch.
- Command/reply registry tests prove selected closed consumer routes remain
  discoverable and imported producer-only/dead private routes are excluded.
- Existing default/named route precedence, exact/fallback dispatch and saga
  fanout checks pass. A new bounded-growth regression dispatches command/event
  routes through two sagas per route at 4, 8 and 16 routes, verifying both executors
  and linear physical-record growth.
- Catalogue tests also cover repeated provider-map use of the same registration,
  decorators and their private dependencies, type aliases/boundary visibility,
  overlay ordering, unhashable factories, fallback/context eligibility without
  repeated callbacks, warmup and anchored singleton ownership.

Full downstream Bark/Cop suites and Linux startup validation remain parent-owned
checks. The actual paired Cop composition/build measurements are recorded below;
they are separate from the synthetic experiment and do not establish readiness or
a guaranteed RSS improvement.

## Installed-wheel experiment

`benchmarks/selected_registration_catalogue_evidence.py` builds five operation
families with two sagas for every route group. It verifies inferred command and
reply consumer counts after compilation. Each sample is a fresh Python **3.14.4**
process using installed wheels in isolated environments, run outside both source
repositories. Dependencies are identical, `provider_roots=()` and
`diagnostics=False` are held fixed, and `DD_TRACE_ENABLED=false` is held fixed in
both stages. There are three uninstrumented samples and one separate tracemalloc
sample per stage/size. No dependency source overrides are used.

Timing covers `build()` only, after composition/imports. RSS is the process peak,
including imports/composition. Traced allocations start after composition and are
sampled after build and garbage collection, with builder and container still
alive. Catalogue shallow bytes count its tuple and entries, excluding referenced
IDs, tags and type objects. They are not a complete transitive retained-size
measurement.

| Routes per family / sagas | Stage | Physical records | Public roots | Public route roots | Catalogue entries | Catalogue shallow bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 4 / 8 | Step 2 | 2,163 | 116 | 20 | unavailable | — |
| 4 / 8 | Step 3 | 1,475 | 76 | 0 | 140 | 11,248 |
| 8 / 16 | Step 2 | 4,303 | 220 | 40 | unavailable | — |
| 8 / 16 | Step 3 | 2,927 | 140 | 0 | 268 | 21,488 |
| 16 / 32 | Step 2 | 8,583 | 428 | 80 | unavailable | — |
| 16 / 32 | Step 3 | 5,831 | 268 | 0 | 524 | 41,968 |

All 20/40/80 selected internal routes are present in the new catalogue; command
and reply registries report exactly 4/8/16 consumers in both stages. Removing
public contribution roots also removes their public implementation aliases.
Physical records grow by 535 per additional route group in Step 2 and 363 in
Step 3; the catalogue adds 32 entries per group. At 16 groups, graph records fall
by **2,752 (32.1%)**, while the catalogue itself adds approximately **41 KiB** of
shallow metadata. The tradeoff is explicit: even applications that do not read
the catalogue retain the frozen metadata tuple.

| Routes per family | Stage | Median build seconds (3 samples) | Median process peak RSS MiB | Traced retained MiB (1 sample) | Traced peak MiB (1 sample) |
| --- | --- | ---: | ---: | ---: | ---: |
| 4 | Step 2 | 0.1654 | 120.69 | 1.843 | 3.119 |
| 4 | Step 3 | 0.1259 | 120.42 | 1.503 | 2.780 |
| 8 | Step 2 | 0.3256 | 124.39 | 3.381 | 6.027 |
| 8 | Step 3 | 0.2394 | 123.80 | 2.703 | 5.112 |
| 16 | Step 2 | 0.6424 | 132.72 | 6.841 | 12.269 |
| 16 | Step 3 | 0.4796 | 131.31 | 5.440 | 10.677 |

These samples show a graph/allocation reduction and lower synthetic build times.
The RSS difference is small and allocator/import dominated; it is not a guaranteed
application RSS reduction. Single traced samples describe allocations, not a
statistical confidence interval. Raw samples preserve dependency shutdown
`WeakMethod` warnings in stderr; all child processes exited successfully and
consumer-count checks passed.

## Actual paired Cop API and worker measurements

The parent measured the pinned Cop checkout (`97011b4`) in fresh processes using
installed Step 2 and Step 3 Clean IoC/Bark wheel pairs, with three uninstrumented
samples for each application/stage. Python is **3.14.4** on the same macOS/arm64
host. Cop composition roots retain `provider_roots=()` and default diagnostics.
The application source hash is unchanged between stages. Timing starts immediately
around `get_container(config)`, covering composition and compilation while
excluding imports and configuration construction. Tracemalloc likewise starts
after imports/configuration construction and garbage collection. These durations
do not measure end-to-end service readiness. RSS records the whole process peak,
including imports and tracing where applicable.

| Application | Stage | Median seconds (3 samples) | Physical records | Process peak RSS range MiB (3 samples) |
| --- | --- | ---: | ---: | ---: |
| API | Step 2 | 0.471337 | 5,240 | 224.3–230.7 |
| API | Step 3 | 0.355628 | 3,528 | 216.7–220.5 |
| Worker | Step 2 | 4.377916 | 59,353 | 389.7–466.5 |
| Worker | Step 3 | 3.893924 | 51,827 | 383.3–417.5 |

API physical records fall by **1,712 (32.7%)** and worker records by
**7,526 (12.7%)**. Median reported durations decrease by approximately 24.5% and
11.1%, respectively. API RSS is lower in these samples; worker RSS ranges overlap
substantially. Three samples do not establish a guaranteed RSS reduction or a
service startup improvement.

A separate single traced worker process per stage measures retained allocations
and transient peak independently:

| Worker metric | Step 2 bytes | Step 3 bytes |
| --- | ---: | ---: |
| Traced immediately after build | 149,289,668 | 100,544,651 |
| Traced after garbage collection | 43,309,316 | 39,401,131 |
| Traced peak | 187,136,182 | 187,138,117 |

Retained traced allocations after garbage collection fall by **3,908,185 bytes
(9.0%, approximately 3.73 MiB)**. The traced peak changes by only **1,935 bytes**
and is effectively **unchanged**. Lower retained graph/allocation costs must not
be described as a reduction in the worker's transient allocation peak. The
immediate-after-build measurement likewise does not replace the measured peak.

`benchmarks/selected_registration_catalogue_application_results.json` preserves
all 14 samples, exact byte/time values, source and repository fingerprints, and
wheel hashes from the parent's `step3-comparison.json`. Absolute source, wheel and
module paths are omitted. Private settings/configuration content is not copied.
Full suites, integration checks and capped Linux readiness measurements are
separate validation, not inferred from these composition measurements.

## Reproduction and frozen artifacts

Install the corresponding Clean IoC/Bark wheels independently with `--no-deps`
after installing the same support requirements. Bark's wheel metadata retains
its existing Clean IoC prerelease pin; this experiment intentionally measures the
explicit local wheel pair without changing versions or lockfiles. Run outside
source repositories with the chosen environment's interpreter:

```sh
DD_TRACE_ENABLED=false /path/to/isolated-env/bin/python /path/to/clean_ioc/benchmarks/selected_registration_catalogue_evidence.py --routes 16
DD_TRACE_ENABLED=false /path/to/isolated-env/bin/python /path/to/clean_ioc/benchmarks/selected_registration_catalogue_evidence.py --routes 16 --heap
```

Raw samples, package source fingerprints, script hash, wheel paths and SHA-256
hashes are in `benchmarks/selected_registration_catalogue_results.json`.

| Artifact | SHA-256 |
| --- | --- |
| Step 2 Clean IoC wheel | `d1c24b886910a463b55e0f1ad24dfc52850500b50c6bfbf06e8a4ee41681ac5c` |
| Step 2 Bark wheel | `047d046561f219b331cd812feb2c52fe9883de070226e1b4ed602222012bf758` |
| Step 3 Clean IoC wheel | `27803660b15d2f1d334792857164d399089b96bbf252c637554c820fdf5b2fa4` |
| Step 3 Bark wheel | `c48697d371ac93d97f462235e64330f25dc11e7b64be46e6d6150585379550eb` |

The Step 3 wheels are frozen in the sequential evidence root's `wheels/step3`
directory. Production sources remain frozen for the parent's paired downstream
measurements. No commits, releases, version updates or lockfile changes were made.
