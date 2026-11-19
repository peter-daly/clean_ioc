# Task 07 — effective layouts and representation consumers

Baseline `d51b6f569e67891e72e022b35aa5590c1c0fda46`, Python 3.14.4/macOS ARM64.
The complete runtime MRO, per-base slots, dictionary/weakref offsets and primary
live/created census are in `evidence/07-inventory-baseline.json`. Counts use
`gc.get_objects()` after compilation; that observer and the offline draft packing
are **excluded** from normal/traced repeated measurements. No measured observer
reads an instance `__dict__`.

## Execution carriers

`_Step` (`container.py:2656`) has no slots. Every ordinary subclass therefore
inherits its dictionary and weakref support, including frozen slotted dataclasses
`_ValueStep`, `_ProvidedStep`, `_ScopeStep`, `_CollectionStep`, `_ProviderStep`,
`_PerCallStep`, `_RegistrationStep`, and `_ObservedCallSiteStep`. Their derived
managed/context/per-call/provider-map/lifespan classes declare slots but retain
the base layout. Dictionary support is not proof of a materialized dictionary:
the allocation microprobe measures objects without opening that attribute.

`_ObservedRegistrationMixin` (`4513`) and `_ObservedScopedCacheMixin` (`4659`)
independently introduce dictionaries; fixing only `_Step` leaves observed
registration carriers with dictionaries. Both mixins store no instance fields.
Observed registration/provider/context/managed-provider subclasses already slot
`_profile_key`. `_ObservedPreConfiguration` slots all four attribution fields
`_profile_key`, `_caller_key`, `_caller_paths`, `_parent_step_id`; its slotted
compiled parent does not inherit from `_Step`. `_ObservedDecorator` likewise
already has an effective layout. `_ObservedScopeMixin` is dictionary-bearing but
Scope/Container remain separate low-count public runtime objects, outside the
carrier probe; removing their dynamic attribute seams is not recommended here.

The isolated slots probe adds `__slots__ = ('__weakref__',)` to `_Step`, and empty
slots to both registration mixins. It preserves weakref support intentionally.
It does not change dataclass fields, constructors, frozen status, replacement or
execution behavior. Existing `object.__setattr__` mutations during instrumentation
(`13900–14134`) and runtime metadata reduction (`5082`) target declared fields.
Step code contains no dynamic generic/protocol machinery; specialization is on
registration definitions, not these private execution instances. Dataclass
`replace()` remains the copy path in managed adaptation and observation.
Instance monkeypatching of arbitrary private fields is an intentionally narrowed
private seam requiring review, not an established public extension interface.

`_legacy._Registration` (`_legacy.py:1091`) declares 15 slots but inherits its
instance dictionary from public `Registration(Protocol)` (`1078`). Making the
protocol slotted would affect public protocol subclasses; severing nominal
inheritance could affect type consumers and generic tooling. Its definition
population is tiny relative to execution steps. That change is deferred rather
than bundled into the measured carrier proposal. Runtime MRO evidence is in the
microprobe outputs. Existing generic mapping writes use `_generic_mapping`, which
is already a slot; this does not establish that all public subclasses avoid
additional fields.

Supported Python is `>=3.11,<4`; CI covers 3.11–3.14 and experimental 3.15.
Measurements use 3.14.4. Available additional interpreters and validation limits
are recorded in the result; offsets and managed-dictionary allocation are
interpreter-specific and must not be extrapolated arithmetically.

## Mutable drafts

`_ComponentDraft` (`components.py:183`) has 27 fields and effective slots. It
contains 11 fields shared by `_ComponentDefinition` only when frozen. Primary
compilation retains 88,558 drafts, but only 116 identity-distinct definition tuples
in the eight-route fixture. The isolated packing screen creates an identity-keyed
tuple pool; it never hashes or compares application values. Its measured pool
storage includes the dictionary plus both key/value tuples, while draft reference
savings remain an arithmetic ceiling, not a measured build peak reduction.

Source enrichment writes service/name/tags/implementation type (`6226–6234`),
boundary visibility writes service/name/tags (`1647–1658`), preference previews
replace and restore service type (`8023`, `8137`), cache-root rebinding writes
service/name/tags (`8495–8497`), and cloning copies boundary (`8853`). A shared
mutable definition is incompatible: mutation must replace one occurrence's
immutable definition, never mutate facts belonging to peers. The bounded COW
microprobe proves isolated replace-and-restore with reference identity and shows
unused opaque facts remain alive until the pool is cleared; it is
not an integrated compiler implementation. Pool lifetime, dead definition cleanup,
per-occurrence generic mapping, dataclass replacement/introspection compatibility,
temporary constructor tuples and interning costs remain design work. A strong pool
can also prolong overwritten opaque facts; merely discarding keys at compiler
return is insufficient if a pool is owned by a surviving graph. The implementation
needs a release policy at snapshot freeze and successful reduction that leaves
escaped Components valid. More generic
or alias-heavy graphs may have many more definitions than this fixture.

## Origins and decorator indexes

`_Compiler.origins` is allocated at `container.py:5454`, populated per draft at
`7194`, used by issue recording (`5475`), callback and budget witnesses (`5506`,
`5543`, `5950`), provider view and clone provenance (`6524`, `6555`, `8841`), and
updated for preconfiguration origins (`9890`). The plan borrows a mapping proxy
(`6475`); `_OccurrenceLayers` (`4840–4856`) maps provider view IDs to their physical
source before reading it. `CompiledGraph._component_evidence` and manifest/error
paths consume the same captured origins. No callback replay can recover them.
The primary eight-route index has 88,558 contiguous positive keys in increasing
insertion order and **45 unique origin objects**: sharing the values is already
happening. Removing repeated origin objects would claim nonexistent savings.

`decorator_explanations` (`5446`) is written during compile (`10427`) and clone
remapping (`8908–8910`), read by graph explanations (`tooling.py:2390`), build rules,
manifest/census and failed finalization. It has 56,522 entries spanning IDs
1–88,507, inserted out of numeric order, each holding a distinct remapping sidecar.
The backing dictionary costs are 5,242,960 and 2,621,528 bytes respectively; proxy
wrappers do not eliminate them and referents are excluded.

The corrected bounded index probe uses a positive-ID reference list, an insertion-order
key list and a sparse dictionary fallback for negative/large/noninteger keys.
Keys are never renumbered and each compiler keeps its own namespace. Capacity is
bounded by a per-write growth guard. Pruning leaves holes; deletion preserves
remaining order, reinsertion appends. Compiler occurrence-ID lookup and proxy use remain,
but mutable key-list iteration and deletion complexity differ from dictionaries;
concurrent mutation during iteration is not established compatible. Boundary,
overlay, sparse-ID and failed graph evidence require focused validation before
any ready recommendation. A shared-definition provenance representation is
separately deferred: component-definition identity does not encode location,
layer, alias or boundary origin exceptions.

## Cache lookup placement

`_compile_registration` constructs a carrier at `8595` before checking
`_activation_templates` (`8630`). The isolated AST probe calculates the existing
cleanup descriptor and sync flag at their original point, computes exactly the
existing key only on the existing eligible path, and allocates a registration
carrier only on a miss. Selection, derived values, templates, dependencies,
preconfigurations and decorators have already run. Maps/per-call/configured/
decorated steps still always construct. Cache ownership and eligibility stay the
same, including opaque application values and map keys. Hits retain the exact
previous step and its original Component attribution. Profile unique/reused
counts stay on their existing branches. This avoids temporary construction; it
does not release retained cache misses or implement Task 06's weak-cache proposal.

Changed placement makes key computation precede the private generated carrier
constructor; those constructors currently only assign fields. Custom class-level
monkeypatches of these private constructors could observe the avoided calls.
Error ordering for cleanup/sync computation remains, but failures from a patched
carrier constructor or pathological type-key computation need explicit review.

The existing schema-5 artifact writer (`benchmarks/graph_artifact.py:201`)
explicitly requires a mapping proxy backed by a dictionary. The index probe
fails eight full-mode artifact cases on this condition. Reduced artifacts and
ordinary graph behavior are separate checks; the codec is not changed here.
Any index implementation needs an explicit, measured codec/conversion design
before it can be called compatible or ready.

The corrected prototype also misses numeric-equivalent non-int queries such as
`mapping[1.0]` when key `1` is dense. This is recorded by the bounded mapping
screen; it is not advertised as a general drop-in dictionary replacement.
Pool-only tracing counts the 40,832 bytes of newly owned integer key referents
in addition to tuple/dictionary shallow storage, while borrowed facts are counted
once. See `07-pool-accounting.json` and `07-index-accounting-final.json` for
allocation, sparse capacity, conversion and lookup screens.
