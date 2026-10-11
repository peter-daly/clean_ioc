# Task 17 — transfer retained drafts at the existing freeze boundary

Status: complete — scoped **KEEP**, accepted after coordinating source, ownership, measurement and quality review. Broader
streaming reclamation is **DROP / DEFER** for this workstream. Recorded effort:
extra high. No commit, version change, push, release, deployment or task 18 work.

The one-line production change replaces a dictionary read with `pop` when the
successful runtime closure is moved into its new draft dictionary. The old local
dictionary previously kept all 88,558 drafts alive while 8,982 retained drafts
were frozen into records. Transferring those retained drafts lets the existing
freeze release each replaced draft. The old dictionary still owns every discarded
draft until the same post-freeze disposal boundary.

The [inventory](17-inventory.md) maps selected, rejected and undecided candidates,
late graph-wide checks/rules, callbacks, detached snapshots, source graphs, graph-
qualified provider/owner links, strong opaque caches and original error witnesses.
No closure traversal, callback, eligibility rule, cache, failure policy or public
capability changes. Ordinary analysis already freezes through another path and
keeps its complete evidence. The graph-facing retained set and order are unchanged.

## Bounded last-consumer proof and rejected alternative

The existing closure already scopes numeric IDs to the actual graph and follows
dependencies, decorators, pre-configurations, parents, owners, decorated targets,
projection sources and contextual parents. Ancestor graphs remain independent.
Before transfer, all primary compilation, mandatory final validation, arbitrary
build rules, warmup planning and selected-registration capture have finished.
Later observation preparation sees the same frozen graph.

The old dictionary is a private local owner. Production readers and saved public
Components address `(graph, occurrence)` and do not own that dictionary or a draft
directly. Each transferred draft remains strongly owned by the new dictionary
until freeze constructs its replacement record. Every occurrence field and opaque
definition referent remains owned by that record. Existing final normalization
can replace only the exact Tag tuple with another tuple holding the same ordered
Tag referents; it does not release a distinct opaque value. Generic cache behavior
and exact live callback Tag tuple identity remain unchanged.

The [internal ownership witness](evidence/17/ownership-proof.py.measured.txt)
compares original, retained-only transfer, and broad `del drafts` policies. A
discarded draft owns an opaque object whose finalizer reads a selected Component.
Original and transfer both report `graph_frozen=True` and
`selected_tags_normalized=True`. Broad deletion reports both **False**. Raw
[original](evidence/17/ownership-before.json),
[transfer](evidence/17/ownership-transfer.json), and
[rejected broad deletion](evidence/17/ownership-release-all.json) are retained.
This deliberately constructed internal ownership witness is not presented as a
public-composition recipe. It establishes why the broad alias deletion lacks the
narrow candidate's ownership proof.

General early rejection/subtree pruning is not adopted. Arbitrary late rules and
saved Components still need complete contextual evidence; opaque execution values
keep task 13's existing strong owners. Decision-only summaries cannot replace
those supported readers, and complete compact facts would require a wider graph
representation. No callbacks are replayed, no fine-grained flags or inferred
purity are introduced, and task 04 contextual sharing remains reverted.

## Source identity and measurement boundary

All **46** accepted task 16 source/harness hashes matched before work. The original
dirty patch, status, source copies and identity are preserved under `evidence/17`.
HEAD remains `34d1ea02840afe6f23f0693b32651028ec7d9128`, branch `version2`, version
`2.0.0rc4`; Python **3.14.4**, macOS ARM64. All 45 previously accepted source hashes
other than the deliberately changed container remain unchanged.

The bounded gate uses the unchanged task 12 public-mode sample function at eight
routes: **three fresh normal and three separate traced processes per policy**, 12
processes total, run serially without competing tests/benchmarks. Both policies
compile their respective container source through the same loader before
measurement. Repeat order is BEFORE/TRANSFER, TRANSFER/BEFORE, BEFORE/TRANSFER for
both normal and traced samples. The executed candidate was loaded in memory before
the production edit; the final production file has exactly that executed hash:
`1a60386b392058ac47143b3acf4fc82b1034b95f360854dae2e98ff6cde42223`.

The shared runner's filesystem source digest naturally described the old file
during this proof. Each sample's additional `executed_source` identifies the actual
loaded candidate; the final verifier checks that identity against production.
Source compilation precedes the traced/timed boundary but contributes to cumulative
process RSS. These matched-loader RSS values must not be compared directly with
task 16's ordinary-import controls. Caller builders and callback snapshots are not
retained in this main fixture. Census and phase observers use separate processes.

## Marginal ordinary-run measurements

[Raw samples](evidence/17/screen.json), [medians/ranges](evidence/17/screen-summary.json)
and [verification](evidence/17/screen-verification-final.txt):

| Metric | Task 16 source | Retained-draft transfer |
| --- | ---: | ---: |
| Build seconds | 5.775553 | 5.771859 |
| Shared resolution workload ms | 14.5289 | 14.3767 |
| Retained traced MiB | 3.10995 | 3.10987 |
| Whole-build traced peak MiB | 40.81200 | 39.41341 |
| Current / peak RSS MiB | 129.9375 / 129.9375 | 128.2500 / 128.2500 |

Traced peak decreases **1,466,522 bytes (1.39858 MiB, 3.43%)**. BEFORE peak range
is 42,794,423–42,795,100 bytes; AFTER is 41,327,803–41,327,974. Final retained
memory differs by only **87 bytes**, which is not a retained-memory improvement.
Build median changes −0.064%, with overlapping ranges
5.7523–5.7863 / 5.7375–5.7819 seconds; no build speedup is claimed. Resolution
ranges also overlap, 14.1265–14.6708 / 14.1774–14.6080 ms. This short shared workload
does not resolve the earlier cold/steady timing signals carried to task 18.

RSS decreases 1.6875 MiB in this matched setup; process ranges are
129.7031–130.0469 / 125.7812–128.8594 MiB. Traced allocations and process RSS are
different measures, and this synthetic result is not a general capacity estimate.
All 12 samples agree on callback/template counts, activations, validated outputs,
selected discovery, executable relationships and retained graph inventory.

Rich-rule run and analysis timing/whole-build peaks are **not remeasured in task
17**. Their public behavior is covered by full/focused checks and their populations
by separate censuses below. Coordinating review explicitly reserved their final
combined timing/memory grid for task 18 rather than duplicating it. Do not apply
the 3.43% ordinary-run result to arbitrary rich-rule builds.

## Simultaneous populations and phase peak

The [six final census processes](evidence/17/census-summary.json) count constructors
and destructors without retaining their objects. The combined maximum is recorded
at each constructor, rather than adding class maxima from different times.

| Population / phase | Original run and rich run | Transfer run and rich run |
| --- | ---: | ---: |
| Drafts constructed | 90,250 | 90,250 |
| Records constructed | 102,490 | 102,490 |
| Maximum simultaneously live drafts | 88,558 | 88,558 |
| Maximum simultaneously live records | 10,674 | 10,674 |
| Maximum simultaneously live drafts + records | 99,232 | 90,295 |
| Live drafts at freeze completion | 88,558 | 79,576 |
| Live records at freeze completion | 10,674 | 10,674 |
| Records retained after build, all graphs | 8,982 | 8,982 |

The simultaneous combined maximum falls by 8,937; exactly 8,982 selected drafts
stop being held by the old dictionary at freeze completion. Primary compilation's
88,558-draft maximum is **unchanged**. This is less overlap during finalization,
not fewer contextual occurrences, fewer constructors or streaming compilation.
Definitions (304 created, maximum 288, 116 retained), graphs (427 created, maximum
29, one retained), and generated snapshots remain unchanged. All counted objects
reach zero after runtime teardown for both policies and all three controls.

Analysis's combined maximum stays **3,289**; its 2,847 drafts/7,463 records created
and 2,847 records retained across nine graphs are unchanged. Its extra 162 source
records keep their existing owners. No source graph is reclaimed early.

The [separate original phase observer](evidence/17/phases-before.json) and
[transfer observer](evidence/17/phases-transfer.json) record the largest segment
at runtime closure freeze: **43,186,764 → 41,721,835 bytes**. Primary compilation's
preceding segment is essentially unchanged, 40,405,301 → 40,407,307 bytes. These
observers reset their segment peaks, including nested boundaries; segment peaks
are never summed or substituted for the unmodified whole-build measurements.
Their imports/instrumentation differ from task 16, so their absolute values are
not a continuation of that task's phase series.

## Verification and limits

- Full Python 3.14.4 `make ci` passes: lint, format, type checks, **2,407 tests**,
  executable documentation and benchmark discovery; the existing Starlette warning
  remains. Strict MkDocs and `git diff --check` pass.
- **Six new regressions** preserve discarded opaque finalization after tag
  normalization, retained opaque facts and independent detached snapshot ownership,
  and late arbitrary rule access to rejected live captures in run/analysis success
  and failure/retry. Original issue code, path, origin and callback pass counts are
  checked without replay.
- **462 focused tests** pass on Python 3.14 and 3.13; Python 3.11/3.12 each pass
  **459**, with the existing three TypeVar-default skips requiring 3.13. Coverage
  includes cache/opaque lifetimes, source/target/position callbacks, contextual
  alternatives, templates, boundaries, overlays, typed and managed providers,
  complete/failing rule views, budgets, warmup/observation failures and all 18
  parked artifact round trips. No assertion or supported-version behavior is weakened.
- The retention set, key order, owner links, record/definition layout and artifact
  schema remain unchanged. Recovery from allocation exhaustion or injected private
  freeze faults gains no transactional promise; ordinary user-controlled failure
  paths occur before this branch and keep their original full-evidence handling.
- Initial lint/type findings were confined to new tests and observer scripts and
  are retained in the evidence. Measured script copies preserve exact execution
  before formatting/type annotations; final production bytes exactly match the measured candidate.

[Final verification](evidence/17/final-verification.json),
[task-16-relative source patch](evidence/17/task17-source.patch), and
[accepted-source manifest](evidence/17/accepted-source.json) capture this state.

## Carry to task 18

Keep the bounded transfer; do not add broader occurrence pruning or an adaptive
definition pool policy. Task 14's unique-definition compiler-peak regression
(4.06–6.31%) remains explicit and is not offset by adding percentages. Task 15's
run cold/steady +6–8% and analysis steady +3.75% signals, and task 16's rich-run
main resolution +2.01% nonoverlapping ranges, remain unresolved. Zero direct
sidecar accesses rules out only that direct cost. Task 18 must use fresh matched
processes with counterbalanced BEFORE/AFTER and AFTER/BEFORE resolution order.

The final combined comparison should use the matching public-mode baseline in
`evidence/12/before.json` (accepted tasks 10/11), never summed stage percentages.
No downstream Bark/Cop tests or production capacity claim is made. The parked
artifact remains schema 8 with task 15's load-cost qualification; it is not
promoted. All exclusive intervals are complete; task 18 awaits coordinating review.
