# Task 15 — sidecar indexes and relationship tables

Audited against the task 14 accepted source captured in `evidence/15/before-source.json`.
The two proposals have independent decisions; topology storage is not changed by
the sidecar candidate.

## Index owners and readers

`_Compiler.origins` and `_Compiler.decorator_explanations` are the only replaced
maps. Compiler writes assign captured values to graph-local occurrence integers.
Origins have 88,558 entries but only 45 distinct borrowed origin objects in the
eight-route fixture; compressing the references does not save those objects again.
Decorator sidecars have 56,522 occurrence-specific references. Task 12 fact sharing,
task 13 cache ownership and task 14 draft sharing remain unchanged.

The compiler publishes mapping proxies into `_PlanSet`, `_OccurrenceLayers` and
`CompiledGraph`. Proxies for occurrence origins and occurrence layers share the
same backing carrier. Inherited `_GraphExplanationSidecars` remain keyed by the
actual graph, so equal integer IDs in different graphs never share a namespace.
Cloning/remapping uses `.get` and integer writes. Selection census uses integer
membership/indexing; explanations, failure provenance and manifest production use
indexed reads. These operations do not promote compact backing.

The exact-dict branches in `_release_execution_composition` and
`_retain_runtime_graph` traverse only their explicitly seeded executable roots,
provider roots, warmup roots and architecture roots, then fields of known execution
carriers. Neither traverses `_PlanSet` or graph sidecars themselves. They never
encounter these new carriers, and need no broader Mapping traversal. Broadening
those branches would risk walking arbitrary application mappings. Scalar activation
eligibility follows only exact library steps and their dependencies; it likewise
never traverses origins/decorator indexes. Observation preparation binds executable
attribution from the supported graph before run reduction, and resolution uses
already-prepared descriptors. No new resolution traversal is introduced.

Successful/failed run lifetime normalization replaces the graph's mapping fields
and plan sidecars under the existing task 11 ownership contract. It does not mutate
caller-held proxies, copies or extracted facts. Caller-held live proxy views may
keep their original backing alive and retain their established contents. Analysis,
failed analysis and parent-overlay graphs retain captured sidecars as before.
Foreign errors/ancestor graphs are not modified. No callback is replayed.

## Native adapter boundary

The private `_CompactIndex` borrows original integer key and value references.
Exact nonnegative integer keys can use a bounded value array plus an insertion-order
key list; a native sparse map handles outliers. Negative, huge, gapped and late-dense
maps can remain native. The carrier starts native with 72 bytes overhead. Density
is reconsidered only at 128, 256, 512, 1024, 2048 and 4096 entries. A conversion
requires a maximum below twice the entry count and below `2**20`; subsequent array
growth has the same bound. Sparse overflow above `max(32, entries // 8)` promotes
permanently. There is at most one conversion each way, with overlap only during
conversion. Tiny/sparse maps allocate no array or order list.

General methods delegate to one permanently locked native backing: iteration,
reversed iteration, views, deletion, copy, equality, updates, unions, clear,
setdefault and pop/popitem. Native receiver methods preserve stored hashes. Foreign
keys lock native backing **before** hashing/equality, including lookups while the
map is still small: reentrant application callbacks cannot change the backing of
an operation already in progress. Raw/caller-held views never detach on clear or
later growth. Exact carrier checks use identity, never application `__class__` or
metaclass equality. Native dunders have positional-only signatures and directly
delegate to native dunders, preserving `NotImplemented`. `update(self=...)` still
inserts a key named `self`.

The historical corrected task 09 class did not cover those three boundaries:
`isinstance` invoked hostile `__class__`, Python dunders accepted keyword keys,
and foreign hashing during eligible fallback could reentrantly compact and lose
an outer write. All are corrected in this candidate; old evidence stays unchanged.

This is not general dictionary substitutability. Constructor/fromkeys, repr,
pickle, arbitrary subclass extension, dynamic attributes and carrier-specific
unsupported-operator type names are outside the private adapter contract. In
particular, `dict(raw_carrier)` / `other_dict.update(raw_carrier)` use Python's
generic Mapping path and may rehash foreign keys; an actual dict source has a
native fast path. No production reader consumes these raw sidecars that way.
Existing public proxy-to-dict paths are already generic Mapping paths and retain
that behavior. Adapter-receiver `.copy`, `.update`, equality and unions delegate
to native dictionaries and are covered by the differential checks. The private
missing sentinel is never a legal stored origin/explanation value.

General raw inspection can forfeit memory savings and temporarily overlap compact
and native storage. Normal explanation/census/manifest inspection is separately
checked for promotion. These maps are implementation details, not a new public
origin-map API or user-selectable build policy.

## Experimental codec

The parked source-coupled codec memoizes the carrier behind a proxy. Compact rows
are encoded directly through ordered raw items; native fallback/promoted carriers
use native dictionary rows. Decoding preserves shared backing through memoization,
uses the same bounded insertion policy and rejects noninteger/duplicate/malformed
compact rows. Schema 8 separates this representation from existing schema 7 files;
no migration or production persistence API is introduced. Only trusted local
experimental files are regenerated in `.cache/graph-memory-task15`. Early task
artifact evidence is not overwritten.

## Relationship census and mutation contract

The three fields `dependency_ids`, `decorator_ids`, `pre_configuration_ids` are
immutable tuples on each draft/record. Empty tuples already share one object.
Dependency tuples are replaced after candidate selection and cloning; resolution
request dependencies append through `+=` before completion. Configuration/decorator
tuples are assigned in order after compilation; decorators may deliberately reverse
activation order. Projection/view remapping makes tuples with context-specific
occurrences. Detached snapshots and freeze borrow completed immutable tuples;
undecorated snapshots replace decorator tuples with empty tuples. Scalar parent,
owner and decorated IDs stay occurrence-local.

Readers include public Component relationship views, ancestry/filter walks,
mandatory lifetime/ownership checks, retention closure, cloning/remapping,
explanations/manifests, warmups, profiling attribution and the experimental codec.
A shared buffer would need graph-qualified ownership, stable snapshots during later
append/update, exact ordering, sparse/large-ID fallback and no new traversal on
resolution. Flattening IDs or merging contexts is not authorized.

The separate intrusive census counts objects by identity across all three fields,
then exact tuple contents. Integer referents are borrowed and listed separately,
never added as another hypothetical saving. Timing/traced memory runs do not
include this census instrumentation.

| Population | Nonempty unique tuples | Unique contents | Tuple shallow bytes | Intern-table bytes with zero hits |
| --- | ---: | ---: | ---: | ---: |
| Eight-route primary | 44,996 | 44,996 | 2,653,968 | 2,621,528 |
| Eight-route retained run | 4,788 | 4,788 | 301,520 | 147,544 |
| Two-route analysis | 1,405 | 1,405 | 87,504 | 73,808 |

There is **zero** recoverable duplicate-tuple storage. Of 35,445 contiguous primary
sequences, 28,764 have length one and 6,681 length two; no longer sequence qualifies.
Even counting only range object headers gives at most 337,008 bytes saved before
new stop integers, fallback dispatch or public-view materialization. Retained run's
analogous upper bound is 36,064 bytes. A buffer of 64-bit references plus raw
64-bit offset/length pairs has an optimistic primary floor of 1,214,048 bytes
before Python row carriers, graph ownership, indexing, spare capacity, conversion
overlap, snapshots and arbitrary-integer fallback. This arithmetic is not a
measured compiler memory improvement. It does not justify replacing all those
readers and mutation/snapshot paths in this task.
