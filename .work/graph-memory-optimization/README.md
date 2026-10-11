# Graph memory optimization

The [artifact retest](artifact-retest.md) compares compilation/export and fresh-process
loading after tasks 01 and 02, using the richer fixture. It is a separate local
experiment and does not implement tasks 03 or 04.

The [retest after task 05](artifact-retest-post05.md) compares full and reduced
artifacts using the same current runtime in separate compile/export/load processes.

Created: 2026-10-08\
Status: Tasks 01–24 have recorded outcomes and reviews; task 23 closes task 21's feature integration gate, and task 24 completes the API/tooling/consumer migration with full quality checks. Task 25 is ready for assignment and remains unassigned. No new performance comparison has been run.

## Current direction: execution-only build and complete analyse

The maintainer's follow-up on 2026-10-10 requests two explicit methods:
`build()` emits a runtime with **no validation rules or safety-policy checks**;
`analyse()` performs complete analysis and all validation. Breaking changes are
acceptable. This supersedes the earlier task 10/11 requirement for mandatory
checks in both modes. There is no implicit analysis prerequisite or new set of
fine-grained build switches.

The follow-up decision removes the build-rule/validation-rule distinction:
one `add_validation_rule(rule)` API, no phase argument, and every rule runs only
in `analyse()`. Task 20's scoped implementation is reviewed. The maintainer has
authorized sequential local implementation and verification of tasks 21–24.

The maintainer accepted task 19's reviewed ownership recommendations: an admitted
build/analysis attempt consumes its builder, including failure, and optional
external composition supports overrides without a blueprint on ordinary runtimes.
Composition has immutable declaration structure and ordinary reference ownership,
with no separate close lifecycle. Ordinary scopes require no handle. These are
design decisions; actual reference release and peak-memory savings require measurement.

The [source investigation](build-and-analyse-investigation.md) identifies the
automatic rich capture for build rules, inline validation, report finalization,
and hidden warmup/profiling dependencies on inspection graphs. It also records
the actual Cop regression and the baseline gap in task 18. Compilation must still
bind dependencies and emit instructions; an impossible plan can fail without
performing an architectural or safety audit.

Tasks 19–24 have completed their design/implementation reviews. Task 23 completes
task 21's feature gate. Task 24 passes full library CI on Python 3.11–3.14 and actual
Bark/Cop verification: 6,040 Bark unit tests (29 existing skips), 504 Cop unit tests
and 64 Cop integration tests. [Task 24 result](24-result.md) records source identities,
consumer patches and the 15 retired duplicate host-mode cases. Preserved baselines
remain intact. Task 25 is ready and unassigned; it supplies performance acceptance.
Passing correctness checks does not establish a memory or startup improvement.

Reduce the memory retained by the compiled output graph while preserving
resolution, ownership, filtering, inspection and diagnostic behaviour. Measure
compilation peak memory and build time alongside retained memory. These
tasks follow the investigation using the large graph fixture with registration
templates, decorator templates, providers and maps.

Task 05 adds a different, explicit build mode: `explain_metadata=False` removes
metadata unnecessary for resolution and enabled runtime capabilities. It permits
reduced inspection in that mode, addressing the compatibility constraint that
blocked task 03. GPT-6.1 Sol with high reasoning implemented and verified the option; its
[result](05-result.md) records the capability limits and measured tradeoffs.

Task 06 investigates preventing unnecessary metadata allocation during compilation.
It extends the work from successful-runtime retention to creation costs and
intermediate lifetimes, using task 05's reduced mode as the initial target.

Task 07 investigates object layout and avoidable construction: effective slots
across inheritance, smaller drafts, graph indexes, and cache lookup before step
allocation. It builds on task 06's findings without implementing its proposals.

Task 08 follows up the compact-index probe from task 07, investigating mapping
semantics, artifact compatibility, sparse storage and lookup costs before an
implementation can be recommended.

Task 09 integrates task 08's native dictionary-delegation fixes in an isolated
candidate, selects a small/sparse fallback policy and repeats compatibility and
memory measurements before deciding production readiness.

## Tasks and recommended order

| ID | Task | Status | Starting point |
| --- | --- | --- | --- |
| 01 | [Compact and share decorator-selection facts](01-compact-decorator-selection-facts.md) | Complete | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](01-result.md) |
| 02 | [Separate component definitions from occurrences](02-share-component-definitions.md) | Complete | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](02-result.md) |
| 03 | [Audit and prune discarded compilation records](03-prune-discarded-records.md) | Complete — pruning declined | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](03-result.md) |
| 04 | [Share repeated subtrees through contextual views](04-share-contextual-subtrees.md) | Reverted — dropped | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](04-result.md), [rollback](04-rollback.md) |
| 05 | [Make explanation metadata optional and minimize the runtime container](05-optional-explanation-metadata.md) | Complete — retained | GPT-6.1 Sol (`gpt-6.1-sol`), high reasoning; [result](05-result.md), [inventory](05-inventory.md) |
| 06 | [Investigate avoiding metadata creation during compilation](06-avoid-metadata-creation.md) | Complete — investigation only | GPT-6 Astra (`gpt-6-astra`), high reasoning; [result](06-result.md), [inventory](06-inventory.md) |
| 07 | [Investigate object layout and avoidable allocation](07-object-layout-and-allocation.md) | Complete — investigation only | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](07-result.md), [inventory](07-inventory.md) |
| 08 | [Investigate compact indexes](08-compact-indexes.md) | Complete — investigation only; refine | GPT-6.1 Sol (`gpt-6.1-sol`), high reasoning; [result](08-result.md), [inventory](08-inventory.md) |
| 09 | [Refine compact indexes and verify dictionary compatibility](09-refine-compact-indexes.md) | Complete — isolated prototype retained; not production adopted | GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning; [result](09-result.md), [inventory](09-inventory.md) |
| 10 | [Replace fine-grained build switches with run and analysis modes](10-run-and-analysis-modes.md) | Complete — implemented | High reasoning; [result](10-result.md), [contract](10-contract.md); 2,204 tests and CI pass |
| 11 | [Define validation requirements and minimum failure evidence](11-validation-and-failure-contract.md) | Complete — scoped lifetime/failure changes retained | Extra-high reasoning; [result](11-result.md), [inventory](11-inventory.md); 2,229 tests and CI pass |
| 12 | [Construct compact selection facts directly](12-direct-compact-selection-facts.md) | Complete — scoped CPU/churn improvement retained | High reasoning; [result](12-result.md), [inventory](12-inventory.md); no memory reduction |
| 13 | [Shorten activation-cache ownership](13-activation-cache-lifetimes.md) | Complete — scoped KEEP accepted; [result](13-result.md), [inventory](13-inventory.md) | Extra-high reasoning; 06 cache/lifetime evidence; 10–12 contracts |
| 14 | [Share component definitions in mutable drafts](14-shared-draft-definitions.md) | Complete — scoped KEEP accepted; [result](14-result.md), [inventory](14-inventory.md) | High reasoning; repeated-definition peak gain with explicit unique-definition regression |
| 15 | [Compact temporary indexes and relationship tables](15-compact-compilation-tables.md) | Complete — scoped index KEEP accepted; wider tables DROP / DEFER | High reasoning; [result](15-result.md), [inventory](15-inventory.md); 4.96 MiB lower peak with explicit costs |
| 16 | [Reduce callback snapshot copying](16-callback-snapshot-sharing.md) | Complete — direct-freeze KEEP for CPU/churn; broader sharing DROP; accepted | High reasoning; detached views preserved, traced peaks flat |
| 17 | [Release completed intermediate occurrences earlier](17-intermediate-occurrence-lifetimes.md) | Complete — retained-draft transfer KEEP accepted; broader reclamation DROP / DEFER | 10–11 and consumer/liveness inventory |
| 18 | [Verify both modes and combined compiler-memory gains](18-mode-equivalence-and-memory-acceptance.md) | Complete — combined qualified KEEP accepted; [result](18-result.md) | High reasoning; 10–11 and each optimization selected for integration |
| 19 | [Define explicit build and analyse contracts](19-build-and-analyse-contract.md) | Complete — design reviewed; ownership decisions accepted; [result](19-result.md) | High reasoning; `/root/graph_memory_task_19`; planning only |
| 20 | [Move all validation into analyse](20-analysis-validation-pipeline.md) | Complete — scoped review accepted; [result](20-result.md) | Extra-high reasoning; 262 focused tests, lint/format/types and real Bark rule proof |
| 21 | [Emit execution plans without analysis finalization](21-execution-only-plan-finalization.md) | Complete — core and task 23 feature gate reviewed; [result](21-result.md) | Extra-high reasoning; direct execution result and discovery |
| 22 | [Avoid analysis evidence allocation during build](22-execution-only-evidence-capture.md) | Complete — scoped review accepted; [result](22-result.md) | Extra-high reasoning; 337 focused tests, lint/format/types and real Bark rule proof |
| 23 | [Decouple runtime features from analysis graphs](23-runtime-features-without-analysis-graphs.md) | Complete — scoped review accepted; [result](23-result.md) | High reasoning; 406 focused tests, quality and real Bark rule proof |
| 24 | [Migrate tooling and verify consumers](24-build-analyse-tools-and-consumers.md) | Complete — reviewed; [result](24-result.md) | High reasoning; full CI/docs and actual Bark/Cop verification |
| 25 | [Accept the whole upgrade against consumer baselines](25-build-analyse-consumer-memory-acceptance.md) | Ready — unassigned; baselines preserved; performance not measured | High reasoning; actual application peak/RSS/startup and separate analysis cost |

## Run and analysis workstream — historical direction for tasks 10–18

The new build/analyse direction above supersedes this section's requirement for
mandatory build validation. The following records the earlier work and measured
decisions; it must not be read as a constraint on tasks 19–25.

On 2026-10-10 the maintainer requested exactly two build modes: **run** and
**analysis**, replacing fine-grained build policy options. This is a change to
the intended public API, not a request to add presets alongside permanent
per-feature overrides. The names and direction are agreed; the API spelling,
default, migration and capability decisions are recorded in the implemented
[task 10 contract](10-contract.md).

- Run builds construct and retain the minimum required for correct application
  resolution, discovery, ownership, cleanup and mandatory validation. Reduce
  temporary construction and lifetime as well as successful-runtime retention.
- Analysis builds provide the complete supported inspection, explanation,
  diagnostic and full-validation workflow. They still do not activate application
  constructors or replay callbacks to manufacture evidence.
- Both use the same dependency-selection and execution semantics. Preserve the
  selected-registration catalogue, including selected dependency-only/deferred
  registrations and decorators. Never recreate public roots merely for discovery.
- Mandatory structural checks and build-mode rules remain effective. Registered
  validation-only rules must not prevent a run build. Full validation uses a fresh
  analysis build; discarded capabilities fail clearly on a run runtime.
- Older tasks describe historical fine-grained flags and their compatibility
  contracts. Preserve those records; tasks 10–11 define their explicit successor.
  Task 10 implements these successor modes in the local working tree.

The maintainer subsequently authorized work on tasks 10–18 sequentially, with
one subagent per task using its recorded reasoning effort. Task 10 was accepted
after root review and all local checks passed. Task 11's
[scoped lifetime/failure changes](11-result.md) are also accepted.
Task 12 completed at high effort; root review accepted the scoped
[direct-fact CPU/churn improvement](12-result.md), with its small peak-memory
cost explicit. Task 13 completed at extra-high effort; root review accepted its
[conservative cache ownership change](13-result.md), with ordinary/rich run traced
peaks 28.72%/8.52% lower and build medians 2.96%/1.78% slower. Retention is unchanged,
cold/steady resolution stays close to baseline, and all checks pass. Task 14 was
completed by `/root/graph_memory_task_14` at high effort, with scoped KEEP accepted
after root review. Its [result](14-result.md) records about 6.4 MiB lower traced
peak on the repeated eight-route graph and roughly 1.4% build cost. Its unique-
definition control increases compiler peak by 0.88–1.29 MiB (4.06–6.31%),
measured separately with matched compiler-only tracing.
Task 15 completed at high effort; root review accepted its [result](15-result.md): scoped
index KEEP with about 4.96 MiB lower large compiler peak and 3.2–3.4% build cost.
Wider relationship tables are independently dropped/deferred. Cold/steady resolution
timing was carried into task 18 despite zero index lookups during resolution;
full experimental artifact loading costs about 8% more. CI passes 2,386 tests,
strict docs and 263 focused tests on each supported Python 3.11–3.13.
Task 16 completed at high effort; its [result](16-result.md) recommends direct
draft-snapshot freezing for CPU/churn only, accepted after root review. It avoids
91,816 record constructors with unchanged peak-live/retained counts and flat traced
peak; build medians improve 5–7%. Rich-run resolution +2.01% was carried into task 18 as a
signal. CI passes 2,401 tests, strict docs and focused checks on 3.11–3.13.
Task 17 completed at extra-high reasoning; root review accepted its [retained-draft transfer](17-result.md), reducing ordinary-run traced peak by 1.40 MiB (3.43%) without claiming a build-time or retained-memory gain. Broader streaming reclamation is dropped/deferred. All 2,407 tests, supported-Python focused checks and strict docs pass. Task 18 completed at high reasoning; its [combined result](18-result.md) received qualified KEEP
after coordinating review. Against accepted10/11, ordinary-run build changes 10.992→5.764 seconds and traced peak
72.848→39.416 MiB; rich-rule peak falls 290.183→254.089 MiB with a 1.53% build-time cost. Retention is nearly flat.
Low-reuse build/peak regressions and bounded analysis/post-collection resolution costs are explicitly retained
as tradeoffs. All 2,409 tests, strict docs and expanded supported-Python focused checks pass. Runtime source is
unchanged from task17; downstream Bark/Cop, Docker and production verification were not run.
The coordinating agent reviews each outcome and carries decisions into the next
task. Resolve design gates during the work rather than treating the earlier
planning-only status as a standing prohibition. Preserve safety and explicit
evidence requirements; an optimization may still conclude with refine or drop.
This execution request does not include a commit, version bump, push or release.
Parked pre-compilation work remains parked; check existing artifact experiments
only where a representation or API change affects them.

### Recommended reasoning effort

These recommendations apply when each new task is assigned; they do not select
a model, assign an agent or change the task's readiness gate.

| Task | Effort | Reason |
| --- | --- | --- |
| 10 — Run and analysis modes | High (`high`) | Public capability, default and migration decisions across tooling and overlays |
| 11 — Validation and failure contract | Extra high (`xhigh`) | Safety-critical evidence requirements and compatibility with arbitrary callbacks |
| 12 — Direct compact selection facts | High (`high`) | Preserve contextual facts and failure semantics while removing allocations |
| 13 — Activation-cache lifetimes | Extra high (`xhigh`) | Subtle observable ownership, weak-reference and derived-value lifetime hazards |
| 14 — Shared draft definitions | High (`high`) | Copy-on-write correctness across mutations, identity and pool lifetimes |
| 15 — Compact compilation tables | High (`high`) | Mapping compatibility, sparse storage and representation tradeoffs |
| 16 — Callback snapshot sharing | High (`high`) | Stable escaped views and bounded sharing without retained-history chains |
| 17 — Intermediate-occurrence lifetimes | Extra high (`xhigh`) | Architectural last-consumer reasoning across graph-wide validation and callbacks |
| 18 — Mode equivalence and memory acceptance | High (`high`) | Cross-feature equivalence, reliable measurement and combined regression assessment |

### Baseline and evidence boundaries

Start from the current checkout, not an archived probe installed as production.
At planning time HEAD is `34d1ea0` (2.0.0rc4), with an uncommitted fix accepting
validation-only rule registrations in reduced builds. RC4 already preserves
`selected_registrations`; the local validation fix has passed 2,163 tests and
repository checks. Record the exact revision and working changes again when work
starts, and preserve this unrelated consumer fix.

The recent eight-route object census, with diagnostics and scope builders off,
has 88,558 full versus 8,982 reduced records, 1,765 retained execution steps and
51 discovery entries in either mode. Across either build it constructs about
90,250 drafts, 1.13 million candidate decisions and 1.13 million template facts;
the primary activation cache has about 31,025 entries. These are object counts,
not new RSS/timing measurements. Tasks 06–09 contain historical measured probes,
including failed approaches; none establishes combined savings or adoption.

### Sequence

1. Define the public mode/capability and migration contract in 10; audit validation
   and evidence consumers in 11. Capture a fresh baseline using 18's protocol.
2. Investigate 12–16 separately. Cache ownership (13) and draft representation
   (14) target live peak; direct facts (12) primarily target allocation churn.
   Task 15 starts from the corrected index work rather than repeating task 08.
3. Proceed with 17 only after lifetime and graph-wide validation obligations are
   explicit. It is a deeper architectural change, not automatic pruning.
4. Integrate only accepted candidates and finish 18 against the combined source.
   Standalone improvements are not additive estimates of the combined result.

Tasks 01–08 have recorded outcomes. Task 06 was completed by Astra with high
reasoning on 2026-10-09; production optimization remains unimplemented. Task 07
was completed by GPT-6.1 Sol with medium reasoning on 2026-10-09; its proposals
remain unimplemented. Task 08 was completed by GPT-6.1 Sol with high reasoning on 2026-10-09;
its then-measured index remained not ready pending native-delegation integration
and remeasurement. Task 09 was completed by GPT-6.1 Sol with medium reasoning: integrated native
delegation, bounded small/sparse fallback and final measurements address those
blockers. Its isolated prototype is retained for implementation review; production
adoption is not approved. Reassess recommendations against
the measured compiler.
A task may conclude that a proposed optimization is unsafe
or not worthwhile; record that outcome and its evidence instead of forcing an
implementation.

## Current evidence

The [fixture report](../../docs/graph-memory-fixture.md) and
[raw results](../../benchmarks/graph_memory_results.json) describe the eight-route
baseline on Python 3.14.4, macOS ARM64. Three normal and three separately traced
processes produced:

| Measurement | Baseline |
| --- | ---: |
| Median fixture import, composition and build | 7.630 s |
| Median process RSS after build | 276.2 MiB |
| Median retained traced Python allocations after build | 187.2 MiB |
| Median traced Python allocation peak through build | 222.7 MiB |
| Physical graph records | 88,558 |
| Distinct execution steps | 1,765 |
| Decorator-explanation entries, diagnostics disabled | 56,522 |
| Component-record objects, shallow storage | 21.6 MiB |
| Record index / origin index, shallow storage | 5.0 MiB / 5.0 MiB |

A subsequent one-process inspection counted 565,220 unique decorator decisions
and 565,220 unique template-fact objects. Only 792 decisions were selected;
564,372 recorded `template-target-not-selected`. Explanations, decisions,
template facts and their selected/rejected tuples occupied 139.7 MiB of combined
shallow storage. This additional census is not yet included in the raw result
file; task 01 must make it reproducible before relying on it for comparisons.
Shallow storage is not total process memory or a promise of recoverable savings.

An initial 32-route run exceeded 4 GiB RSS before completion and was stopped.
Use eight routes for the initial comparisons and increase scale deliberately.
The baseline is synthetic and does not establish production memory use.

## Shared implementation and measurement rules

For tasks 20–24, the maintainer's latest direction overrides per-task measurement
requirements below: continue implementation and correctness/quality verification,
preserve source identities and existing evidence, and defer further memory/timing
benchmarks and performance population studies to final task 25. Individual task
completion must state that performance acceptance remains pending.

- Preserve the original baseline; write each task's before/after results to new
  files. Record the source revision and any local changes, fixture, interpreter,
  architecture, build options and measurement method.
- Keep the workload fixed within a comparison. Use at least three fresh normal
  processes and three separate traced processes. Run measurements without
  concurrent test or benchmark workloads.
- Report retained Python allocations after collection, allocation peak, current
  and peak RSS, build time, resolution time, and physical versus logical graph
  counts separately. Attribute shared objects once and avoid additive savings
  claims across overlapping representations.
- Preserve registration and occurrence identities, parent context, generic
  bindings, selection order, lifetime/cache/cleanup ownership, and observed
  resolution attribution. Sharing metadata must not share transient instances.
- Preserve public component traversal, explanations, manifests, fingerprints
  and reports. Construct optional inspection views from captured immutable facts;
  never rerun application constructors, template factories or selection callbacks
  to recover omitted evidence.
  Task 05 explicitly relaxes inspection compatibility when `explain_metadata=False`;
  its documented capability boundary applies in that mode. Preserve resolution
  and full-mode inspection, and never reconstruct omitted facts by callback replay.
- Check diagnostics on and off, ordinary and managed providers, maps, scope
  builders/overlays, boundaries and profiling where the change touches them.
  The richer fixture does not cover every library feature by itself.
- Keep ordinary resolution free of new whole-graph traversal or compilation
  work. Measure the cost of inspecting a graph separately if allocation becomes
  lazy, including whether repeated inspection retains new caches.
- For each implementation, run relevant behavioural tests and the repository's
  required checks. Record failures and existing limitations accurately. Mark
  completion only after the acceptance criteria and measurements are recorded.

Example baseline capture for task 01:

```sh
.venv/bin/python -m benchmarks.graph_memory_evidence repeat --routes 8 --repeats 3 --output .work/graph-memory-optimization/evidence/01-before.json
```

The [fixture](../../benchmarks/graph_memory_fixture.py),
[measurement runner](../../benchmarks/graph_memory_evidence.py) and
[integration tests](../../tests/test_graph_memory_fixture.py) are the starting
tools. The [artifact-loading experiment](../../docs/graph-artifact-experiment.md)
remains unfinished and may be dropped; these tasks concern the normal compiler
and runtime graph.

## Task 01 result

[Recorded implementation and evidence](01-result.md): diagnostics-disabled
decorator facts now share captured patterns, with per-occurrence target identities.
Eight-route retained traced allocations decrease from 187.2 to 45.2 MiB; build
time increases from 7.777 to 11.511 seconds. Diagnostic history remains eager.
All 2,055 tests and required checks pass; strict MkDocs retains eight existing
links-to-files-outside-docs warnings. Later task results are recorded below.

## Task 02 result

[Recorded implementation and evidence](02-result.md): frozen occurrences share
eleven captured metadata fields through 116 definitions. Eight-route retained
traced allocations decrease from 45.17 to 38.43 MiB and build allocation peak
from 80.22 to 73.58 MiB. RSS remains effectively unchanged (131.55→132.59 MiB).
Public manifest fingerprints and graph counts match; all 2,070 tests and required
checks pass, with the same existing strict-MkDocs link warnings. Compilation and
inspection observations and limitations are recorded separately. Task 03 is
recorded below; task 04 is recorded below.

## Task 03 result

[Recorded audit and declined experiment](03-result.md): 8,932 records are in
public relationship closure, 50 additional records support runtime/provider roots,
and 79,576 additional records are held by explanation-owner closures. No record
is outside every conservatively protected root. A forwarding selection callback
captures views requiring 600 records outside runtime-root closure at two routes;
the compiler has no escape inventory. Production pruning is therefore declined,
with zero production memory benefit or added runtime/build/inspection cost.
Twelve fresh comparison processes retain 38.43 MiB allocations and 73.58 MiB build
allocation peak with identical production-source hashes and behavior. All 2,079
tests and required checks pass, apart from the same eight existing strict-MkDocs
link warnings. The offline audit costs 0.762 seconds and a separately observed
77.09 MiB temporary allocation peak; it is not integrated into compilation.
Task 04 is recorded below.

## Task 04 result — reverted

The maintainer requested undoing task 04 on 2026-10-09. Its [recorded experiment](04-result.md)
saved 2.66 MiB of retained Python allocations, but process RSS rose about 3.3 MiB
(2.5%), allocation peak increased slightly and graph inspection slowed. This did
not demonstrate a process-memory benefit, so the original KEEP recommendation
was superseded.

The [rollback](04-rollback.md) restores the exact pre-task-04 runtime, memory
runner and schema-5 artifact codec. Tasks 01 and 02, task 03's offline audit and
the richer artifact experiment remain. Task 04's raw measurements are unchanged;
its implementation, tests and probes are archived as inert text for reference.

## Task 05 result — retained

[Recorded implementation and evidence](05-result.md): both builders accept
`explain_metadata=True` by default. Opting out releases explanation/inspection
metadata and 79,576 of 88,558 records while preserving runtime relationships.
Final same-source eight-route Python retention falls 38.43→3.10 MiB, RSS
134.16→129.45 MiB, and allocation peak 73.57→72.84 MiB. Diagnostics-enabled
builds retain the same reduced Python total but still use about 350.84 MiB RSS;
their build allocation peak rises about 3.20 MiB. Future overlays cost about
0.18 MiB; caller-retained snapshots are measured separately. All 2,127 tests,
222 reused reduced-mode execution checks and required CI checks pass, except
strict MkDocs' same eight existing external-file link warnings. Inspection limits,
escaped views, scope modes, ownership and failure evidence are documented.


Task 06's [investigation](06-result.md) locates reduced-mode peak in primary
compilation. Conservative scalar-only weak cache ownership is recommended for a
scoped implementation/review: repeated peak 72.844→52.053 MiB and normal RSS
130.766→106.781 MiB, with unchanged ~3.10 MiB Python retention and graph/activation
counts. Build median rises 7.1%; the three short resolution samples rise 2.410 ms
at the median, so timing needs follow-up before acceptance. Strong fallback
preserves opaque values, map keys and unknown carriers: broad weak caching fails
16 lifetime cases despite passing all 2,132 existing tests. The conservative probe
passes both. Early fact interning avoids 1,695,090 named metadata constructor calls
and lowers build median 40.6%, but has no demonstrated peak-memory benefit.
Smaller drafts and diagnostic history remain unmeasured design opportunities;
coarse fact omission is incompatible. All changes are evidence/tooling, with no
production optimization, commit, or pre-compilation implementation.


## Task 07 result — investigation only

The [result](07-result.md) records source/MRO inventory, independent probes and
five normal/three traced processes per candidate. Effective slots retain weakrefs,
lower traced peak 72.844→71.422 MiB and normal RSS median 130.578→128.812 MiB
(with overlapping RSS ranges), and are ready for scoped implementation/review.
Compact indexes lower peak to 67.851 MiB and RSS to 121.031 MiB, but fail eight
full-artifact cases and need mapping/codec/sparsity design; not ready. Pre-lookup
avoids 25,081 constructors but establishes no peak/RSS/speed benefit. Early draft
sharing remains a bounded feasibility result with unresolved mutation/pool-lifetime
semantics, not an achieved saving. Slots/pre-lookup pass all 2,132 existing tests;
full/reduced attribution/facts and 16 lifetime cases match, and slots checks pass
Python 3.11–3.14. No production/test/benchmark source, commit, push or pre-compilation
implementation is changed.


## Task 08 result — investigation only; refine

The [result](08-result.md) and [inventory](08-inventory.md) record bounded compact
indexes and a direct experimental codec. Reduced peak/RSS decrease
72.844→67.851 MiB / 130.438→119.734 MiB with no established build-time change;
full retention decreases 38.432→33.523 MiB. All eight prior artifact failures are
resolved, all 2,132 tests and focused Python 3.11–3.13 checks pass, and provenance,
callback and lifetime evidence matches. Six stronger custom-hash counterexamples
still fail the measured mapping, including read-only proxy equality. A separate native-
delegation feasibility subclass resolves those cases but is unintegrated/unmeasured.
Sparse-only shallow storage rises 15.3%; full artifact load median rises 8.0% while
load peak/RSS decrease. **REFINE; not ready for implementation** until the complete
adapter and fallback policy are integrated, checked and remeasured. Production,
Task 06 caches, Task 07 layouts and pre-compilation work remain unchanged.

## Task 09 result

[Corrected prototype and final evidence](09-result.md): all six custom-hash
counterexamples, 103 operation/codec-state checks, 2,132 tests and 16 lifetime
cases pass. Focused Python 3.11–3.13 checks pass. The 104-process same-source
matrix shows reduced traced peak 72.844→67.887 MiB and full retained Python
38.431→33.474 MiB; current RSS falls about 9.6–9.7 MiB during compilation.
A bounded fallback keeps sparse/tiny storage at native dictionary plus 72 bytes.
Full artifact load retains 38.060→33.103 MiB and peaks 66.535→60.619 MiB, but
full export/load medians rise ~13% and narrow dense lookup remains ~3× native.
RETAIN the isolated prototype for implementation review; production adoption is
not approved. Production sources and prior evidence are unchanged. Raw repository
lint retains one prior Task 08 E501; a narrowly exempted rerun and other checks pass.
