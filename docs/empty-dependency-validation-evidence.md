# Empty dependency-name validation evidence

Step 7 skips `_validate_dependency_names()` immediately when its dependency mapping
is empty. An empty set cannot contain an unknown callable argument name. The only
production Python change from the frozen Step 6 wheel is this two-line guard in
`clean_ioc/container.py`. There is no signature cache, global state, garbage
collection change, graph change or new build option.

Registration still extracts callable signatures through
`legacy._set_up_dependencies()` and `_get_arg_info()`. That extraction includes
required arguments, annotations, defaults and configured extra names. Nonempty
name mappings still follow the existing inspection, `**kwargs` allowance,
unknown-name rejection and best-effort `TypeError`/`ValueError` fallback. Missing
required components still fail during dependency compilation. Decorator argument
selection and pre-configuration signature extraction retain their separate checks.

## Regression and validation

`tests/test_empty_dependency_validation.py` adds 16 cases. Its multi-route fixture
uses three parameterless classes inheriting `object.__init__`, repeated under two
infrastructure branches per route. Contextual selection callbacks force each
occurrence to be visited, preserving the expensive path even when invariant
subplans are available. At both 4 and 32 routes, with diagnostics on and off,
registration performs exactly three builtin signature parses; build and resolution
add none. All expected callbacks, transient identities and dependency values are
verified, and constructors remain dormant until resolution.

Other cases cover invalid arguments on constructors, closed generic constructors
and factories; recovery after a failed build; required constructor, factory,
decorator and pre-configuration dependencies; parameterless factories and
initializers through scope-builder and ordinary-scope paths; generic and factory
`**kwargs`; and the existing fallback for uninspectable nonempty targets.

Full `make ci` passed: **2,029 tests**, Ruff lint and formatting, typing,
documentation examples and benchmark discovery. The existing warning is unchanged.
The subsequently added evidence script also passed its lint, formatting and typing
checks. Package versions, lockfiles, resource budgets, assertions in existing
tests, application sources and timeout settings were not changed by this step.

## Frozen-wheel synthetic comparison

`benchmarks/empty_dependency_validation_evidence.py` constructs a synthetic route
graph using actual Bark `UtcDatetimeProvider`, `HeaderBasedPrefixResolver` and
`ResolveQueueNameFromHeader` implementations. Each route has three direct helpers
and one shared infrastructure class with the same three helpers. Helpers are
transient and dependency-only. Contextual cases add an opaque selection callback
that must run independently for every helper occurrence. Other cases allow
invariant infrastructure reuse.

The two independent environments install the same support requirements and
unchanged Bark wheel, paired with frozen Step 6 and Step 7 Clean IoC wheels.
They run outside both repositories on **CPython 3.14.4, macOS/arm64**. No editable
install or source override is used. Imports and registration precede measurement;
the fixture imports 860 modules before build. Both stages use
`provider_roots=()`, `allow_scope_builders=False`, `check_unreachable=False` and
`aggregate_errors=False`.

Each scenario has three fresh-process normal samples per stage, alternating stage
order; one separate traced sample per stage; and one separate diagnostic counter
sample per stage. Normal samples have neither tracemalloc nor a profiler. Heap
tracing starts after identical pre-build garbage collection. Retained allocations
are sampled after build and garbage collection; the recorded peak is the maximum
during build, captured before graph serialization and runtime activation. RSS is
the whole process peak up to the end of build, including imports. Diagnostic
samples temporarily wrap signature/name validation functions and enable
`CompilationProfiler(max_records=0)`; their timings are not performance evidence.
All **80 subprocesses** succeeded with no stderr output.

| Routes | Context callbacks | Diagnostics | Step 6 median seconds | Step 7 median seconds | Step 6 traced peak MiB | Step 7 traced peak MiB |
| ---: | :---: | :---: | ---: | ---: | ---: | ---: |
| 64 | Off | Off | 0.037536 | 0.032455 | 4.508 | 0.856 |
| 64 | On | Off | 0.047339 | 0.033584 | 8.018 | 0.863 |
| 256 | Off | Off | 0.135982 | 0.107745 | 17.004 | 2.660 |
| 256 | On | Off | 0.173697 | 0.125513 | 31.176 | 2.561 |
| 512 | Off | Off | 0.270771 | 0.211225 | 33.702 | 5.029 |
| 512 | On | Off | 0.352041 | 0.232941 | 62.073 | 4.817 |
| 256 | Off | On | 0.152502 | 0.126132 | 18.458 | 4.104 |
| 256 | On | On | 0.204215 | 0.151736 | 33.047 | 4.370 |

At 512 contextual routes, median build time falls approximately **33.8%** and the
single traced peak approximately **92.2%**. These are measured synthetic results;
they do not estimate a Cop worker or service-readiness improvement. Three timing
samples and single heap samples do not establish a statistical confidence interval.

| Routes, diagnostics off | Context callbacks | Step 6 normal RSS range MiB | Step 7 normal RSS range MiB | Step 6 traced retained MiB | Step 7 traced retained MiB | Step 6 builtin parses | Step 7 builtin parses |
| --- | :---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 64 | Off | 90.64–134.19 | 86.34–86.97 | 0.565 | 0.546 | 130 | 0 |
| 64 | On | 94.17–94.91 | 86.62–87.03 | 0.567 | 0.569 | 256 | 0 |
| 256 | Off | 105.47–105.97 | 89.91–90.09 | 1.584 | 1.603 | 514 | 0 |
| 256 | On | 121.27–121.38 | 89.28–90.22 | 1.603 | 1.612 | 1,024 | 0 |
| 512 | Off | 126.02–126.30 | 94.27–94.48 | 2.973 | 2.979 | 1,026 | 0 |
| 512 | On | 157.08–157.20 | 94.05–94.33 | 2.984 | 2.981 | 2,048 | 0 |

The first small baseline RSS range contains a high sample; raw values are kept.
RSS depends on imports, allocation and collection timing, so the observed ranges
are not guaranteed application savings. Retained traced allocations remain
approximately unchanged, as expected for identical frozen runtime graphs. The
change removes transient signature-parsing work rather than graph records.

For each scenario, every stage/sample preserves manifest and validation
fingerprints, physical records, provider view count, public roots, selected
registration count, runtime helper types, transient instance separation and
constructor activation counts. Every compilation-profiler counter also matches
across stages. Context callbacks remain six per route. Diagnostic builtin parse
counts fall to zero while empty and nonempty validator invocation counts remain
equal across stages; only the work inside the empty-name calls is skipped.

## Actual paired Cop API and worker measurements

The pinned Cop checkout is `97011b424a439297eaf7e90c73023e2a7f89573c`.
Fresh-process measurements compare installed Step 6 and Step 7 Clean IoC wheels
with the unchanged Bark wheel on the same CPython 3.14.4 macOS/arm64 host.
The application source hash is identical across stages:
`03e92831c52227a55aeb7fee5534647559251b47f2e747727e3c10e81207b2d3`.
The five Cop composition roots retain their existing build options; Step 7 makes
no Cop production edit.

Timing begins immediately around `get_container(config)` after imports,
configuration construction and identical pre-build garbage collection. It covers
composition and compilation, and does not measure full service readiness.
Three normal samples per application/stage alternate stage order. A separate
single worker sample per stage starts tracemalloc after imports and configuration;
retained allocations are sampled after build and garbage collection. RSS is the
whole process peak. Diagnostic signature counters and live-heap snapshots are
separate investigations, excluded from these performance samples.

| Application | Stage | Median seconds (3 samples) | Physical records | Normal process peak RSS range MiB |
| --- | --- | ---: | ---: | ---: |
| API | Step 6 | 0.330947 | 3,528 | 218.59–224.28 |
| API | Step 7 | 0.313210 | 3,528 | 207.52–211.19 |
| Worker | Step 6 | 3.766082 | 51,827 | 382.41–386.16 |
| Worker | Step 7 | 3.399977 | 51,827 | 218.84–219.78 |

Median reported composition/build durations decrease approximately **5.4%** for
the API and **9.7%** for the worker. Physical records and zero provider views
are unchanged in all samples, as are the empty optional diagnostic sidecars.
The observed worker normal RSS ranges decrease substantially; they remain
measurements of these processes and do not guarantee identical allocation or
garbage-collection behavior on another host.

| Worker metric (1 traced sample per stage) | Step 6 bytes | Step 7 bytes |
| --- | ---: | ---: |
| Traced immediately after build | 100,038,608 | 40,131,440 |
| Traced after garbage collection | 38,466,893 | 38,469,996 |
| Traced peak | 187,126,382 | 55,537,218 |

The measured worker traced peak falls by **131,589,164 bytes (70.3%, approximately
125.49 MiB)**. Retained allocations differ by only **3,103 bytes** and are
effectively unchanged. This distinguishes the reduction in temporary allocation
peak from the final runtime graph footprint. The earlier six steps' retained
memory improvements did not reduce this worker peak; this isolated guard does
in the paired samples.

The earlier separate builtin-signature diagnostic attributed 2,803 of 2,812
parses to empty dependency-name validation: `UtcDatetimeProvider` (1,996),
`ResolveQueueNameFromHeader` (550), `HeaderBasedPrefixResolver` (253) and
`SystemMonotonicClock` (4). The Step 7 diagnostic reports **nine total parses**:
eight legacy registration `object` signatures and one unrelated `list` signature.
All 2,803 validator-driven builtin parses are gone. The parser's temporary
`sys.modules` copies had been identified in a separate live-heap investigation;
that intrusive snapshot changes allocation/collection timing and is not used
as paired performance proof. Diagnostic counts confirm the removed work;
the fresh-process samples above measure its application effect.

`benchmarks/empty_dependency_validation_application_results.json` preserves the
14 paired application samples, exact time/byte values, source and repository
fingerprints, wheel hashes and separate before/after signature counts. Absolute
source, wheel and installed module paths are omitted; private settings and
configuration content are not copied. Full suites, integration checks and Linux
readiness/resource-budget validation remain separate evidence.

## Source identity and reproduction

`benchmarks/empty_dependency_validation_results.json` contains sanitized raw
samples, summaries, parity fingerprints, compiler counters, wheel/source/script
hashes and the support-requirement hash. Absolute environment paths and private
application settings are omitted. Clean IoC remains on `version2` at
`3d576f10427d506b414889af21ad95291c39cccf`, with prior dirty work preserved.

| Artifact | SHA-256 |
| --- | --- |
| Step 6 Clean IoC wheel | `0ee5ac2bf2573da9a4dd630bc3552f40a28e03c531d7ce4fe0406f7b2ad04cd9` |
| Step 7 Clean IoC wheel | `2828273554efd910ef99ff8c008b58b42590aa7a8579b1206bda469a080f4b7a` |
| Unchanged Step 3 Bark wheel | `c48697d371ac93d97f462235e64330f25dc11e7b64be46e6d6150585379550eb` |

The Step 7 wheel is frozen in the sequential evidence root's `wheels/step7`.
Install each pair independently with `--no-deps` after installing the identical
support requirements. From a directory outside the repositories, run the chosen
environment's interpreter:

```sh
DD_TRACE_ENABLED=false /path/to/isolated-env/bin/python /path/to/clean_ioc/benchmarks/empty_dependency_validation_evidence.py --routes 512 --contextual
DD_TRACE_ENABLED=false /path/to/isolated-env/bin/python /path/to/clean_ioc/benchmarks/empty_dependency_validation_evidence.py --routes 512 --contextual --measurement heap
DD_TRACE_ENABLED=false /path/to/isolated-env/bin/python /path/to/clean_ioc/benchmarks/empty_dependency_validation_evidence.py --routes 512 --contextual --measurement counts
```

Actual Cop paired composition measurements and downstream/full-suite/Linux
readiness checks are recorded separately. No application result is inferred from
this synthetic comparison. No commit, push, release or version update was performed.
