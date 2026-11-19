# 06 — Investigate avoiding metadata creation during compilation

Created: 2026-10-09\
Status: Complete — investigation; production changes not implemented\
Assignment: GPT-6 Astra (`gpt-6-astra`), high reasoning\
Agent: `/root/graph_memory_task_06`\
Starting revision: `d51b6f5`\
Prerequisites: Tasks 01, 02 and 05 retained; task 03's audit and task 04's rollback

The [result](06-result.md) and [inventory](06-inventory.md) recommend conservative
scalar-only weak cache ownership for a scoped implementation/review: measured
peak 72.844→52.053 MiB and RSS 130.766→106.781 MiB, with observed timing costs.
Plain weak caching is rejected because it changes application-value lifetimes.
Early immutable fact interning is a separate speed proposal, not a peak-memory
win. Production sources remain unchanged; raw evidence and exact probe versions
are listed in the [evidence index](evidence/06-evidence-index.json).

## Outcome and scope

Identify ways to reduce compilation peak memory by avoiding unnecessary metadata
allocations in the first place. Determine which facts must exist while compiling,
which exist only to explain a build, and where metadata can be omitted or created
in a smaller form without changing selection, validation or resolution behaviour.

This is an investigation task. Deliver an allocation/lifetime inventory, measured
evidence and ranked recommendations. Isolated local probes may test a hypothesis
when the investigation is assigned, but this task does not require landing a
production optimization, changing public contracts or implementing precompilation.
Mark any proposed implementation that needs a new behaviour/API decision as not
ready and record the question. The maintainer assigned this investigation to an
Astra agent with high reasoning; production implementation remains outside scope.

Read the [shared plan](README.md) for measurement and compatibility requirements.

## Evidence and working hypotheses

Task 05 made successful-build metadata optional. Its final same-source,
eight-route comparison with diagnostics and future scope builders disabled was:

| Measurement | Full metadata | Reduced metadata |
| --- | ---: | ---: |
| Retained traced Python allocations after build | 38.431 MiB | 3.097 MiB |
| Peak traced Python allocations through build | 73.569 MiB | 72.844 MiB |
| Process RSS after build | 134.156 MiB | 129.453 MiB |

The full graph has 88,558 records and 1,765 distinct execution steps. Reduced
mode retains 8,982 records. Those counts show different representations and
lifetimes; their difference is not proof that all discarded records were
unnecessary during compilation. With diagnostics enabled, the reduced build
retained 3.097 MiB of traced allocations but peaked at 290.055 MiB, with current
RSS of 350.844 MiB. See the [result](05-result.md) and [inventory](05-inventory.md).

Investigate these hypotheses rather than treating them as established savings:

- Reduced mode still constructs some explanation structures, origins and
  contextual metadata before releasing them after successful finalization.
- Contextual cloning can create many metadata occurrences while executable
  steps are shared. Some context is necessary for filters, ownership and errors.
- Template source graphs, drafts, caches, indexes and finalization structures
  may overlap in lifetime and amplify peak live memory.
- Allocator retention/fragmentation may explain part of the small RSS decrease
  after objects are freed. It does not explain which compiler allocations were
  necessary, and must be measured separately from Python object retention.

Task 05 already freezes only the required successful reduced graph; do not
present skipping the final freeze of discarded drafts as a new optimization.
Task 04's subtree-sharing implementation remains reverted.

## Investigation

1. **Establish the current allocation timeline.** Capture a fresh baseline from
   the current runtime, then observe discovery/blueprint preparation, registration
   and decorator template source inspection/expansion, primary compilation,
   final validation, warmup planning, graph freezing/reduction and compiler release.
   Record phase boundaries, live allocations, phase high-water marks and metadata
   counts. Keep a separate unmodified whole-build peak measurement: resetting a
   tracer peak or summing phase peaks does not measure the whole-build peak.
2. **Inventory creation sites and actual readers.** For drafts, contextual clones,
   candidate decisions, explanation objects, origins, relationship indexes,
   template source snapshots, memoization caches and report carriers, record:
   creation site/count; first and last consumer; retaining owner; supported modes;
   and whether the data serves runtime execution, build selection/validation,
   failure diagnostics, full explanations or another optional capability.
   Follow indirect references and failure paths as well as successful readers.
3. **Identify allocations that can be skipped entirely.** Examine capability-aware
   capture, especially decorator evidence when both diagnostics and explanation
   metadata are disabled. Determine the smallest facts required by build rules,
   validation, template checks and warmup planning before gating creation.
   Suppressing a dictionary insertion after constructing the value is not evidence
   that its allocation was avoided.
4. **Investigate smaller necessary build representations.** Assess compact drafts,
   shared invariant facts established earlier than freezing, and minimal contextual
   records that preserve callback-visible Components. Account for occurrence and
   parent identities, negative provider views, generic bindings and cache/cleanup
   owners. Do not infer equivalent contexts from a shared registration or step.
5. **Investigate shorter intermediate lifetimes.** Find the earliest safe release
   point for source inspection graphs, indexes, clone maps and completed expansion
   evidence. Classify these as peak-reduction opportunities separately from
   avoided creation. Establish whether multiple representations are simultaneously
   live at the actual peak; measure any replacement pass's own allocations.
6. **Evaluate diagnostic capture separately.** Determine what can be compacted or
   omitted under each diagnostics/explanation combination while preserving current
   failed-build evidence. Include exceptions during selection, template expansion
   and final validation, aggregated errors, budgets and deferred unreachable checks.
   Never recreate omitted facts by replaying application callbacks or compiling
   the graph again. Record incompatible proposals as design questions.
7. **Test the strongest hypotheses with bounded probes.** Start small to check
   semantics, then use the unchanged eight-route rich fixture for comparisons.
   Isolate one change per probe and retain a patch or source hashes sufficient to
   reproduce it. Rank candidates by measured peak/RSS benefit, work avoided,
   compilation time, compatibility risk and implementation complexity.

## Compatibility boundaries

- Prioritize `explain_metadata=False`, initially with `diagnostics=False` and
  `allow_scope_builders=False`. These flags remain independent. Check other modes
  when a proposal touches their capture paths; do not silently disable capabilities.
- Preserve full-mode inspection and requested failure diagnostics. Reduced-mode
  callbacks must see valid Components while running, and escaped views retain
  task 05's documented behaviour after success. Caller-owned snapshots/builders
  are separate owners, not reclaimable compiler storage.
- Preserve selected registrations, argument values, decorator order, template and
  predicate call counts, aliases/generics, provider/map targets, lifetimes and
  cleanup. No application service activation may be introduced during compilation.
- Keep metadata needed by runtime root filters, `has_component`, context injection,
  providers, warmups, boundaries and enabled overlays/profiling. No deferred
  compilation, whole-graph walk or explanation reconstruction moves into resolution.
- Keep normal compilation as the subject. Existing artifact round-trip checks
  matter if a probe alters shared representations, but extending the artifact API
  or implementing the pre-compilation backlog is outside this investigation.

## Measurement and evidence

- Preserve existing evidence; use new `06-*` files under `evidence/`. Record
  revision/local changes, source hashes, Python/platform, options and ownership.
  Earlier task-05 prototype probes are leads, not current baseline measurements.
- Use at least three serial fresh normal processes and three separate traced
  processes for each candidate taken forward. Keep the fixture/options identical
  within each comparison and run no concurrent tests or benchmarks.
- Report build time, total created metadata counts where measurable, maximum live
  counts, retained allocations after collection, traced peak, current/peak RSS
  and resolution behaviour separately. Count shared referents once. An end-of-build
  heap snapshot cannot count temporary allocations that have already disappeared.
- Keep phase observation separate from normal timing/RSS comparisons. Do not
  retain inspected graphs or snapshot-heavy profiling data inside the measured
  process and mistake the observer's allocations for compiler allocations.
- If inspecting allocator statistics, record the active allocator and distinguish
  allocated objects, unused allocator capacity and other process memory. Treat
  allocator experiments as attribution evidence, not a production allocator change
  or a substitute for preventing unnecessary allocation.
- Check relevant semantic and failure cases for each probe. Run applicable
  repository checks for any retained executable tooling; planning documents alone
  do not require running tests or benchmarks.

## Deliverables and acceptance

- [x] A creation/lifetime inventory identifies actual consumers and mode-specific
  requirements, with source locations and measured counts or explicit unknowns.
- [x] Phase evidence identifies where the current peak occurs and which metadata
  categories are live there; observed facts and hypotheses are distinguished.
- [x] Candidates distinguish avoided construction, smaller representations and
  earlier release. Each states its correctness boundary and supporting evidence.
- [x] Promising probes have repeated comparisons and semantic/failure verification;
  declined probes retain their evidence and reason for rejection.
- [x] A `06-result.md` report ranks recommendations, identifies unresolved decisions
  and says whether each is ready for implementation. A justified conclusion that
  no tested candidate is worthwhile is a valid investigation outcome.
- [x] The task index records the investigation outcome. No production optimization
  is declared complete solely because metadata counts or traced retention decrease.

## Starting points

- `_ComponentDraft`, graph/view storage and freezing in
  [components.py](../../clean_ioc/components.py).
- Compiler capture dictionaries, `_clone_component_tree`,
  `_capture_decorator_pattern`, template source/expansion paths, `_finalize_plan`,
  `_retain_runtime_graph` and `_reduce_explanation_metadata` in
  [container.py](../../clean_ioc/container.py).
- [Explanation and report structures](../../clean_ioc/tooling.py),
  [compilation profiling](../../clean_ioc/compilation_profile.py),
  [memory runner](../../benchmarks/graph_memory_evidence.py),
  [reachability audit](../../benchmarks/graph_reachability_audit.py) and
  [rich fixture](../../benchmarks/graph_memory_fixture.py).
- [Task 03 audit](03-result.md), [task 04 rollback](04-rollback.md),
  [task 05 inventory](05-inventory.md),
  [reduced-runtime tests](../../tests/test_optional_explanation_metadata.py) and
  [fixture tests](../../tests/test_graph_memory_fixture.py).
