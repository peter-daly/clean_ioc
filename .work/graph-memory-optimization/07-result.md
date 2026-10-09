# Task 07 — object layout and avoidable allocation

Investigation complete, 2026-10-09. No production optimization, commit, push,
or pre-compilation implementation is part of this task. Source baseline:
`d51b6f569e67891e72e022b35aa5590c1c0fda46`.

The [source-backed inventory](07-inventory.md) covers the four scoped areas and
all execution carrier MROs. Effective slots and cache lookup placement have
independent executable probes. Compact indexes have an artifact compatibility
blocker; mutable draft sharing remains representation design work.

## Measurement method and source setup

Each final candidate has five normal and three separately traced fresh processes,
run serially on Python 3.14.4, macOS ARM64, using the existing `.venv`. The unchanged
rich eight-route fixture uses `diagnostics=False`, `explain_metadata=False`,
`allow_scope_builders=False`, with no caller-retained builder/views or profiling.
Build timing includes fixture import, composition and compilation. Cleanup and
provider/activation/laziness checks are the production evidence runner's checks.

The probe imports an isolated transformed `container` module. Preparation saves
inert source text and same-interpreter bytecode before measurement; each load
verifies original-source, transformed-source and bytecode hashes. There is no
source patch active in the shared checkout. Other Python versions fall back to
compiling the same inert source for semantic checks, not memory comparison.
`07-prepared-sources.json` and per-run hashes identify exact implementations.

Two preliminary loader baselines are preserved and **excluded**: the first
rewrote ASTs during import, and the second compiled prepared source during import.
Both left roughly 88–90 MiB setup RSS and about 166 MiB normal build RSS. The final
bytecode loader has 47–49 MiB setup RSS, 130.578 MiB normal build RSS and a 72.844
MiB traced build peak, agreeing with Task06's build peak. Setup/import allocation
is outside the tracer; before-build RSS is recorded and never subtracted to claim
candidate savings. Final candidates use the same loader. Historical screens with
older loading methods are explicitly exploratory, not mixed into this comparison.

Inventory, constructor wrappers, GC census, draft packing and microallocation
screens run separately. They do not read instance dictionaries and are excluded
from the repeated memory/build measurements. Retained Python allocations follow
collection; peak is the build tracer high-water mark. Current RSS, process peak
RSS, timings, object counts and backing storage remain separate quantities.

## Results

`07-extended-comparison.json` combines the initial three normal/three traced
processes with two additional counterbalanced normal processes per candidate.

| Median, eight routes | Baseline | Effective slots | Pre-lookup | Compact indexes |
| --- | ---: | ---: | ---: | ---: |
| Build, seconds | 12.248 | 12.378 | 12.256 | 12.503 |
| Cold resolution workload, ms | 17.368 | 17.572 | 17.798 | 17.563 |
| Retained Python, MiB | 3.099 | 3.044 | 3.099 | 3.099 |
| Traced build peak, MiB | 72.844 | 71.422 | 72.844 | 67.851 |
| Current RSS after build, MiB | 130.578 | 128.812 | 130.188 | 121.031 |
| Process peak RSS, MiB | 130.578 | 128.812 | 130.188 | 121.031 |
| Runtime records / execution steps | 8,982 / 1,765 | 8,982 / 1,765 | 8,982 / 1,765 | 8,982 / 1,765 |

Effective slots lower traced peak **1.422 MiB / 1.95%** and runtime retention
0.055 MiB. Normal RSS median falls **1.766 MiB / 1.35%**, but ranges overlap:
slots 122.219–131.266 MiB; baseline 129.703–131.562 MiB. This establishes a modest
Python-allocation benefit and a favorable RSS median, not a universal RSS reduction.
Build median is 1.1% higher; ranges overlap (slots 12.206–12.810 s; baseline
12.207–12.394 s). The source-integrated implementation needs its own acceptance
measurement, especially for this small RSS/timing signal.

Pre-lookup has **no demonstrated build-peak or runtime-retention benefit**.
Its build median differs by +0.007 seconds / +0.06%; normal RSS differs by
−0.391 MiB with overlapping ranges. Avoided constructor calls are not equivalent
to released cache entries, lower live peak, or an established speed improvement.

Compact indexes lower traced peak **4.993 MiB / 6.85%** and normal current/peak
RSS **9.547 MiB / 7.31%**. Normal ranges are separated: indexes 119.453–123.750
MiB versus baseline 129.703–131.562 MiB. Build median rises **2.1%**; ranges are
12.395–12.545 versus 12.207–12.394 seconds. Retained runtime Python memory is
unchanged because successful reduction already releases these sidecars. This
is a useful representation result, but the eight artifact failures below prevent
calling the prototype compatible or ready.

Longer warm-resolution comparisons are reported below separately from these
short cold samples.

## Carrier layout and avoided construction

At primary return, all candidates have **62,581 live steps**, including 31,026
value carriers and 31,153 ordinary registration carriers. Slots changes no
constructor counts or live counts. All ordinary/observed step classes then have
zero dictionary offset and retain nonzero weakref support; both observed
registration mixins must be fixed alongside the base.

On Python 3.14 the primary step shallow total is the **same 5,509,912 bytes**
before and after. Separately allocating 100,000 `_ValueStep`s reports the same
5.6 MB shallow instance total, but actual retained traced allocations fall from
8.805 to 6.401 MB, including the same list. No instance dictionary was accessed.
This is measured allocation associated with effective dictionary support that
shallow instance sizing misses; it is not a dictionary materialization experiment.
Microallocation timing is a screen, not a whole-build speed claim.

Pre-lookup reduces registration-base constructor calls **56,708→31,627**:
**25,081 avoided calls**, while all other tracked carrier creation counts and
primary live counts remain unchanged. The count includes source compilation;
one `_ValueStep` call is the inventory's weakref check, not compiler work.
Selection/derive/configuration/decorator processing, existing cache eligibility,
cleanup/sync calculations, unique/reused counters and exact prior-step attribution
remain intact. Maps and per-call/configured/decorated cases still construct.
Strong cache ownership remains intact, including opaque values and map keys.

For resolution timing, three fresh processes per carrier/lookup candidate each
perform 50 measured workloads after one warmup in a new scope each time. Scope
cleanup, explicit GC and topology validation run outside timing; fixture counters
reset per workload. Median of process medians is **13.391 ms baseline, 13.304 ms
slots, 13.486 ms pre-lookup**. The respective process-median ranges are
13.177–13.581, 13.238–13.445 and 13.446–13.508 ms. These overlap and do not settle
a small throughput difference. The +0.203/+0.430 ms cold-sample differences remain
recorded above; warm scopes and warmed singleton caches are a different workload.
No general runtime speed or zero-overhead claim follows from either set.

## Smaller mutable drafts: bounded feasibility, not a build saving

Primary compilation has 88,558 drafts and only 116 identity-distinct tuples of
the eleven definition fields. Offline tuple/key/dictionary packing costs 36,240
shallow bytes and 0.177 seconds in one untraced observer run. A separate pool-only
tracer measures **77,304 retained bytes / 77,720 peak bytes**, including 40,832
bytes of 1,276 newly owned integer key referents. Definition values borrow the
existing draft referents, which are not charged again. Its packing takes 0.682 s
under tracing; this is not a normal-build timing comparison. Replacing eleven references
with one has an **ideal 6.756 MiB shallow ceiling**, before replacement objects,
constructor tuples, lookup keys, pool ownership and field-access costs. This is
not a measured peak, retention or RSS benefit.

The bounded COW microprobe checks sharing, one-occurrence replacement and restoring
previous reference identity without mutating peers or calling application equality.
It does not integrate a new draft class or claim existing compiler behavior is
preserved. A separate opaque-payload check also shows that a strong fact pool
keeps an unused overwritten fact alive after both drafts return to their original
definition; clearing the pool releases it. Real writes occur in source enrichment, visibility aliases, preference
previews, cached-root rebinding and clone boundaries. A strong pool can prolong
opaque overwritten facts and retain discarded definitions through surviving graphs.
Releasing it must preserve escaped callback Components and frozen snapshots.

**Not ready:** design graph-local pool ownership/release, immutable replacement,
compatibility with field/dataclass readers and per-occurrence generic caches, then
measure constructor/transition overlap and changed-fact frequency. Do not revive
Task04 contextual subtree sharing or count Task05's existing skipped freezing again.

## Index representations and provenance

At primary completion, origins use 5,242,960 shallow dictionary bytes for 88,558
keys but only 45 origin objects. These values already share; there is no additional
origin-object saving to claim. Decorator sidecars use 2,621,528 dictionary bytes
for 56,522 distinct remapping carriers. Their keys span 1–88,507 and their insertion
order differs from numeric order.

The bounded sequence/fallback prototype preserves keys and insertion order using
positive-ID reference storage, a key-order list and a sparse fallback dictionary.
It does not renumber occurrences, combine graph namespaces or lose negative/large
keys. Its bounded mapping checks cover holes, updates, deletion/reinsertion, proxy
conversion, negative provider-view-sized IDs and extremely sparse IDs. Dense growth
is guarded; referents are shared, not copied.

A separate conversion/storage screen holds original dictionaries and observer
alternatives simultaneously, so it is **not** a build-peak comparison. Origins'
combined alternative object/list/list/sparse backing is 1,424,040 bytes; decorators'
is 1,293,704 bytes. Dense lengths are 88,559 and 88,508, with no sparse entries
in this fixture. Value/key identities are borrowed, not charged twice. Traced
conversion takes 0.259/0.169 seconds; the integrated build prototype instead
populates alternatives directly and has no whole-map conversion phase.

Lookup has a concrete cost: 442,790 origin `.get()` calls take median 10.270 ms
on dictionaries versus 52.386 ms on the prototype; 282,610 decorator calls take
7.031 versus 34.150 ms. Three batches each, untraced, one observer process.
These ~5× microlookup costs are not the whole-build +2.1% cost and should not be
extrapolated into a general inspection throughput claim.

**Not ready:** eight full-mode artifact tests fail because the existing schema-5
writer requires mapping proxies to have real-dictionary backing (`graph_artifact.py:201`).
The codec remains unchanged. Public/failed graph behavior and ordinary reduced
runtime success do not erase this incompatibility. A measured export/codec strategy
must preserve backing sharing and exact facts; simply converting every proxy may
reintroduce table storage and duplicate shared maps. Mutation-during-iteration
semantics, deletion cost and extreme namespace sparsity also need an explicit design.
The prototype is not a drop-in generic mapping: a bounded check records that
`{1: value}[1.0]` works while the array/fallback prototype misses that numeric-equivalent
lookup. Existing compiler occurrence-ID paths match, but public/private consumer
contracts and nonstandard key equivalence must be decided explicitly.
Definition-level provenance plus exception maps remains deferred because definition
identity does not determine source, layer, boundary and alias origin evidence.

## Semantic checks and implementation readiness

Slots and pre-lookup each pass **all 2,132 existing tests**: 2,129 repository tests
and the three executable examples, run separately and serially. Indexes pass
2,124 and fail only the eight full-mode artifact cases listed above. All probes
also pass the sixteen reused opaque-value lifetime cases across diagnostics/full/
reduced combinations, with identical callback order and returned arguments.

Eight-route reduced step class/primary occurrence/multiplicity attribution, two-route
full manifests, complete normalized decorator facts and template callback counts
match baseline exactly. Failed reduced diagnostics-off finalization still exposes
the selected decorator fact. Existing tests cover callbacks and saved Components,
providers/maps, generics/aliases, scopes/overlays, cleanup/ownership, warmup,
profiling, budgets, aggregation and error evidence. No callback replay is added.
The only full-suite warning is the existing Starlette/httpx deprecation.

Slots passes the 97 focused profiler/reduced-mode/artifact tests independently on
Python **3.11.13, 3.12.11 and 3.13.5**, plus the complete 3.14.4 suite. Cross-version
checks use existing interpreters with pure Python dependencies from the current
`.venv`; plugin autoload is disabled and pytest-asyncio explicitly loaded. These
are semantic checks, not matched cross-version performance environments. The
slot microprobe retains weakrefs on all four. Python 3.15-dev is experimental in
CI and unavailable locally; it has not been validated here. Older interpreter
allocation/shallow values differ, so the 3.14 memory saving is not extrapolated.

| Rank | Proposal | Readiness and decision |
| --- | --- | --- |
| 1 | Effective slots for `_Step` and both observed registration mixins | **Ready for scoped implementation and review**, preserving explicit weakrefs and profiling slots. Modest traced peak reduction is established; RSS/timing are noisy and need source-integrated acceptance measurements. Review private arbitrary-attribute/constructor monkeypatch seams. Leave public Scope/Container and legacy protocol inheritance unchanged. |
| 2 | Compact origins/decorator indexes | **Not ready**, despite measured peak/RSS benefit. Resolve artifact backing/codec compatibility, mapping key-equivalence/iteration behavior, sparse capacity and lookup tradeoffs. Preserve exact failed graph/provenance facts and per-compiler namespaces. |
| 3 | Share draft definition facts before freeze | **Not ready**. The 116-definition pool is small, but old-fact lifetime, writes/restores, pool release, field compatibility, lookup/mutation/transition costs and actual replacement build peak remain unresolved. The 6.756 MiB ceiling is not an achieved saving. |
| 4 | Cache lookup before registration carrier construction | **Mechanically ready as a separate allocation-cleanup proposal, deferred as a memory optimization**. 25,081 calls are avoided with semantic checks, but no peak, RSS or speed benefit is established. Do not complicate the compiler or prioritize it over demonstrated memory opportunities without source-integrated justification. |
| Deferred | Slot legacy `_Registration` via public `Registration(Protocol)`; observed Scope/Container layouts | Public inheritance/dynamic seams and low-volume objects make these separate compatibility work, not part of the measured carrier change. |

All retained executable tools pass Ruff lint/format, `ty check` and byte-compilation.
Source verification covers all 191 tracked production/test/benchmark files; they
match the committed baseline. The evidence index hashes every Task07 deliverable
and retained probe/source version. No production optimization is active.

## Compatibility and reproduction

Carrier probes preserve weak-reference support explicitly for possible future weak
cache work. The main metadata, graph/view, record/definition and decision/explanation
classes already lack dictionaries. The private carrier base and both observed
registration mixins need effective slots together; declarations on subclasses alone
are insufficient. Legacy registration's public protocol inheritance is a separate
compatibility boundary and is not changed.

Task06's weak-cache and immutable-fact proposals remain unimplemented. This task's
probes neither weaken cache ownership nor skip callback work; savings cannot be
added to Task06's figures without a new combined experiment. Broad weak caching
remains rejected by its lifetime counterexamples.

```sh
.venv/bin/python .work/graph-memory-optimization/evidence/07-prepare.py
.venv/bin/python .work/graph-memory-optimization/evidence/07-probe.py repeat --probe baseline --output .work/graph-memory-optimization/evidence/07-repeat-baseline.json
.venv/bin/python .work/graph-memory-optimization/evidence/07-probe.py repeat --probe slots --output .work/graph-memory-optimization/evidence/07-repeat-slots.json
.venv/bin/python .work/graph-memory-optimization/evidence/07-probe.py repeat --probe prelookup --output .work/graph-memory-optimization/evidence/07-repeat-prelookup.json
.venv/bin/python .work/graph-memory-optimization/evidence/07-probe.py repeat --probe indexes --output .work/graph-memory-optimization/evidence/07-repeat-indexes.json
```

`inventory` is a separate constructor/live/layout and primary-index census;
`07-layout-micro.py` measures 100,000 value carriers without materializing dictionaries;
`07-semantics.py` reuses Task06's source-attribution/failed-finalization checks;
`lifetimes` reuses its sixteen opaque-value cases. Reused helper JSON internally
labels its original Task06 probe `baseline`; Task07 installation comes first and
the Task07 command/file name plus prepared-source hashes identify the actual candidate.

This remains a synthetic fixture, not production capacity evidence. It has no
custom validation rules or warmup declarations in its measured build; those paths
are separate semantic checks. No production-source benefit is inferred merely from
smaller instance sizes or avoided constructor counts.
