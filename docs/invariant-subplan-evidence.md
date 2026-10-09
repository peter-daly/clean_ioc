# Invariant subplan reuse evidence — 7 October 2026

Early reuse now occurs before dependency compilation. The existing executable
interning remains a separate optimization after per-occurrence compilation.

## Safety and scope

The early cache belongs to one `_Compiler` instance and never enters the frozen
plan or survives into another build/retry. It stores only completed successful
subplans that emitted no new findings. A transitive unsafe-work epoch checks all
candidate alternatives and reached descendants, not merely the parent registration.
Only identity-recognized built-in unnamed/all selection filters may be skipped.
A user callback with a built-in-looking name receives ordinary evaluation.

Opaque/contextual candidate or selection policies, derivations, preferences,
parent precedence, boundary projections, providers/maps, per-call plans, runtime
context, slots, declared resolution requests, anchored descendants, decorators and
pre-configurations force fallback. Rejected decorator/configuration definitions
also force fallback because their applicability callbacks must run per occurrence.
A registration's own eligibility callback still runs outside subplan reuse, for
each occurrence, against its fresh metadata and full dependency subtree.

The key includes actual registration and layer identities, runtime closed type
identity, composition area, nearest singleton/long-lived retention owner context,
deferred boundary kind and source-inspection mode. Source registrations are retained
in the cached footprint, preventing recycled identity keys and hidden stack cycles.
Ordinary cycle and root captive checks precede lookup. The full cached registration
footprint must avoid the active stack; otherwise ordinary compilation resumes.
Ancestor retention contexts have distinct keys. Cleanup owners must be internal
to the cloned subtree; external promoted owners force ordinary compilation.

Reuse clones fresh occurrence records with distinct parent, argument, occurrence
and owner references, and shares immutable executable plans and diagnostic payloads.
It does not generalize the existing positive-source provider-view encoding. Physical
record allocation is unchanged for an identical selected tree. Budget accounting
charges every cloned record and checks its full logical depth. Runtime lifespan,
scope caches, async activation/cleanup and occurrence profiling retain their normal
semantics. No constructor, factory or parameter activation provider runs at build.

`candidate compilation attempts` counts entry into the registration compilation
pipeline, including cache lookup. `registration subplans compiled` and definition
`subtrees compiled` count actual admitted bodies. `invariant subplan cache hits`
and definition `subplans reused` count early reuse; `reused activation templates`
counts the independent post-compilation interning hits. Failed-build census and
selection history report actual evaluation rather than fabricated cache-descendant
attempts. Graph inspection, argument evidence, validation findings and partial
graph edges retain the new occurrence's path.

## Reproduction and development measurements

`benchmarks/invariant_subplan_evidence.py` compiles 64 public routes sharing six
levels of binary transient infrastructure, with two uses of the preceding type at
each level. Each sample starts a fresh Python 3.14.4 macOS arm64 process. Imports
and builder registration precede timing; all samples use zero-span compilation
profiling. Separate allocation samples use `tracemalloc`, whose overhead makes
those timings unsuitable for normal startup comparisons.

The disabled comparison only suppresses early cache lookup/storage. Existing
executable interning, all candidate selection, validation and graph records remain.
Its nominal `invariant subplans cached` counter records eligible store attempts into
a deliberately disabled benchmark sink; it is not a retained-cache measurement.
Raw final samples are in `benchmarks/invariant_subplan_results.json`.

Both modes retain 9,984 physical component records and 1,024 provider view contexts.
Actual registration subplan compilations fall from 8,192 to 71; dependency parameter
attempts from 8,128 to 76; candidate compilation entries from 8,192 to 140. The enabled
sample has 69 early cache hits, each of which may replace a larger descendant tree.
These are real skipped compilation calls; fresh graph records remain allocated.
Without allocation tracing, profiled build time falls from 1.3260 to 0.5464 seconds
and process peak RSS from 71,860,224 to 51,216,384 bytes in this synthetic shape.
Separate traced peak allocations fall from 28,232,542 to 10,489,767 bytes (about
63% lower), demonstrating reduced allocation independently of graph counters.

The same pinned Cop project and stage4 Bark development wheel used by the parent
verification were probed with the parent interpreter plus explicit development
`PYTHONPATH` pointing to this Clean IoC source. The installed parent environment was
not modified. These are source-development probes, not installed-wheel acceptance.
Settings were loaded from the existing supplied JSON without printing their values.

A profiled worker sample records 37,935 candidate compilation entries, 17,421 actual
registration subplans compiled, 20,514 early hits, 34,910 parameter attempts and
82,558 selection callbacks. Stage4 pre-reuse counts were 48,586 candidate entries,
46,025 parameter attempts and 103,860 callbacks. It retains the same 91,570 physical
records and 4,220 provider view contexts. A separate normal worker sample calls
`get_container(config)` without profiling and measures 6.5285 seconds and
555,532,288 bytes process high-water RSS. The parent's stage4 installed-wheel
baseline for the same app records 7.0405 seconds and 513,769,472 bytes. These
unpaired samples use different import routing and do not establish a repeatable
Cop RSS improvement: this candidate normal sample has higher high-water RSS.
The final independent profiled sample records 7.3293 seconds and 593,739,776 bytes.
Do not compare its timing against normal builds. RSS includes imports/settings and varies across processes. Paired final installed
wheel measurements belong to the parent acceptance run.

## Verification and limits

`make ci` passed with Ruff lint/format, ty, 1,805 tests, graph-change policy,
documentation examples and BenchBro discovery. Nineteen focused regressions cover
shared compilation growth, all occurrence/argument/export/profiler paths, opaque
and contextual callback fallback, own per-use eligibility, derivation/runtime
context/slots, same display names with distinct closed generic types, captive
ancestors, async scoped cleanup and overlay identity, failed validation/partial
paths, exact physical budgets/full depth, compiler release with GC disabled,
rejected decorator/configuration callbacks, descendant stack cycles, declared alias
identity and fresh-cache failed-build retries. Existing selection-census assertions
remain unchanged and truthful to evaluated work.

The five existing count assertion updates are the 2/4/8/16/32 parametrizations of
`test_many_sender_transport_eligibility_avoids_unrelated_subtree_compilation`.
For N routes, candidate entries become 3N+1, actual bodies 2N+2, parameter attempts
2N+1 and early hits N−1. Eligibility exclusions and successful route selection
assertions are retained. Post-compilation intern hits are separately zero in that
shape.

This bounded implementation shares diagnostic payloads and avoids repeated
compiler work, while retaining one physical record per occurrence. It does not
claim to eliminate all contextual compiler work or to meet the Linux 512 MiB/100m
readiness gate. The parent performs final installed-wheel downstream tests and
runtime measurements. Publication/released lock coherence remains a separate
release gate; no versions, published artifacts or Bark/Cop files were changed here.
