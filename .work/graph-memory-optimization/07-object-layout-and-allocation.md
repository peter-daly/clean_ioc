# 07 — Investigate object layout and avoidable allocation

Created: 2026-10-09\
Status: Complete — investigation only, 2026-10-09\
Assignment: GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning\
Agent: `/root/graph_memory_task_07`\
Starting revision: `d51b6f5`\
Prerequisites: Task 06's completed inventory and measurements; tasks 01, 02 and 05 retained

## Outcome and scope

Investigate four additional ways to reduce compiler and graph memory: effective
`__slots__` throughout inheritance, smaller component drafts, more compact graph
indexes, and checking the activation cache before constructing a redundant step.
Produce measured recommendations with a clear compatibility boundary for each.

This task is investigation only. The maintainer assigned GPT-6.1 Sol with medium
reasoning on 2026-10-09. Use bounded isolated probes and record their source and
results; production implementation and commits remain outside this assignment.
Proposals that need a new contract or further design must be marked not ready
for implementation.

Read the [shared plan](README.md), [task 06 result](06-result.md) and
[creation/lifetime inventory](06-inventory.md). Task 06's weak-cache and immutable
fact-sharing proposals remain separate, unimplemented candidates. Do not combine
their reported savings with an object-layout estimate.

## Starting evidence

- Runtime class inspection confirms that component drafts, records, definitions,
  graph/view objects, decisions, explanations and compiled dependency/decorator
  carriers already lack instance dictionaries.
- `_Step` has no `__slots__`. Slotted execution-step subclasses inherit its
  instance-dictionary and weak-reference support. Profiling mixins can introduce
  dictionary support independently. `_legacy._Registration` similarly inherits
  dictionary support from its `Registration` protocol base.
- A class declaring slots is therefore not sufficient evidence of a dictionary-free
  layout. Dictionary support also does not prove every instance has materialized
  a separate dictionary; measure actual allocation behaviour on each interpreter.
- `_ComponentDraft` currently has 27 declared slots. Eleven definition fields
  become shared only when frozen. Replacing those eleven references with one
  shared definition reference has an ideal shallow ceiling of about 6.76 MiB over
  88,558 primary drafts, before replacement objects, lookup keys and mutation costs.
- Task 06 measured origin-index backing storage at 5,242,960 bytes and decorator
  sidecar-index backing storage at 2,621,528 bytes at primary completion. These
  exclude referents and are not promised recoverable savings.
- Registration-step construction currently precedes activation-template cache
  lookup. A hit discards the newly constructed step after all dependency selection
  and callback work has already run.

These are investigation leads, not demonstrated improvements in peak or RSS.

## Investigation areas

### 1. Effective slots across inheritance

- Inventory high-volume metadata and executable carrier classes, including their
  complete base/mixin chains. Record actual instance-dictionary and weak-reference
  support, slot fields, live/created counts and shallow layout costs. Prioritize
  frequently created objects rather than low-count builders or exception classes.
- Audit `_Step`, ordinary and observed subclasses, profiling mixins, and legacy
  registration inheritance. Identify dynamic attribute writes, monkeypatch seams,
  generic/protocol machinery, copy/replacement behaviour and class-layout assumptions.
- Probe complete, dictionary-free layouts where compatible. Preserve required
  weak-reference support explicitly: task 06's proposed weak cache depends on it.
  Do not assume adding empty slots to one class fixes every derived class.
- Include profiling fields, multiple inheritance and supported Python versions.
  Measure effects on creation cost, actual allocated memory, peak and retained
  runtime size. Avoid creating dictionaries merely to inspect `obj.__dict__` in
  the measured run and then counting that observer-induced allocation as baseline.

### 2. Smaller component drafts

- Compare sharing invariant definition fields during compilation with the current
  per-draft references. Preserve occurrence, parent, owner, argument and dependency
  relationships independently from definition identity.
- Inventory all writes to nominally shared facts: source-inspection enrichment,
  alias/visibility changes, preference previews and cached-root rebinding. Sharing
  must not let a write to one occurrence change another's callback-visible facts.
- Explore explicit definition replacement or another bounded representation;
  measure the definition pool, temporary keys and transition overlap as well as
  per-draft savings. Do not revive task 04's reverted contextual subtree sharing.
- Keep a clear distinction between an arithmetic shallow ceiling and a measured
  net improvement. If mutation semantics or overhead defeat the proposal, record
  that result rather than forcing a shared representation.

### 3. Graph indexes and provenance storage

- Identify parallel indexes and their actual readers, key density, sparse areas,
  shared referents and lifetimes. Count shared values once; a read-only mapping
  wrapper does not remove its backing dictionary's storage.
- Assess shared provenance with per-occurrence exceptions, consolidated indexes,
  or occurrence-indexed sequences/packed storage where justified. Preserve lookup,
  ordering and iteration behaviour required by compilation and public inspection.
- Account for pruned/gapped occurrence IDs, negative provider-view IDs, separate
  graph namespaces, inherited graphs and overlays. Do not renumber public
  occurrences or merge identities simply to obtain a dense array.
- Preserve exact error origins, boundaries, aliases, budget witnesses and failed
  graph evidence. Include conversion costs, lookup time and any sparse capacity
  retained by an alternative representation in the comparison.

### 4. Cache lookup before step construction

- Compute the existing semantic cache key after dependency/decorator/configuration
  processing, but before allocating a registration step where the path is eligible.
  On a hit, reuse the existing step without constructing a throwaway replacement.
- Preserve all selection, derivation, template and configuration callback counts,
  order and results. This changes allocation placement, not compilation eligibility.
- Keep cleanup descriptors, sync support, type/layer/owner identity, provider-map
  and per-call exclusions, profiler counts and original step-source attribution
  exact. Audit failure order and application-value ownership as well as success.
- Count avoided constructors and allocations separately from cache-owned live
  plans; this proposal does not itself release the cache misses identified in 06.

## Measurement and compatibility

- Capture a fresh baseline at the actual source revision. Initially use the
  unchanged rich eight-route fixture with explanations, diagnostics, future
  overlays and instrumentation disabled; then cover modes touched by each probe.
- Use new `07-*` evidence files and preserve task 06's results/probe versions.
  Record interpreter, platform, source/probe hashes, options and caller ownership.
  Test candidates individually. Any later combination needs its own measurement.
- For candidates taken forward, run at least three fresh normal processes and
  three separately traced processes, serially without competing tests/benchmarks.
  Keep observer/import/setup differences explicit and do not derive RSS savings
  by adding object sizes or subtracting unrelated setup measurements.
- Report creation counts, simultaneous live counts, instance/backing-container
  storage, retained/traced peak memory, current/peak RSS, compilation and resolution
  timings. Extend timing sampling when a short/noisy result cannot settle a tradeoff.
- Preserve full/reduced and diagnostics behaviour, callback-visible Components,
  weak-reference/application-value lifetimes, ownership and cleanup, providers/maps,
  aliases/generics, scopes/overlays, warmup, profiling and truthful failure reports
  wherever touched. Reuse task 06's lifetime counterexamples for affected caches.
- Run focused semantic checks and applicable repository checks for retained
  executable tooling. Check existing artifact round trips if shared representations
  change; expanding precompilation is outside scope. Planning edits need no tests.
- Keep shared production sources unchanged at completion. Preserve reproducible
  isolated patches or process-local probes, with limitations of their installation
  method clearly distinguished from a source-integrated production result.

## Deliverables and acceptance

- [x] An effective-layout inventory identifies dictionary/weakref inheritance and
  measures its relevance by creation/live counts; slots declarations alone are
  not treated as proof of a compact layout.
- [x] Each of the four areas has a source-backed feasibility decision and explicit
  correctness boundary. Rejected or deferred ideas have recorded reasons.
- [x] Promising candidates have repeated, comparable measurements and semantic
  checks; theoretical ceilings and single screens remain labelled as such.
- [x] Compatibility includes observed classes, weak-reference support and supported
  Python versions for any proposed slots change, with unavailable checks recorded.
- [x] A `07-result.md` report ranks candidates, records timing/memory tradeoffs,
  identifies design questions and marks implementation readiness individually.
- [x] The task index records the outcome. No production change is accepted solely
  because an instance is smaller or fewer constructors run.

## Starting points

- `_Step`, registration/provider/collection steps, observed mixins and activation
  template lookup in [container.py](../../clean_ioc/container.py).
- Drafts, shared definitions, records and graph/view storage in
  [components.py](../../clean_ioc/components.py).
- Registration protocol/inheritance in [_legacy.py](../../clean_ioc/_legacy.py)
  and captured facts in [tooling.py](../../clean_ioc/tooling.py).
- [Memory runner](../../benchmarks/graph_memory_evidence.py),
  [rich fixture](../../benchmarks/graph_memory_fixture.py),
  [profiler tests](../../tests/test_resolution_profiler.py),
  [reduced-runtime tests](../../tests/test_optional_explanation_metadata.py) and
  [artifact tests](../../tests/test_graph_artifact_experiment.py).

## Recorded outcome

The [result](07-result.md) and [inventory](07-inventory.md) record five normal
and three traced processes for each candidate. Effective carrier slots reduce
traced peak 1.422 MiB and normal RSS median 1.766 MiB, with overlapping RSS ranges;
scoped implementation/review is recommended, preserving weakrefs. Compact indexes
reduce peak 4.993 MiB and RSS 9.547 MiB but are not ready: eight artifact failures
and mapping-equivalence/iteration/sparsity design remain. Pre-lookup avoids 25,081
constructors without demonstrated memory/speed benefit and is low priority. Draft
sharing remains not ready; its small measured fact pool can extend old opaque-fact
lifetimes and its 6.756 MiB shallow ceiling is not a build saving. Slots/pre-lookup
pass all 2,132 existing tests, lifetime/attribution/fact checks match, and focused
slots tests pass Python 3.11–3.14. Production/test/benchmark sources remain unchanged.
