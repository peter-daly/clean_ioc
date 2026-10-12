# Task 14 result — share immutable definitions in mutable drafts

Completed 2026-10-10 by the assigned high-effort agent. **KEEP** the scoped
candidate, accepted after coordinating source, evidence and check review. Repetition-heavy
compilation saves about **6.4 MiB of traced peak**, with about **1.4% slower builds**.
This is not a universal memory improvement: **2,000 unique definitions increase
compiler peak by 0.88–1.29 MiB (4.06–6.31%)**, and retained memory increases slightly
in every control. Adaptive bypass remains an unassigned future refinement; it is not added
to tasks 15–18 or bundled as an unmeasured policy.

The [mutation/ownership inventory](14-inventory.md) records the complete field,
setter, source enrichment, boundary, preference, clone, snapshot and introspection
audit. Task 10/11 modes, rich mandatory-rule evidence, failures and expiration
remain intact. The activation cache from task 13 is unchanged.

## Representation and correctness boundary

Mutable drafts now hold one immutable definition and a graph-local weak pool
reference instead of eleven repeated metadata slots. The main compiler's draft
constructor looks up the identity key before creating the definition. COW setters
replace only the receiving occurrence's definition; changing or restoring one
occurrence cannot alter another. All contextual fields, ownership, registration
and occurrence identities, topology and generic caches stay occurrence-local.

Keys contain only built-in integer identities. A live definition owns every
referent in its key, while a standard weak-value index removes dead definitions
and keys. The pool never owns opaque facts strongly, definitions never reference
the graph or pool, and final freeze clears both weak and final-normalization keys.
Overwritten opaque values release as soon as legitimate drafts/snapshots stop
owning them. Snapshot records remain stable, without retaining their source pool.
No runtime instance sharing, new runtime traversal or callback replay is added.

Root review found a real error in the first candidate: reusing final-graph ordered
Tag normalization for live drafts merged distinct tags tuple identities before
`when` callbacks. A public two-registration example changed selection in both
modes. The corrected live key uses **the exact tags tuple identity**. Only final
graph freeze retains the existing ordered-Tag normalization. Setter/restoration
and detached snapshot identity are tested explicitly. The superseded source/log
are archived and excluded from accepted samples.

The private draft remains a slotted dataclass with explicit constructor support
for existing arguments and `dataclasses.replace` metadata overrides. Its private
field/repr/equality representation deliberately changes; no public dataclass API
is changed. The artifact adapter excludes the temporary pool from serialized
graph slots and reconstructs an empty pool at load. Existing payload fields and
schema remain unchanged; parked precompilation remains parked.

## Measurement identity and method

Task 13's accepted source/fixture/harness hashes, Python **3.14.4**, macOS ARM64
platform and settings were verified before editing. Its final AFTER is reused as
the matching shared-control BEFORE. The original dirty working diff and source
copies were saved first in `evidence/14/`. HEAD remains `34d1ea02840afe6f23f0693b32651028ec7d9128`,
branch `version2`, version `2.0.0rc4`; prior dirty changes remain intact.

The unchanged [shared harness](evidence/12/measure.py) runs **three fresh normal
and three separate traced processes per control**, serially without competing
tests or benchmarks. It uses public modes, eight routes for run/rich-rule run and
two routes for analysis. The arbitrary rich rule asserts full temporary
diagnostics. Tracing covers fixture import/composition/build; retained allocations
are after collection. Callers retain neither builders nor callback snapshots.
The [AFTER samples](evidence/14/after.json),
[range/median summary](evidence/14/comparison-summary.json) and
[evidence cross-check](evidence/14/evidence-validation.json) are preserved.

Medians, **accepted task 13 → task 14**:

| Control | Build s | Resolve workload ms | Retained traced MiB | Peak traced MiB | Current / peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| Run, 8 routes | 5.881 → 5.961 | 14.041 → 14.363 | 3.103 → 3.110 | 52.137 → 45.770 | 106.734 / 106.734 → 102.688 / 102.688 |
| Rich-rule run, 8 routes | 8.634 → 8.755 | 15.001 → 14.871 | 3.102 → 3.110 | 265.468 → 259.045 | 325.828 / 328.828 → 322.500 / 322.500 |
| Analysis, 2 routes | 0.2933 → 0.2920 | 2.747 → 2.602 | 6.482 → 6.494 | 7.627 → 7.644 | 49.359 / 49.359 → 49.109 / 49.109 |

Run traced peak falls **12.21%**, rich-rule run **2.42%**; build medians rise
**1.36% / 1.40%**. Analysis peak rises **0.018 MiB (0.23%)**. Run/rich retained
allocations rise about 7.3/7.7 KiB, analysis about 11.9 KiB. Definitions need weak
reference support: their measured shallow size rises 120→136 bytes, and the graph
carrier gains eight bytes plus its empty pool carrier. These costs are included
in retained/peak totals, not hidden behind the draft saving.

Normal build ranges are 5.871–5.997→5.959–6.003 seconds for run,
8.580–8.716→8.747–8.995 for rich run, and
0.2871–0.2960→0.2892–0.2930 for analysis. Traced peak ranges are:

| Control | BEFORE MiB, min–max | AFTER MiB, min–max |
| --- | ---: | ---: |
| Run | 52.136708–52.137168 | 45.769706–45.769884 |
| Rich run | 265.467848–265.468532 | 259.044365–259.045216 |
| Analysis | 7.626232–7.626953 | 7.644362–7.644657 |

Run RSS ranges 105.203–110.125→99.766–103.656 MiB; rich current RSS ranges
324.734–328.891→319.625–325.484 MiB overlap. Analysis RSS ranges also overlap.
The short run resolution median rises 0.322 ms, with an AFTER range of
14.164–15.960 ms; rich/analysis medians fall. There is no changed resolution
algorithm and no speedup claim. Root review did not require repeating task 13's
cold/steady grid; task 18 owns combined resolution verification.

Every shared sample preserves callback/template/activation results, discovery,
execution steps, relationships, kinds, field identity patterns and graph counts.
Run retains 8,982 records, 116 definitions, 1,765 steps and 51 catalogue entries.
The cross-check permits only the explicitly changed shallow definition/graph sizes.

## High-definition-diversity counterexample — final matched control

The final [compiler-only harness](evidence/14/diversity-compiler.py) imports the
library before tracing, then creates 2,000 distinct service classes, registers
and builds them with provider roots disabled, collects, and resolves every class
once with exact-type checks. Its modes/rich rule match the other controls.
Both policies compile the same two library modules through the same SourceLoader
strategy before tracing, retaining original source filenames; BEFORE reads the
saved accepted-task-13 bytes and AFTER the actual candidate. This avoids source
compilation versus cached-bytecode RSS bias. Loaded-source hashes are checked for
all **36 fresh processes**, three normal plus three traced per mode/policy.
Current and peak RSS are sampled outside the build/resolution timers.

[BEFORE](evidence/14/diversity-compiler-before.json),
[AFTER](evidence/14/diversity-compiler-after.json),
[full ranges](evidence/14/diversity-compiler-summary.json), and
[identity checks](evidence/14/diversity-evidence-validation.json):

| Control | Build s | Resolve ms | Retained traced MiB | Peak traced MiB | Current / peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| Run | 0.5659 → 0.5755 | 6.614 → 7.090 | 6.795 → 6.899 | 18.899 → 20.091 | 109.672 / 109.672 → 111.312 / 111.312 |
| Rich run | 0.6072 → 0.6187 | 6.711 → 6.877 | 7.302 → 7.404 | 21.331 → 22.622 | 112.984 / 112.984 → 113.078 / 113.078 |
| Analysis | 0.5795 → 0.5881 | 7.910 → 8.180 | 15.517 → 15.630 | 21.681 → 22.560 | 111.828 / 111.828 → 112.438 / 112.438 |

Peak increases **6.31%, 6.05%, 4.06%** (1.192, 1.291, 0.879 MiB);
retained allocations increase 0.104, 0.102, 0.113 MiB. Build medians rise
**1.70%, 1.90%, 1.48%**. Run RSS increases 1.64 MiB; rich/analysis RSS ranges
overlap. Source compilation before tracing raises process RSS for both policies,
so these absolute RSS values must not be compared with the ordinary shared-harness
processes. Small resolution medians rise 0.476/0.166/0.270 ms; run and analysis
ranges overlap. No resolution speed improvement is claimed.

Normal build ranges are 0.5651–0.5711→0.5748–0.5859,
0.6051–0.6078→0.6159–0.6206, and 0.5785–0.5800→0.5830–0.5932 seconds.
Traced peak ranges, in the same order, are
18.898667–18.898960→20.090618–20.091067,
21.331100–21.331355→22.621638–22.622211, and
21.676600–21.685699→22.557630–22.560033 MiB.

The initial diversity harness traced library import as well as compiler work.
An automatic lint cleanup removed its unused `statistics` import after BEFORE;
that changed modules imported before tracing. Its apparent **+4.52%** peak was
therefore **invalid as compiler evidence**. A matched-import rerun showed the
library-import peak largely masked compiler costs. Those historical rows, plus
an interrupted asymmetric-loader AFTER attempt, remain clearly named and excluded
from this final comparison. The final source loader and compiler-only boundary
resolve both setup mismatches. No application source changed during this correction.

A bounded/adaptive bypass could reduce the unique-definition regression, but
would require a measured mixed representation or ownership/density policy. It is
an unassigned future refinement, not a new task in 15–18. The scoped repeated-
definition gain is retained with this real counterexample explicit.

## Construction, pool costs and freeze overlap

Separate intrusive censuses add constructor/finalizer observers; they are excluded
from timing and byte claims. The exact BEFORE uses saved baseline source copies in
a temporary import tree. Counts after complete runtime release all reach zero.

| Carrier/control | Constructed BEFORE → AFTER | Maximum live BEFORE → AFTER | Retained after build |
| --- | ---: | ---: | ---: |
| Definitions, run/rich 8 | 92,104 → 304 | 2,019 → 288 | 116 → 116 |
| Drafts, run/rich 8 | 90,250 → 90,250 | 88,558 → 88,558 | 0 → 0 |
| Records, run/rich 8 | 194,306 → 194,306 | 10,674 → 10,674 | 8,982 → 8,982 |
| Definitions, analysis 2 | 4,696 → 84 | 981 → 80 | 80 → 80 |
| Definitions, unique run | 2,000 → 2,000 | 2,000 → 2,000 | 2,000 → 2,000 |

The overall maxima can occur at different times and must not be summed. The
primary run graph still owns 88,558 drafts until existing retention runs; this
candidate releases no occurrences early and avoids no snapshot record copies.

At that primary graph, draft shallow storage falls 21,962,384→15,586,208 bytes
(248→176 per draft). The 116 live definitions cost 15,776 bytes; weak-pool key
tuples 15,776, key integers 40,832, weakrefs 10,208, backing table 4,688 and
pool/mapping/dictionary wrappers 176 bytes. These are separate ownership
components, not additional measured savings. Temporary constructor/key tuples,
COW replacements, weak callbacks and freeze overlap are included in actual traced
peaks; the shallow census is not a complete allocator model.

The unique control reverses the tradeoff. Its 2,000 drafts save only **144,000**
shallow bytes, while definitions cost **272,000** and the live weak pool costs
**1,226,184** in the same key/integer/weakref/table/wrapper categories. No definition
construction is avoided. The table alone is 73,808 bytes, keys 272,000, integer
leaves 704,000 and weakrefs 176,000. This explains why field-count arithmetic is
not a valid peak-memory forecast.

A tagged eight-route screen covers 29,972 nonempty-tag drafts and source clones:
28 exact tag tuples / two ordered patterns still produce only 116 live definitions.
Registration tuples are reused across occurrences. The screen is a separate
intrusive count, not another timing/memory claim.

[Separate freeze probes](evidence/14/freeze-profile.py) reset tracing peaks per
freeze and therefore are **not** whole-build peak measurements. Largest bounded
analysis freeze: 2,685 drafts, elapsed 54.6→53.5 ms, current allocations before
10,915,151→10,770,297 bytes, phase peak 10,965,511→10,915,769. Largest unique
freeze: 2,000 drafts, 53.3→36.0 ms, current before 18,196,996→19,493,579 bytes,
phase peak 19,864,385→20,920,891. The latter starts with 2,000 live pool entries;
its extra backing storage already exists before freeze, and weak and final
normalization keys overlap during the transition. All weak keys are cleared at
completion. These are single instrumented phase observations, not timing medians.
The main matrices capture actual total peaks including the entire transition.

The shared runner's historical `retained_definition_index_bytes=0` describes the
released final normalization index. The new empty weak-pool carrier remains on
frozen graphs and is included in measured retention; the separate census exposes
its actual backing costs.

## Verification and source handoff

- [Full CI](evidence/14/make-ci.txt) passes: lint/format/type checks, **2,338 tests**,
  executable documentation and BenchBro discovery. The existing Starlette warning remains.
- All **23 new regressions** pass, covering every COW field, restoration, hostile
  referents, exact tuple identities, public selection in both modes, snapshot
  stability, weak pool/opaque ownership, dataclass replacement and failed builds.
- **167 focused checks** pass on isolated Python
  [3.11](evidence/14/python311.txt), [3.12](evidence/14/python312.txt),
  [3.13](evidence/14/python313.txt); these include all 68 task-13 cache cases,
  25 inspection lifetime cases, 18 direct-fact cases and artifact round trips.
  Python 3.14.4 is covered by full CI.
- [Strict docs](evidence/14/docs-strict.txt) and `git diff --check` pass.
  The final evidence-only loader addition also passes separate final
  [lint](evidence/14/final-lint.txt), [format](evidence/14/final-format.txt) and
  [type checks](evidence/14/final-typecheck.txt); runtime/tests are unchanged from full CI.
- The existing freeze-capacity dataclass-reader test was adapted to flatten all
  definition and occurrence facts, excluding only the temporary pool. Its original
  all-facts/capacity assertions remain effective; full CI includes all four cases.

[Accepted-source identity](evidence/14/accepted-source.json) and the
[task-only patch](evidence/14/task14-source.patch) preserve the final candidate
relative to accepted task 13, with all prior dirty work retained. Exact measured
script forms are archived as `*.measured.txt`; only formatter/type comments changed
those final workloads. The artifact adapter's direct slot assignment became
`object.__setattr__` for the static union checker; its measured form is archived and
full CI repeats artifact round trips. Runtime, fixture and shared harness source
remain byte-identical to the final shared matrix. The diversity setup corrections
are separate observer changes and are recorded above, not silently treated as
formatting-only changes.

Task 15 must start from this accepted source, preserving task 10–13 contracts,
exact live tag identity and weak-definition ownership. Audit current exact-dict
and mapping walkers, including plan closure, runtime retention and instrumentation,
before integrating any historical compact-index probe. Historical task 09 is a
reference, not a production patch to apply mechanically. Topology/relationship
packing is task 15; snapshot copying task 16; occurrence release task 17. Task 18
must carry both the repetition-heavy gain and unique-definition regression and
measure the combined source rather than adding percentages.

No commit, version bump, push, release, deployment, precompilation promotion or
task 15 implementation was performed.
