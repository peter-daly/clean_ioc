# Task 15 — compact sidecar indexes; wider tables declined

Status: complete — scoped index KEEP accepted; wider-table DROP / DEFER after root review.

The scoped candidate adopts compact origin/decorator sidecars from the corrected
task 09 direction, with additional native-operation fixes found during current
source review. Wider relationship interning/ranges/rows are independently **DROP /
DEFER**: the measured corpus has no duplicate nonempty relationship tuples, and
broader representations do not justify their reader/ownership complexity here.
No commit, push, release, version change or precompilation feature is included.

## Scoped implementation and new compatibility findings

`clean_ioc/_compact_index.py` is a private generic carrier installed only for
`_Compiler.origins` and `_Compiler.decorator_explanations`. It keeps original
integer key/value identities, insertion order, bounded dense backing, geometric
small-map reconsideration, sparse fallback and permanent native promotion.
[The inventory](15-inventory.md) records ownership, readers, exact-dict walker
reachability, promotion and public-proxy boundaries.

Current review found three gaps beyond task 09's original differential coverage:

- `isinstance(other, CompactIndex)` could invoke an operand's application-defined
  `__class__` property where a native dictionary would not. Exact type identity
  now unwraps only the private carrier.
- Direct Python dunders accepted keyword keys, and expression-based equality/union
  did not preserve native dunder `NotImplemented` behavior. The candidate uses
  positional-only signatures and direct native delegation; `update(self=...)`
  remains a legitimate mapping entry.
- A foreign key's hash callback could reentrantly cross the 128-entry compaction
  boundary while an outer native operation still held the old dictionary. The
  historical adapter lost an outer insertion (129 native entries versus 128 and
  a missing value). Foreign get/index/membership/write now lock native backing
  **before** application hashing/equality, even in initial fallback. Raising and
  nonraising callback regressions preserve native outcomes/state.

[Boundary evidence](evidence/15/adapter-boundaries.json) preserves original-probe
failures and corrected-source agreement. The old probe/evidence is unchanged.
The private adapter is not a general-purpose dict substitute: unrelated native
`dict.update(raw_carrier)` / `dict(raw_carrier)` use generic Mapping paths and may
rehash foreign keys. No production sidecar consumer uses those raw-source paths.
Existing proxy consumers already use generic Mapping behavior. Receiver copy,
update, equality and union operations use native stored hashes.

Plan/graph sidecars remain graph-qualified through their owning graphs. Current
runtime-retention/composition-release exact-dict walkers follow executable fields,
not these sidecars; broadening them is unnecessary and could inspect application
mappings. Scalar cache eligibility is unchanged. Run reduction/failure expiration,
caller-held proxies, mandatory rich rules, selected discovery, overlays, providers,
cleanup and instrumentation retain tasks 10–14 contracts. There is no callback
replay or added ordinary-resolution traversal. Exact live tag tuple identity and
all task 14 pools/definitions remain unchanged.

The parked codec uses source-coupled schema 8, memoizes shared carrier backing and
encodes compact rows directly without first promoting/copying full dictionaries.
Native fallback/promoted states use ordinary dictionary rows. Decode rejects
malformed, duplicate or noninteger compact rows. Old artifact files are preserved;
new comparison files are under `.cache/graph-memory-task15`. Public analysis remains
outside the codec's supported subset; full artifact controls are explicitly private
historical fixture policies, not a third public mode.

## Main measurements

Task 14's accepted source/fixture/harness hashes were verified first, and its final
AFTER reused as BEFORE. Original source copies and the complete pre-task dirty diff
are retained in `evidence/15/`. The same unchanged task 12 harness runs public run
and rich-rule run at eight routes, public analysis at two routes, three fresh
normal plus three separate traced processes each, serially without another test or
benchmark workload. Python 3.14.4, macOS ARM64, HEAD `34d1ea0`, version `2.0.0rc4`.
The rich rule asserts complete temporary diagnostics. No caller builder or selection
snapshots are retained. Runtime source stayed frozen throughout comparison work.

[Raw AFTER](evidence/15/after.json), [medians/ranges](evidence/15/comparison-summary.json),
[identity/output verification](evidence/15/evidence-validation.json):

| Control | Build s | Resolve workload ms | Retained traced MiB | Peak traced MiB | Current / peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| Run, 8 routes | 5.961 → 6.165 | 14.363 → 14.158 | 3.110 → 3.111 | 45.770 → 40.814 | 102.688 / 102.688 → 90.172 / 90.172 |
| Rich-rule run, 8 routes | 8.755 → 9.031 | 14.871 → 14.728 | 3.110 → 3.111 | 259.045 → 254.088 | 322.500 / 322.500 → 312.266 / 314.938 |
| Analysis, 2 routes | 0.2920 → 0.2967 | 2.602 → 2.676 | 6.494 → 6.437 | 7.644 → 7.588 | 49.109 / 49.109 → 49.500 / 49.500 |

Ordinary/rich peaks fall **4.956 / 4.957 MiB (10.83% / 1.91%)**. Build medians
increase **3.42% / 3.15%**; this is an explicit startup cost, including the rich
path relevant to arbitrary Bark-like mandatory rules. Small analysis saves about
0.056 MiB retained/peak but builds 1.60% slower and has no demonstrated RSS saving.
Run retained allocations rise only about 1.7 KiB, rich run about 0.8 KiB; successful
run releases the sidecars and gets no meaningful retained-memory improvement.
RSS is whole-process memory, and peak RSS is cumulative. Tracemalloc records Python
allocations separately. These synthetic local samples do not establish production
capacity or universal timing estimates.

All samples agree on callback/activation results, discovery, topology counts,
execution carriers and retained graph inventory. Both run controls retain 8,982
records, 116 definitions, 1,765 execution steps and 51 selected registrations.
Analysis retains 2,685 records with 1,549 logical visits. The shared runner's
post-measurement census promotes inspected analysis sidecars and counts only their
72-byte outer carriers in legacy shallow fields. Those two field-size differences
are explicitly allowed by the verifier; they are **not** used as memory totals.
Backing storage is measured separately below.

## Storage, promotion and inspection

The large primary compiler has 88,558 origin entries / 45 borrowed values and
56,522 decorator entries. Actual candidate backing occupies 1,425,368 + 1,241,656
bytes. Origin value/order lists have capacity 89,152 / 88,988; decorator lists
95,752 / 59,424, including Python spare capacity. Origin logical array length is
88,559; decorator length is 88,508. Referenced origins/facts are counted once.

The [policy](evidence/15/policy-checks.json) and [storage](evidence/15/storage.json)
screens cover empty, tiny, dense, sparse, negative, huge, reverse and mixed keys;
the carrier adds 72 bytes in fallback (empty 64→136 bytes, ten entries 352→424).
At 100,000 dense entries, native 5,242,960 shallow bytes become 1,602,104; narrow
get batches cost **2.62× native**. Gapped/reverse/negative/huge controls retain
native backing +72 bytes and cost **1.78–1.99× native** in that observer loop.
These ratios describe mapping operations, not whole builds or resolution.

The 88,558-entry transition screen holds a source dictionary outside its new tracer.
Compact construction newly retains 1,423,968 bytes; promotion newly peaks at
9,288,696 bytes (~8.86 MiB), taking about 23 ms, before releasing compact containers.
This is conversion overlap, not a net process saving. A caller's raw iteration,
views/copy/equality may permanently give up compact savings. Conversions remain
bounded and never allocate arrays proportional to an arbitrary huge key.

Separate constructor/GC censuses count 22 carriers in each large run build, maximum
four live, zero at successful return. Analysis constructs ten, maximum four live,
retains two at return and releases all on runtime teardown. This observer is excluded
from timing and byte claims. Neither snapshots nor failure ownership is pruned.

The bounded 64-component/256-decision inspection screen has identical retained
allocations before/after: rich-rule first/repeat 321,328 / 321,600 bytes; analysis
420,023 / 420,295. Rich first/repeat times are 11.366→12.734 ms /
0.978→1.156 ms; analysis 12.786→12.268 ms / 0.938→0.918 ms. Both compact indexes
stay compact and capacities unchanged. These single observer processes are
indicative, not precision timing claims; callbacks do not rerun.

## Independent wider-table decision

**DROP relationship tuple interning; DEFER packed rows/ranges.** The primary graph
has 44,996 nonempty tuple objects with 44,996 distinct contents; retained run has
4,788 with 4,788 contents. An interning dictionary would add 2,621,528 / 147,544
bytes with zero hits. Empty tuples already share storage. Borrowed integer bytes
are not another saving.

Only one- and two-element sequences are contiguous; the maximum raw range-header
saving is 337,008 primary / 36,064 retained bytes before owned stop integers,
fallback/adapters or public views. An optimistic packed-reference/offset/length
floor could remove part of 2.65 MB of primary tuples, but excludes row carriers,
mutable construction/snapshot ownership, spare capacity, conversion overlap,
large/sparse integer fallback and retrofit of all graph readers. No compiler
benefit is measured for it and no row/range implementation is retained. Task 16
should consider its own snapshot-sharing evidence; task 17 owns last-consumer
lifetime reasoning. This decision adds no new work or contract to those tasks.

## Carry-forward constraints

Task 14's separate 2,000-unique-definition control still has a 0.88–1.29 MiB
compiler-peak regression (4.06–6.31%). This task does not remeasure that control,
claim its regression is offset, or add an adaptive definition-sharing policy.
Stage percentages are not additive; task 18 owns the combined acceptance.

## Cold and steady resolution

[Raw samples](evidence/15/resolution.json) and [ranges](evidence/15/resolution-summary.json)
use three fresh normal processes per mode/policy, with the first resolve cold and
the median of seven subsequent resolves steady. The symmetric source loader loads
the captured task 14 container for BEFORE and current source for AFTER, before
measurement; all fixtures, validation and teardown are identical. Processes run
serially, in run/rich-run/analysis order, each repeat BEFORE then AFTER. This order
is not randomized or counterbalanced, so process/time drift remains a limitation.
The main build grid instead reuses the verified earlier task 14 AFTER baseline;
it is not an interleaved contemporary build comparison.

| Control | Cold median ms, before → after | Steady median ms, before → after |
| --- | ---: | ---: |
| Run | 10.045 → 10.897 (+8.48%) | 9.749 → 10.378 (+6.45%) |
| Rich-rule run | 10.169 → 10.151 (−0.17%) | 9.815 → 9.690 (−1.27%) |
| Analysis | 2.059 → 2.139 (+3.90%) | 1.894 → 1.965 (+3.75%) |

Run cold process ranges are 9.959–11.340 → 9.996–11.240 ms, steady ranges
9.717–11.102 → 9.696–10.842 ms. Analysis cold ranges are 2.058–2.122 →
2.111–2.241 ms, steady 1.887–1.896 → 1.947–1.984 ms. Overlapping run ranges do
not establish equivalence, and the analysis steady ranges do not overlap. These
are unresolved material signals, despite the main grid's near-flat resolve medians.

A separate [untimed access census](evidence/15/resolution-accesses.json) wraps
`_CompactIndex.get`, `__getitem__` and `__contains__` only during each of the same
eight workload resolves, after compilation. All 24 workloads produce **zero calls**
and matching validated outcomes. This rules out direct sidecar lookup cost for
this fixture, but does not identify the timing cause or rule out indirect memory
layout/allocator effects. Task 18 must revisit cold/steady resolution with matched
fresh processes and alternating BEFORE/AFTER versus AFTER/BEFORE ordering, retaining
both process ranges and the relevant analysis/rich controls. Do not dismiss the
signal because runtime code paths are unchanged or add stage percentages.

The full analysis inspection check also retains both compact backings unchanged.
First and repeated explanation/census/traversal/manifest passes have matching
512-decision samples, 1,549 visits and manifest fingerprint, with no callback
replay. Its [before](evidence/15/inspection-full-before.json) and
[after](evidence/15/inspection-full-after.json) observer costs are separate from
build/resolution measurements; final traced peak is identical at 6,732,185 bytes.

## Parked artifact comparison

[Artifact samples](evidence/15/artifacts.json) cover full private fixture export
and load in 24 fresh processes: three normal and three separate traced per
operation/policy. Execution is serial: export before load, each repeat normal then
traced, and BEFORE then AFTER. Source loaders and import boundaries match. Loading
disables both the compiler constructor and public builder; cold resolution and
fixture validation still succeed. Source and files stay frozen throughout.

| Operation | Time s | Retained traced MiB | Peak traced MiB | Current / peak RSS MiB |
| --- | ---: | ---: | ---: | ---: |
| Export | 1.587 → 1.614 (+1.66%) | 38.336 → 33.379 | 85.302 → 80.345 | 155.484 / 188.938 → 145.016 / 179.000 |
| Load | 1.163 → 1.256 (+7.97%) | 37.960 → 33.003 | 66.432 → 60.511 | 130.938 / 154.688 → 124.422 / 148.547 |

Export time ranges are 1.582–1.593 → 1.604–1.717 s; load ranges
1.163–1.171 → 1.249–1.260 s. The roughly 8% load cost is accepted explicitly
for this parked experiment, not hidden by its memory improvement. Subsequent cold
resolve medians are 20.878→21.647 ms after export and 20.809→19.925 ms after load.
Artifact size changes 29,484,153→29,484,171 bytes (+18 bytes).

Export tracing begins before building and resets peak before exporting; retained
compiled graph bytes therefore remain included in export retained/peak totals.
Load tracing begins after imports; cumulative RSS includes prior process work.
Neither is a compiler-only peak estimate. The codec's normal compatibility digest
reads the current filesystem even when the baseline loader executes captured
source; the external [artifact manifest](evidence/15/artifact-files.json) records
actual loaded container/codec hashes and separate file hashes/schema 7 versus 8.
Those executed hashes, not the shared filesystem digest, establish this comparison's
source identity. Archived task 09 files are unchanged; this does not promote the
codec or widen its supported public subset.

## Verification and final decision

**KEEP the scoped origin/decorator indexes**, with approximately 4.96 MiB lower
large compiler peak, about 3.2–3.4% build cost, narrow lookup/promotion costs and
the unresolved resolution signal above. **DROP relationship tuple interning;
DEFER wider rows/ranges** independently. Their measured corpus lacks interning hits,
and speculative layout savings have not earned the additional ownership/readers.

- Python 3.14.4 `make ci`: all lint/format/type checks, **2,386 tests**, executable
  documentation and benchmark discovery pass. One existing pytest warning remains.
  Strict documentation build passes. No blanket formatting of archived probes.
- Python 3.11 / 3.12 / 3.13: **263 focused tests each** covering the new indexes,
  codec, both modes, failures/lifetimes, all 68 cache lifetime regressions, shared
  drafts and instrumentation. Each also passes 10,093 mapping differential checks
  and all 103 native-operation/codec cases.
- Python 3.14 mapping differential/native audits pass, including original six hash
  cases and new hostile-class, dunder, reentrancy, caller-held live proxy, bounded
  sparse/fallback and codec tests. The 48 added pytest cases preserve earlier tests.
- All 16 historical opaque-value lifetime cases pass through a narrow adapter that
  changes only the removed public `build` spelling to private `_build`; original
  probe source is untouched and no historical weak-cache patch is installed.
- Main sample output/source verification, full inspection, artifact sharing and
  round trips, index access census and final task 14 source/patch preservation pass.
  The historical Python 3.15-dev `Latealias` failure remains a nonblocking prior
  environment limitation; no assertion was weakened and it was not rerun here.

Initial failed harness attempts remain in raw evidence: one nonexistent test path,
one overstrict reverse-key test assumption corrected to the actual bounded-checkpoint
contract, an obsolete public-build spelling in the lifetime script, and initial
lint/type-check findings. Corrections affect tests/evidence only after runtime
freeze; measured script copies preserve exact earlier imports and timing boundaries.
The final passing logs identify the accepted state.

[Accepted source manifest](evidence/15/accepted-source.json),
[task-14-relative patch](evidence/15/task15-source.patch), initial dirty diff and
before/measurement copies preserve all prior dirty work and allow reconstruction.
The manifest records executable/source/evidence hashes and final checks. No commit,
push, version bump, release or work on tasks 16–18 was performed. Task 16 remains
queued for root review/assignment. Carry the resolution signal, promotion/read
costs, artifact load cost and task 14 diversity regression into task 18's combined
acceptance; the separate wider-table decision needs no speculative implementation.
