# Task 09 — integrated compact-index boundary and fallback

Task 09 builds on [Task 08's reader inventory](08-inventory.md); production
writers/readers, graph-local occurrence IDs and captured values are unchanged.
The isolated loader installs one `CompactIndex` in the compiler and experimental
codec. The same loader reads untransformed baseline bytecode for controls.

## Storage policy

The carrier has five slots and occupies 72 bytes on CPython 3.14 ARM64. It starts
with an ordinary dictionary and null array/order/sparse references. Thus empty,
tiny, negative-only, huge-ID, reverse-inserted and sparse-only maps pay only the
carrier above native dictionary storage. Keys and values are borrowed references.

Density is examined at 128, 256, 512, 1024, 2048 and 4096 entries. A dictionary
converts once if all stored keys are exact nonnegative integers and its maximum
key is below both twice its entry count and `2**20`. Failed checkpoints defer to
the next doubled size; after 4096 the map remains native. The scan/overlap is
bounded to these small checkpoints, not a conversion at graph completion.
Foreign-key writes lock native backing immediately.

Compact insert/update/get retains the original integer key and value identities.
Its single order list preserves insertion order; its value list is bounded by
`min(2 * entries, 2**20)` logically, with Python list spare capacity measured
separately. Outlying keys use a sparse dictionary. If sparse entries exceed
`max(32, entries // 8)`, the carrier permanently promotes to native dictionary
storage and releases all three compact containers. There can be at most one
native-to-compact conversion and one compact-to-native conversion.

## Native adapter

Foreign-key lookup/membership/write and deletion promote the same carrier. Public
iteration, reversed iteration, keys/items/values views, clear, copies, equality,
setdefault, pop/popitem, update and unions delegate directly to a native backing
dictionary. Views permanently lock that dictionary, so later growth and clear
cannot detach a live view. Proxy wrappers continue referring to the same carrier.
Copy produces a native snapshot; equality and dictionary-to-dictionary update
reuse stored native hashes. Operations between carriers unwrap the native
backings, avoiding ABC helper paths. Positional-only get/setdefault/pop match the
native keyword rejection boundary.

These are private typed graph/plan sidecars, not a new public origin-map API or a
complete general-purpose `dict` replacement. The private missing sentinel is not
a legal stored `DefinitionOrigin` or `_DecoratorExplanation`. Repr, pickle,
`dict.fromkeys`, dynamic attributes and carrier-specific unsupported-operator
error message class names are outside this adapter contract. Native method
outcomes, hash/equality callbacks, key/value identity, ordering, live views,
iterators and read-only proxy behavior are inside it.

Promotion on inspection of the raw mappings costs memory and is permanent.
Normal explanations/manifests use indexed reads and do not promote. Constructor,
selection and template callbacks are never replayed to recover evidence.

## Codec

Experimental schema **8009** accepts exactly native dictionary or exact candidate
backing behind mapping proxies. It memoizes the backing carrier identity, encodes
compact rows directly through `raw_items`, and decodes those rows through the
same bounded constructor/insertion policy. Initial, sparse and promoted dictionary
states encode dictionary rows. Shared proxy backing survives either representation.
Duplicate/noninteger keys and malformed compact rows are rejected. Unsupported
backing/value rejection preserves existing publication and removes temporary files.

Prepared original/transformed sources and bytecode hashes are in
[evidence/09-prepared.json](evidence/09-prepared.json). The source-coupled artifacts
remain in `.cache/graph-memory-task09`; no production schema or migration is added.
