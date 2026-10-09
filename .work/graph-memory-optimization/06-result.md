# Task 06 — avoiding compiler metadata creation

Investigation complete, 2026-10-09. No production optimization, precompilation implementation,
commit or push is part of this task. The source baseline is
`d51b6f569e67891e72e022b35aa5590c1c0fda46`.

The [creation and reader inventory](06-inventory.md) records the contracts that
bound this investigation. The strongest findings are that the successful
reduced build's peak occurs in **primary compilation**, that strongly owned
activation-template cache entries survive until compiler release, and that
compact decorator capture still constructs over a million short-lived facts.

Recommend a scoped implementation/review of **conservative scalar-only weak
activation-cache ownership**: the repeated probe lowers traced peak 28.5% and
normal RSS 18.3%, while retaining strong ownership for opaque application values.
It has measured timing tradeoffs and requires the explicit fallback boundary
below. Broad weak caching is rejected. Early immutable fact interning is a
separate build-speed recommendation, with no established peak-memory benefit.

## Baseline and phase attribution

`evidence/06-baseline.json` contains three serial normal processes and three
separate traced processes using the unchanged production runner. Eight routes;
`diagnostics=False`, `explain_metadata=False`, `allow_scope_builders=False`;
Python 3.14.4, macOS ARM64, existing `.venv`; no caller-retained builder or callback
views. The fixture also uses `check_unreachable=False`, `aggregate_errors=False`
and four explicit roots (`Provider[Worker]`, async, managed and async-managed
provider forms). There are no warmup declarations or custom validation rules in
this measured build. Build timing includes fixture import, composition and compilation.

| Unmodified baseline median | Value |
| --- | ---: |
| Build | 11.150 s |
| Resolution workload | 14.881 ms |
| Retained Python allocations after build and collection | 3.097 MiB |
| Traced allocation peak through build | 72.843 MiB |
| Current process RSS after build | 129.406 MiB |
| Peak process RSS through build | 129.406 MiB |
| Final physical component records | 8,982 |
| Distinct execution steps | 1,765 |

The separate phase observer (`evidence/06-timeline.json`) records **live traced
allocations** and the high-water mark since the preceding observation. It resets
only its own segment peak. Segment peaks are never summed, nor substituted for
the unmodified whole-build measurement. It retains only scalar evidence and weak
compiler references; no graph/snapshot is kept in its output. Its event/index
bookkeeping adds about 0.09 MiB near the observed peak. Constructor/live census
runs have additional overhead and are separate again.

| Phase boundary | Live MiB | Relevant preceding segment peak, MiB |
| --- | ---: | ---: |
| Fixture imported | 0.105 | 0.200 |
| Discovery/blueprint snapshot completed | 0.251 | 0.253 |
| Registration template expansion completed | 0.525 | 0.604 |
| Decorator template expansion completed | 1.062 | 1.117 |
| Primary compilation begins | 1.117 | 1.117 |
| Primary compilation returns | 71.445 | **72.930** |
| Final validation returns | 71.459 | 71.462 |
| Warmup planning returns (no declarations in fixture) | 71.476 | 71.478 |
| Orphan pruning returns | 71.495 | 71.536 |
| Compiler/report wrapper returns | 45.999 | 71.506 |
| Runtime-closure freeze begins | 49.859 | 50.085 |
| Runtime-closure freeze ends | 51.393 | 51.783 |
| First runtime graph retention returns | 17.904 | 51.393 |
| Final metadata reduction returns | 17.263 | 18.104 |
| Public build returns, before explicit collection | 4.163 | 17.265 |
| After explicit collection | 3.167 | 4.164 |

At primary completion, 88,558 drafts, 56,522 remapped decorator sidecars, the
88,558-entry origin map, the 31,025-entry activation-template cache, and 26
source graphs with 1,692 records are simultaneously live. Only 43 compact
explanation patterns / 430 template facts remain, despite their enormous
cumulative constructor counts. Primary compilation makes **zero**
`_clone_component_tree` calls in this fixture; all 1,352 observed clone calls are
in source inspections. Repeated contextual compilation is the current draft
multiplier. This does not generalize to every composition.

The compiler/report wrapper's return releases roughly 25.5 MiB before runtime
reduction. That is an ownership/lifetime observation, not attribution of every
byte to one cache. Its locals, compiler indexes and discarded executable plans
all overlap. The weak-cache probe tests the cache contribution independently.
The largest observed snapshot high-water mark was below the overall primary
peak; source graphs and freezing are not the dominant peak in this workload.
The exact individual allocation at the high-water mark is not sampled.

## Repeated candidate measurements

The three-plus-three comparisons use the **same process-local harness** for the
baseline and each candidate. Its additional imported modules raise absolute
normal RSS relative to the original runner by about 1.36 MiB; their traced build
peak agrees within 0.001 MiB. Candidate RSS comparisons therefore use the harness
baseline, not the slightly smaller original-runner RSS.

| Median, eight routes | Harness baseline | Scalar-only weak cache | Plain weak cache (rejected) | Early fact interning |
| --- | ---: | ---: | ---: | ---: |
| Build, seconds | 11.344 | 12.149 | 11.708 | 6.739 |
| Resolve workload, milliseconds | 14.849 | 17.260 | 14.423 | 14.955 |
| Retained Python, MiB | 3.098 | 3.097 | 3.097 | 3.097 |
| Traced build peak, MiB | 72.844 | 52.053 | 52.053 | 73.056 |
| Current RSS after build, MiB | 130.766 | 106.781 | 104.531 | 133.453¹ |
| Peak RSS through build, MiB | 130.766 | 106.781 | 104.531 | 133.453¹ |
| Physical records / execution steps | 8,982 / 1,765 | 8,982 / 1,765 | 8,982 / 1,765 | 8,982 / 1,765 |

The conservative cache lowers traced peak by **20.791 MiB (28.5%)** and normal
current/peak RSS by **23.984 MiB (18.3%)**. Retained runtime Python memory stays
about 3.10 MiB. This is earlier release of intermediate executable carriers,
not avoided construction, reduced graph records, or a runtime ownership change.

Its build median is **7.1% higher**; ranges overlap (baseline 11.328–11.683 s;
conservative cache 11.219–12.260 s). The three short resolution samples are
14.301, 17.260 and 17.507 ms, versus 14.684, 14.849 and 15.068 ms at baseline:
**+2.410 ms / +16.2%** at the median. This observed cost must not be hidden as
noise or converted into a precise general throughput claim. The candidate adds
no resolution traversal or callback, but source-integrated implementation should
check broader timing before acceptance. Normal RSS ranges are 128.188–133.234
MiB at baseline and 104.750–108.250 MiB with the conservative cache.

Every one of the six runs per candidate matches baseline runtime census,
validation, template calls, activations, lazy activation counts and retained graph
inventory. The plain weak-cache figures remain as rejected evidence: its lower
RSS does not justify changing application-value lifetimes. None of these results
claims benefits for combining candidates.

¹ Early fact interning uses AST recompilation to install its process-local
function changes. It begins at 46.156 MiB RSS, versus 43.156 MiB for baseline;
plain weak-cache setup begins at 43.328 MiB and conservative cache setup at
43.563 MiB. The fact probe's final +2.69 MiB RSS
therefore **cannot be attributed as a production regression**. Subtracting setup
RSS is not a valid allocator correction either. Its traced build peak, measured
only after installation, still rises 0.212 MiB: this is not an established peak
memory optimization. The 40.6% build-time reduction is a separately reviewable
speed tradeoff. A source-integrated implementation would need fresh RSS results.

The named constructor census establishes actual avoided construction: template
facts fall from 1,130,440 to **570**, and candidate decisions from 1,130,498 to
**565,278**. Other observed constructor counts are unchanged. This avoids
1,695,090 calls to those two metadata constructors; it is not a count of *all*
Python allocations, because lookup tuples/identity integers are also created.
The interning pool retains 570 entries until compiler release versus 430 template
facts in baseline patterns, explaining why less cumulative work need not mean a
smaller live peak. No skipped callbacks or lost decision fields produce this gain.

## Bounded screens (not repeated benefit claims)

These use one normal and one separate traced eight-route process per candidate,
after successful small semantic screens. They are declined or deferred rather
than promoted on one favorable number. All retain the same 3.10 MiB runtime Python
allocations and the fixture's execution behavior. Startup RSS differs by probe
installation, particularly for AST-based changes; no RSS delta here is a
source-integrated production estimate.

| Single screen | Build s | Traced peak MiB | Current / peak normal RSS MiB | Decision |
| --- | ---: | ---: | ---: | --- |
| Snapshot record reuse | 11.106 | 72.843 | 131.547 / 131.547 | Avoids redundant construction; no peak benefit established. Low priority. |
| Snapshot definition interning | 11.784 | 74.593 | 130.719 / 130.719 | Peak increased in this screen; do not promote as a memory optimization. |
| Release source graph ownership | 11.469 | 72.390 | 129.938 / 129.938 | About 0.45 MiB lower traced peak; low priority, not repeatedly verified. |
| Omit decorator evidence | 5.000 | 68.682 | 126.391 / 126.391 | Rejected for lost build-rule and failed-build evidence. |

Snapshot definition interning's extra temporary memo/keys and allocation schedule
need their own attribution before any renewed attempt; fewer definitions alone
are insufficient evidence. Source graph release needs an explicit internal scalar
carrier instead of the probe's `None` placeholder, preserving full expansion views.
Neither candidate meets the bar for a claimed production memory improvement here.

## Probe boundaries

All probes install changes inside a fresh Python process using
`evidence/06-probe.py`. Production files stay unchanged. Single hypotheses are
isolated; results must not be added together as combined savings.

- **Intern normalized template facts at capture:** keep actual selectors,
  callbacks, ordering and all explanation outcomes, but capture immutable,
  reference-identical template facts once with target occurrence represented by
  the existing remapping wrapper. Avoid constructing an occurrence fact followed
  by its normalized duplicate. Diagnostics-on retains the current eager path.
  The probe's temporary target field and eager-reference routing are experiment
  scaffolding; a production patch should make the capture interface explicit.
- **Plain weak activation-template values (rejected):** keep memo keys and
  compilation/selection work, but let templates die when no plan/candidate/adapter
  owns them. This saves memory, but also releases opaque application values early;
  the counterexample below changes a later resolved argument. It is not ready.
- **Conservative scalar-only weak values:** retain the original strong cache for
  any subtree containing an opaque argument value, map/provider/collection step,
  decorator, pre-configuration, or unrecognized step form. Only exact library
  registration steps with no decorators/configurations and recursively safe
  dependencies can use weak ownership. Value leaves must be exact `NoneType`,
  `bool`, `int`, `float`, `complex`, `str`, or `bytes`; subclasses and containers
  fall back to strong ownership. Inspect only library carriers, never arbitrary
  application values. This is shorter lifetime, not avoided construction or
  instance sharing. All graph drafts, definition inputs and origin evidence
  remain strongly owned through their existing build consumers.
- **Snapshot definition interning:** pass a snapshot-local definition memo to
  draft freezing. Every occurrence and snapshot remains distinct. It reduces
  repeated definition objects; the temporary memo also allocates keys.
- **Snapshot record reuse:** skip `replace(record, decorator_ids=())` only when
  the immutable record already has no decorators. Primary drafts are still
  frozen into detached records. This avoids redundant construction, not an
  entire snapshot or graph walk.
- **Release source graph ownership:** reduced-mode selection carriers retain
  scalar source facts but stop owning completed source Components. Callback-held
  source snapshots remain valid; full-mode expansion results keep their current
  Components. This is earlier release, not skipped source inspection.
- **No decorator evidence:** a deliberately incompatible ceiling probe skips
  decision construction when diagnostics and successful explanations are off.
  It is rejected: build rules can inspect these facts, and failed-finalization
  graphs retain an explanation contract. There is no callback replay fallback.

## The ownership counterexample and conservative refinement

The plain weak cache passed all 2,132 existing tests and matched full manifests,
complete decorator facts and execution attribution in the rich fixture. A new
small counterexample nevertheless disproves broad compatibility:

1. A dependency-only candidate derives a `Payload` and saves only a weak reference
   outside the compiler.
2. Its `when` callback rejects it, so it is absent from the selected collection.
3. A later derive callback asks whether that weak reference is still alive, then
   supplies the resulting boolean as an actual runtime argument.

Baseline returns **True**; plain weak cache returns **False**. Both invoke exactly
`derive payload`, `reject candidate`, `observe payload`, once each, in that order.
No constructor activation or callback replay explains the difference: the cache
was the last owner of the rejected `_ValueStep.value`. Evidence and executable
reproduction are in `06-payload-*.json` and `06-payload-lifetime.py`.

This is why a compiler cache cannot automatically be classified as metadata-only.
Provider-map key callbacks can similarly produce opaque keys; unknown execution
carriers can contain other application state. The conservative refinement uses
strong ownership for all such paths instead of trying to inspect or reconstruct
those values. It preserves **True** in the counterexample and passes all 2,132
existing tests. The generalized `06-value-kinds.py` checks an opaque object, a
string subclass, a container holding an opaque value, and a provider-map key
across all four diagnostics/explanation combinations. Baseline and conservative
cache return **True in all 16 cases**, with identical callbacks and argument
results; the plain weak cache returns **False in all 16**. Exact scalar types are
intentional: replacing the guard with `isinstance` would admit the failing string
subclass. Unknown carriers conservatively keep strong ownership.

The cache-only census (`06-cache-strong.json`, `06-cache-weak.json`) observes the
plain weak candidate's mechanism independently of timing: primary compilation
has 31,025 insertions and 25,081 hits in both modes. Strong ownership keeps all
31,025 entries; weak ownership peaks at 635 live entries and ends with 617.
The 88,558 graph drafts remain unchanged. This supports shorter intermediate
lifetime as the memory source, not skipped compilation. It does not override the
plain weak candidate's semantic rejection.

## Semantic evidence and known limitations

The targeted probe suites each passed 396 tests (except the deliberately
incompatible omission probe). These covered reduced/full
modes, diagnostics, template expansion/selection/position callbacks and escaped
snapshots, exact source binding, generic targets, ordinary/managed providers,
maps, overlay owners, boundaries, warmups, profiling, budgets, aggregation and
failed final validation. The rich fixture checks activation/laziness, callback
counts, scopes, exact dependencies and cleanup.

The conservative cache, plain weak cache and fact-interning probes each also
passed the complete **2,132-test** suite. The suite alone did not detect the
plain-cache lifetime regression.

The final eight-route reduced execution-source census (plus two-route full
manifest and complete decorator-fact comparisons) compares step class, primary
occurrence ID and multiplicity, not just totals. Each of those three probes matched the baseline.
`06-semantics-*.json` also demonstrates that the compatible probes retain a
selected decorator fact on a failed reduced, diagnostics-off finalization.
The omission probe instead reports `explain-decorators-not-recorded` and fails
`test_build_rules_run_before_reduction_and_saved_graphs_expire[False]` (47 other
reduced-mode tests pass). That failure is a reason to reject the optimization,
not a test to remove.

Two initial capture-probe test failures were harness defects: copied function
globals bypassed a monkeypatched snapshot observer, and an eager-reference
capture seam received normalized target IDs. The final process-local harness
uses the live module globals and routes the explicitly monkeypatched eager
reference through its original function. The corrected capture run passes all
396 tests. Original failures and the old probe source are preserved for audit.
The first small-screen harness also inverted its `--full` flag: those five
outputs explicitly report full metadata, are renamed `06-small-initial-full-*`,
and are excluded from reduced comparisons. Corrected reduced screens are separate.

This is a synthetic eight-route fixture, not production capacity evidence.
It has no warmup declarations or custom validation rules in its measured build;
those behaviors are tested separately. No proposal assumes callbacks are pure,
replays them to recover evidence, changes deferred unreachable checks, or uses
Task 04's reverted subtree views. Python allocation retention, transient peak,
RSS, allocator capacity, construction counts and timing remain separate metrics.

## Diagnostic capture and allocator attribution

The fresh diagnostics-on reduced phase run (`06-timeline-diagnostics.json`)
peaks in primary compilation too: 288.741 MiB segment high-water, with 287.515 MiB
live at primary return. At that boundary it holds 117,168 diagnostic history
entries, 61,790 occurrence explanations, 44,362 parameter-explanation owners and
56,522 decorator sidecars; generic explanations are empty for this fixture.
Compiler release brings live traced allocations to 258.600 MiB. Metadata reduction
still temporarily leaves about 231.613 MiB while callers unwind, and final
collection leaves 3.168 MiB including observer bookkeeping. These are phase
observations, not a new three-process diagnostic whole-build benchmark.

The safe capture requirements differ by capability:

| Mode | Required during build / failure | Permissible direction |
| --- | --- | --- |
| Diagnostics off, full explanations | Full decorator facts for ordinary inspection and build rules | Share immutable fact content; retain every outcome and occurrence mapping. |
| Diagnostics off, reduced explanations | Build-rule inspection and failed-finalization graph still work | Same facts may need to exist until success is known; coarse omission is incompatible. |
| Diagnostics on, full explanations | Occurrence/parameter/generic histories, census, partial attempts and full graph | Compact captured facts only if per-attempt order, identity, incomplete states and public values remain exact. |
| Diagnostics on, reduced explanations | Same requested failure evidence; successful evidence is released later | A late successful release does not remove diagnostic build peak. Do not disable diagnostics implicitly. |

A diagnostic-history compaction proposal remains **not ready**. Existing history
readers include budget-failure conversion (`container.py:610`), partial attempts
(`5509`, `5780`), error/report carriers (`422–449`, `12674`, `12746`) and failed
selection census (`selection_census.py:666`). They rely on eager captured evidence,
including attempt identity and not-examined states. Adapting them to compact
immutable facts is plausible; dropping history or replaying callbacks is not.
Aggregation already has its documented root retries; an optimizer must not add
replay to rebuild omitted evidence. Deferred unreachable checks and warmup
fingerprints retain their current semantics.

The separate untraced allocator run uses the default allocator, with
`PYTHONMALLOC` unset, `WITH_PYMALLOC=1`, GIL enabled, and `sys._debugmallocstats`
confirming 512-byte small-block classes and 1 MiB arenas. No allocator setting is
changed. It includes all process small-block allocations, including imports that
precede the benchmark's tracer, so it must not be equated with traced retention.

| Default allocator observation | Before build | After build + GC | After releasing runtime + GC |
| --- | ---: | ---: | ---: |
| Current small-object arenas, MiB | 16 | 76 | 49 |
| Allocated small-object blocks, MiB | 15.098 | 17.829 | 15.162 |
| Available blocks within pools, MiB | 0.261 | 20.896 | 1.799 |
| Unused pools, MiB | 0.516 | 37.031 | 31.906 |
| Arenas reclaimed cumulatively | 0 | 0 | 27 |
| Process RSS, MiB | 42.188 | 128.219 | 101.219 |

After the build, about 57.93 MiB is available-block/unused-pool capacity within
still-owned arenas. Releasing the small runtime allows 27 arenas to be reclaimed.
This supports allocator retention/fragmentation as part of the RSS/live-allocation
gap. It does not account for all RSS: large allocations, interpreter/library
memory, mappings and OS residency remain outside this table. No subtraction of
these figures claims uniquely recoverable bytes, and no allocator change is
recommended as a substitute for reducing compiler allocation/lifetimes.

## Ranked recommendations and readiness

| Rank / candidate | What changes | Decision and remaining boundary |
| --- | --- | --- |
| 1. Conservative scalar-only weak cache | Shorter intermediate lifetime; peak −28.5%, RSS −18.3%; no retention saving | **Ready for scoped implementation and independent review**, retaining the exact-type/known-carrier strong fallback. Add the 16 lifetime cases as regressions, keep callbacks and occurrence attribution exact, and measure source-integrated timing/RSS before accepting the observed tradeoff. No public contract change is proposed. |
| 2. Intern immutable template facts at capture | 1,695,090 fewer named metadata constructor calls; build median −40.6% | **Ready as a separate speed proposal**, not a demonstrated peak/RSS optimization. Replace AST scaffolding with an explicit capture interface and measure source-integrated RSS; preserve full facts, remapping and the eager diagnostics path. |
| 3. Release completed source graph ownership | Earlier release; about 0.45 MiB traced-peak decrease in one screen | **Deferred**: small, unreplicated benefit. Design a truthful internal scalar carrier, preserving full-mode and escaped source views, before implementation. |
| 4. Snapshot reuse / definition interning | Avoid redundant record construction / smaller snapshot representation | **Defer reuse; decline interning as tested**. No peak benefit for reuse; interning increases screened peak. Existing frozen generic-mapping caches also need aliasing review for reuse beyond freshly frozen drafts. |
| 5. Compact mutable drafts / origins / unused subplan history / pre-lookup step construction | Smaller necessary records or avoided construction | **Not ready**: source-backed opportunities only; sizing ceilings and shallow tables are not measured savings. Mutable facts, identity, provenance and cache eligibility require designs and bounded probes. |
| 6. Compact diagnostic history | Smaller captured facts in diagnostics-enabled modes | **Not ready**: preserve per-attempt identity/order, incomplete states, public failure graphs, budgets and census without replay. Any loss of evidence needs a maintainer contract decision. |
| Rejected: plain weak cache; omit decorator facts | Earlier release of arbitrary values; skipped evidence construction | **Incompatible** with actual value lifetimes and build-rule/failure explanations respectively. Do not implement under existing contracts. |

The most direct avoided-creation result improves speed but not live peak. The
strongest measured memory opportunity instead shortens intermediate ownership.
These findings answer different parts of the original hypothesis and should not
be collapsed into a single “metadata saved” number. Task 05 already avoids freezing
discarded successful drafts; no new credit is claimed for that work. Task 04's
subtree-sharing implementation remains reverted.

All retained executable evidence tooling passes Ruff lint/format, `ty check`,
and byte-compilation. Original failed probe outputs remain alongside corrected
results. The one full-suite warning is the existing Starlette/httpx deprecation.
`06-validation.json` records evidence consistency checks; `06-source-check.json`
verifies unchanged production/test/benchmark content and revision. The
[hashed evidence index](evidence/06-evidence-index.json) lists every Task 06 file,
including exact historical probe source versions. No commit or push was made.

## Reproduction and evidence ownership

From the repository root, use the existing interpreter:

```sh
.venv/bin/python -m benchmarks.graph_memory_evidence repeat --routes 8 --repeats 3 --no-explain-metadata --output .work/graph-memory-optimization/evidence/06-baseline.json
.venv/bin/python .work/graph-memory-optimization/evidence/06-probe.py repeat --probe baseline --output .work/graph-memory-optimization/evidence/06-repeat-baseline.json
.venv/bin/python .work/graph-memory-optimization/evidence/06-probe.py repeat --probe scalar-weak-cache --output .work/graph-memory-optimization/evidence/06-repeat-scalar-weak-cache.json
.venv/bin/python .work/graph-memory-optimization/evidence/06-probe.py repeat --probe intern-template-facts --output .work/graph-memory-optimization/evidence/06-repeat-intern-template-facts.json
.venv/bin/python .work/graph-memory-optimization/evidence/06-probe.py timeline --output .work/graph-memory-optimization/evidence/06-timeline.json
.venv/bin/python .work/graph-memory-optimization/evidence/06-probe.py count --output .work/graph-memory-optimization/evidence/06-count-baseline.json
```

The counterexamples and separate lifetime/allocator observations are reproducible
with the same interpreter:

```sh
.venv/bin/python .work/graph-memory-optimization/evidence/06-value-kinds.py scalar-weak-cache
.venv/bin/python .work/graph-memory-optimization/evidence/06-payload-lifetime.py weak-activation-cache
.venv/bin/python .work/graph-memory-optimization/evidence/06-cache-lifetime.py --weak
.venv/bin/python .work/graph-memory-optimization/evidence/06-allocator.py 2>allocator-stats.txt
```

Use `--full`, `--diagnostics`, and `--overlays` independently for alternate modes;
`measure --heap` runs one traced process. `pytest --probe NAME -q tests/...`
installs a candidate before running existing tests. Run every measurement/test
serially. The raw JSON includes production source hashes, interpreter/platform,
actual build flags, ownership, transformed function hashes and probe-source hash.
Older probe versions are inert `.py.txt` files; no experiment is active outside
its process. Preserve the original raw files when making another comparison.
