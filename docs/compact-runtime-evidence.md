# Compact immutable runtimes

`ContainerBuilder.build(allow_scope_builders=False)` and
`ScopeBuilder.build(allow_scope_builders=False)` opt into a runtime that releases
its composition blueprint after successful compilation, validation, graph
finalization and warmup planning. The default remains `True` for compatibility.
The flag must be an actual `bool`; an invalid value fails before discovery,
profiling or builder consumption. Failed compilation still leaves the builder
reusable and performs the same validation as the default mode.

```python
from clean_ioc import ContainerBuilder

builder = ContainerBuilder()
builder.register(str, instance="ready")
with builder.build(allow_scope_builders=False) as container:
    with container.new_scope() as scope:
        assert scope.resolve(str) == "ready"
        assert not scope.allow_scope_builders
```

Ordinary scopes, private managed-provider acquisition scopes and per-call scopes
reuse the frozen plan and inherit this restriction. `new_scope_builder()` and
the direct public `ScopeBuilder(scope)` constructor fail with a clear
`RuntimeError` mentioning `allow_scope_builders=False`, before allocating mutable
composition state. A default-mode parent can compile a compact overlay; that
child and its descendants cannot compile further overlays. Its parent retains
its own capability and composition, and remains the owner of inherited
singletons. A compact child therefore does not release its parent's blueprint.

The runtime captures declared root scope slots, ensured import module names and
validation-only rule definitions independently. It retains executable steps,
selected registrations, build arguments, ownership and cleanup state, warmup
plans, graph/report data and explicitly requested diagnostics. Registration
selection predicates, template preparation and registries belonging solely to
the dropped blueprint can be collected after the caller releases the builder.
Executable factories, instances, value providers and pre-configuration state
remain available, and validation-only rules remain live for subsequent
`validation_report()` calls. Any application state captured by those necessary
callables remains live too. Retaining the original builder also retains its
mutable composition; compact mode cannot release references owned by callers.

No runtime graph records or escaped components are truncated. Graph manifests,
filters on frozen roots, selection census with diagnostics, validation reports,
selected registration discovery, aliases, scope provision, warmup, sync/async
resolution, resolution profiling and cleanup continue to operate without
compilation. Public provider-root selection remains a separate build option.
The compiler still prunes orphan blueprint definitions in the same way before
freezing either mode; no compilation-phase optimization is mixed into this
change.

## Verification

`tests/test_compact_runtime.py` adds 26 regression cases. Weak references prove
registration eligibility predicates and build-only rules are collectible in
both diagnostic modes, while validation-only rules remain callable. Tests cover
sync and async private managed acquisitions, declared slots and aliases, ordinary descendants,
resolution profiling, warmup, full graph inspection, selected discovery,
anchored parent singleton ownership and overlay cleanup. They also verify direct
constructor guards, malformed-flag builder reuse, failed-build reuse, and
identical manifests and build reports between compact and compatible execution.

Full Clean `make ci` passed: 1,956 tests, Ruff lint/format, typing, documentation
examples and benchmark discovery. Production adoption is limited to all five
pinned Cop composition roots and the worker/response processor foundation tests.
An audit of pinned Cop and Bark production found no `new_scope_builder()` or
`ScopeBuilder(...)` use; Bark's existing overlay tests retain default behavior.

## Reproducible synthetic evidence

`benchmarks/compact_runtime_evidence.py` uses the existing Bark five-family route
fixture: 24 commands, queries, events, replies and query results, with 48 sagas.
It compares compact and compatible modes on the same installed wheel, including
both diagnostic settings. Every run is a fresh process, with no `PYTHONPATH`
override. Import warmup precedes measurement, tracing starts before composition,
and the builder is deleted and garbage collected before retained memory is
sampled. Timing is build-only; traced runs are reported separately from normal
time. Manifest generation and consumer discovery run after memory sampling.
The process retains the same dynamic message types in both modes.

Use a separate Python 3.14.4 environment containing the support requirements,
the final Clean wheel and the unchanged step-3 Bark wheel, installed separately
with `--no-deps` (the development wheel deliberately does not alter dependency
pins). Run each of these three times, alternating the two modes, from a directory
outside either repository:

```sh
<evidence-python> <clean-repo>/benchmarks/compact_runtime_evidence.py --routes 24 --mode compatible
<evidence-python> <clean-repo>/benchmarks/compact_runtime_evidence.py --routes 24 --mode compact
```

Repeat with `--heap`, `--diagnostics`, and both options together. Raw process
results are saved in `benchmarks/compact_runtime_results.json`.

Frozen wheel SHA256:

- Clean `clean_ioc-2.0.0rc2-py3-none-any.whl`:
  `0d95a134c793af7d88b22621fd222b73a40ba81dbd6d8e7ea814ca4f54b5f27b`
- Bark `bark_core-1.0.0b1-py3-none-any.whl` (unchanged step 3):
  `c48697d371ac93d97f462235e64330f25dc11e7b64be46e6d6150585379550eb`

Installed source fingerprints (relative Python paths and bytes, sorted,
NUL-delimited SHA256):

- Clean: `006f20abf67383a9261344d6a7702301b81fd00d3b1391833825bf02c91c05df`
- Bark: `caf579f9fa1713dad3838f6ebe2eb50014dbfda84ec9fbdd747817814c114213`

On macOS 26.7.1 ARM64, Python 3.14.4, three runs per mode and setting gave
these medians (bytes are raw measured counts):

| Diagnostics | Runtime mode | Build seconds, untraced | Peak RSS, untraced | Traced retained bytes | Traced peak bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| False | Compatible | 0.71318 | 146,276,352 | 12,875,518 | 21,505,717 |
| False | Compact | 0.71736 | 145,358,848 | 10,746,272 | 21,504,686 |
| True | Compatible | 0.84384 | 153,485,312 | 22,039,509 | 28,502,084 |
| True | Compact | 0.85238 | 152,731,648 | 19,905,937 | 28,494,722 |

Compact mode reduced traced retained memory by 2,129,246 bytes (16.5%) without
diagnostics and 2,133,572 bytes (9.7%) with diagnostics. Traced compilation peaks
were effectively unchanged. The small timing and RSS differences are not grounds
for claiming a build-time or peak-memory improvement. Retained memory is sampled
after releasing the builder and collecting garbage; peak RSS covers the whole
process and includes dependency imports.

All 24 processes produced exactly the same complete execution manifest:
`c3b8d85ebbf479cafe886e8f11dc56a3142851a561792069f11adfcf65947945`.
Each retained 8,735 physical records, zero provider view contexts, 396 public
roots and 780 selected catalogue entries. Both modes discovered all 24 command
consumers and 24 reply consumers. Composition was retained only in compatible
mode. One-off interpreter-shutdown WeakMethod callback messages were saved in
the artifact stderr log; each measured process completed successfully.

These synthetic results demonstrate runtime retention savings without changing
execution shape. Actual Cop measurements and downstream suites are a separate
paired verification against the frozen step-3 wheels; synthetic evidence alone
does not establish application startup readiness or compliance with a Linux
memory limit.


## Paired Cop application measurements

The pinned Cop revision `97011b424a439297eaf7e90c73023e2a7f89573c` was
measured in fresh Python 3.14.4 processes on macOS 26.7.1 ARM64, alternating
frozen step-3 and step-4 application snapshots and their installed wheels. The
Bark wheel is identical in both stages. Step 3 uses `provider_roots=()`; step 4
also passes `allow_scope_builders=False` at the actual Cop composition roots.
Diagnostics remain disabled by default.

The application imports, configuration construction and a garbage collection
complete before timing or tracing begins. Measurement surrounds the actual
`get_container(config)` call, including composition and compilation. Traced
retained memory is sampled after garbage collection with the container still
live. Process peak RSS includes the earlier imports and configuration. There
are three normal samples per application/stage and one separate traced worker
sample per stage; traced timing is not included in normal timing medians.

| Application | Metric | Step 3 | Step 4 |
| --- | --- | ---: | ---: |
| API | Median seconds, untraced | 0.347922 | 0.370129 |
| API | Peak RSS range, MiB, untraced | 216.8–220.8 | 216.8–217.0 |
| API | Physical records | 3,528 | 3,528 |
| Worker | Median seconds, untraced | 3.916230 | 3.861126 |
| Worker | Peak RSS range, MiB, untraced | 380.6–395.6 | 383.2–392.3 |
| Worker | Physical records | 51,827 | 51,827 |
| Worker | Traced retained bytes after GC | 39,403,812 | 38,527,365 |
| Worker | Traced peak bytes | 187,134,591 | 187,137,888 |

The worker retained 876,447 fewer traced bytes after garbage collection (2.2%).
Its traced peak differed by only 3,297 bytes and was effectively unchanged.
Normal RSS ranges overlap. The API median increased by about 0.022 seconds and
the worker median decreased by about 0.055 seconds; these samples establish no
guaranteed startup-time or RSS improvement. Graph record counts remain unchanged
at 3,528 for the API and 51,827 for the worker. Every application sample retained
zero provider views and zero optional explanation sidecars.

Sanitized raw samples and frozen snapshot/wheel provenance are preserved in
`benchmarks/compact_runtime_application_results.json`. Absolute local paths and
configuration/settings content are excluded. Its source artifact is
`step4-comparison.json`, with the SHA256 recorded in that JSON. These application
measurements support a modest retention improvement; they do not establish
Linux startup readiness or compliance with a particular memory limit. Downstream
unit and integration validation is recorded separately when complete.

## Downstream verification

The frozen step-4 Clean IoC wheel with the unchanged step-3 Bark wheel passed
5,946 Bark unit tests (26 skipped), 494 Cop unit tests and all 64 Cop integration
tests (373.49 seconds). All catalogue capacity assertions passed; the complete
integration run exercised the five application hosts, synchronous inventory
admission and progress queries. Clean IoC's full CI passed 1,956 tests. These
checks used installed wheels with no dependency source overrides, but the
released dependency pins have not yet been updated. Linux budget verification
remains separate from these macOS results.

For an additional resolution-focused mode, combine this option with
`explain_metadata=False`. See [optional explanation metadata](compiler-tooling.md#optional-explanation-metadata)
for the explicit inspection limits and independent ownership rules.
