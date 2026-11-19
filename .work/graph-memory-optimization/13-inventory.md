# Task 13 — activation cache ownership inventory

This inventory applies to the task 12 accepted source plus the scoped task 13
candidate. No draft, graph-index, snapshot or occurrence-lifetime representation
change is included.

## Owners and last consumers

| Owner | What it owns | Last consumer / release boundary |
| --- | --- | --- |
| Compiler blueprint, registration specialization tables, layers | Registration definitions, factories/classes, argument policies, tags, source/requested contracts, layer and singleton owner tokens | Compilation, validation, warmup/observation preparation; composition survives in analysis for overlays. Caller builders are independent owners. |
| Primary graph drafts/records | Component metadata and all contextual parent/dependency/decorator/owner links | Existing task 10/11 retention and expiration boundaries. This task does not release graph occurrences early. |
| Activation cache, strong entries | Whole execution closures containing any opaque value, scalar subclass, collection, provider/map, decorator/configuration, unknown carrier or unfamiliar key | Compiler release, including ordinary exception/traceback ownership on failed builds. No destructor-visible application value is released early. |
| Activation cache, weak entries | A weak reference to a completed scalar-only execution plan plus its key and removal closure | Removed when the last required strong owner of that plan disappears. Weak callbacks do not own the compiler/cache. |
| Candidate lists and in-progress dependencies | Completed plans awaiting selection, parent construction and ownership checks | Existing selection/stack boundaries. Rejection may leave the cache as the only optional owner. |
| Invariant subplan cache | Plans plus context-cloning components and registration identity owners | Compiler release. These remain strong even when activation reuse is weak. |
| Managed adapter sources/memo | Original and adapted executable plans; collection failure/cleanup semantics | Compiler release, followed by selected runtime owners. No adapter becomes weak through this change. |
| Selected roots, provider targets, architecture roots and warmups | Selected executable closures | Runtime/analysis lifetime, inherited runtime owner lifetime, or explicit warmup owner. A live selected plan cannot be recreated by cache eviction. |
| Detached callbacks and inspection views | Public components/snapshots and captured evidence, not activation-cache entries | Existing caller ownership; run inspection views expire under task 11. No callback snapshot is invalidated here. |

## Eligibility and fallback

Only exact `_TransientRegistrationStep`, `_PerResolutionRegistrationStep`,
`_ScopedRegistrationStep` and `_SingletonRegistrationStep` carriers without
pre-configurations or decorators are traversed. Every dependency must recursively
meet the same rule or be an exact `_ValueStep` whose value has exact type
`NoneType`, `bool`, `int`, `float`, `complex`, `str` or `bytes`. Empty registration
closures qualify. Every other form stays strongly owned, including containers of
scalars and all scalar subclasses. Application object contents are never read.

All type whitelist checks use `is`. Equality-based tuple/set membership is not an
exact-type check: custom metaclasses can override equality/hash. The task 06 probe
used that unsafe spelling; task 13's initial reproduction was stopped and its
incomplete measurement log is explicitly superseded.

Eligibility walks completed immutable library carriers with a per-call `seen` set;
there is no persistent eligibility memo, no extra field on every execution step,
no global cache and no added resolution traversal. This avoids a second ownership
system, weak-key hashing, stale identity memo entries and graph-retaining memo
values. The separate CPU profile quantifies the repeated walk cost.

A single native dictionary holds either strong steps or un-hashed weak references.
Strong-fallback lookup/insertion retains the original native dictionary operations.
Weak-removal callbacks accept only library-known key leaves. Requested-type keys
must recursively use `object`, `typevar` or `generic` identity branches with exact
tuple/string/integer shapes. Every `literal`, `sequence` or unknown branch stays
strong even when its current leaves look inert. This gate examines the captured
library key, not the application type's attributes. No application hash/equality
is used to infer eligibility.

This extra grammar gate is necessary: a public `Literal[Scalar("token")]` can
include a string subclass whose type's module label is an application string
subclass. A rejecting callback can change that label to an exact string. Without
the grammar gate, a later weak entry's removal compares against the earlier
colliding strong key and calls application equality after rejection. A derived
boolean is False with strong ownership, True in that superseded candidate, and
False with the corrected gate.

For the remaining mixed dictionary, keys from different registration/layer
identities differ before application leaves. Within a registration, dependency
names are the fixed registration dependency-mapping keys, reused by identity.
They cannot switch from fallback to weak eligibility. Metadata-based requested
type branches differ from admitted identity branches at exact library tag strings
before reaching application leaves. Weak removal therefore cannot encounter an
application equality method through a colliding strong entry.

## Key identity and metadata

The existing template key includes registration and layer identities, the closed
requested-type key, exact execution class, owner token, cleanup descriptor,
synchrony and ordered `(dependency-name, dependency-step identity)` pairs. It is
not changed by this task. While a weak value is alive, its dependencies strongly
own every dependency identity in the key; its registration and source contract are
strong fields. The compiler also owns registrations/specializations, layers and
component metadata independently. When the plan dies, its stale key is removed;
a recycled dependency address cannot return a different live plan.

Removal checks that the stored weak reference is still the callback's own entry
before deleting it. Replaced entries therefore survive delayed old callbacks.
The callback holds only a weak cache reference, avoiding an entry/callback/cache
cycle. If the cache already died, removal does nothing. Ordinary failure cleanup
releases the compiler and cache; traceback and caller-held builders remain ordinary
independent owners and are not erased.

## Attribution, reuse and lifetimes

Cache misses do not skip or replay derivation, selection, decorator, configuration
or template callbacks. Insertion follows complete compilation and validation.
Rebuilding a dead scalar-only step may give its private `component` a later
occurrence; that component is not the application's selected occurrence API.
Root/candidate plans retain their own contextual components. Unobserved activation
uses registration IDs and explicit owner tokens/cleanup descriptors, not the
step's component occurrence. Observed execution binds the current selected
occurrence and its dependency edges. Inherited steps stay strongly owned by the
ancestor runtime and continue to use ancestor attribution.

The regression deliberately disables invariant reuse with a rejecting decorator,
rejects the first candidate, then selects an equal activation-cache key. Strong
control hits; weak candidate misses. Callback order, activation/finalization,
profiling paths/counts and lifetime behavior agree in run and analysis for
transient, per-resolution, scoped and singleton lifetimes. Constructors remain
inactive throughout compilation. Overlay tests preserve inherited singleton and
opaque-value ownership.

## Alternatives considered

- Broad weak values are rejected: opaque derived values and map keys change later
  callback results when released after rejection.
- Explicit phase-end clearing is too late for the primary compilation peak. Early
  clearing requires consumer/liveness analysis owned by task 17 and still cannot
  drop opaque values with observable destructors/weakrefs.
- Lightweight cached descriptions require dependency identity guards and enough
  activation/attribution metadata to reconstruct plans. They retain many of the
  same keys and add a second executable representation. The scalar-only candidate
  already releases optional closures without reconstruction or callback replay.
- Eligibility memoization might reduce repeated scans but adds per-step identities,
  weak callbacks and memory. It is not adopted without evidence that its cost is
  justified. No bonus slots optimization is bundled with this task.

## Counting cache work

The existing compilation profiler label `unique activation templates` records
cache admissions/generations. With optional entries evicted, an equal key may be
admitted again; this is not a count of structural uniqueness or simultaneously
live plans. `reused activation templates` still counts live cache hits. The
separate census records constructor calls, peak-live carriers, cache admissions,
cache peak-live entries and entries at compiler release independently. None of
these populations is summed into a byte estimate.
