# Task 08 — index contracts and consumers

Investigated against `7b9a841`, 2026-10-09. Production sources match the Task 07
`d51b6f5` baseline. `benchmarks/graph_artifact.py:27` is **schema 7**; Task 07's
schema-5 prose is stale. This inventory concerns only the compiler's occurrence
origin and decorator explanation indexes; registration/slot origins, occurrence
records, all caches and execution layouts are unchanged.

## Source-backed ownership and use

| Stage | Writers/readers and observable obligation |
| --- | --- |
| Compiler construction | `container.py:5446,5454` allocate separate indexes per compiler. Occurrence IDs are local namespaces, never global cache keys. |
| Origins | `7194` captures the exact supplied/synthetic `DefinitionOrigin` per occurrence; `9890` replaces preconfiguration provenance. No origin deduplication is introduced: 45 shared objects already cover the rich eight-route fixture. |
| Decorator explanations | `10427` captures selection patterns at the original callback point; `8908–8910` captures clone-specific remapping. Out-of-order insertion must stay observable. Values are distinct remapping carriers, with shared immutable patterns beneath them. |
| Compilation readers | `.get` at `5475,5506,5543,5950,7454,8263,9060,9302,9325,9488,9536,9547,9572–9573,9609,9640,9758` supplies issue, budget, callback, preparation and rule provenance. Missing keys retain their original defaults. |
| Provider views and cloning | `6524,6555,8841–8845,8895`; inherited `_GraphExplanationSidecars` at `4911,5008–5009` retain the source graph's exact origins and decorators. Each target compiler owns its new index. No namespace merging, occurrence renumbering or definition-based origin inference. |
| Plan publication | `6475–6476` wrap both backing objects in live `MappingProxyType`; `6484` creates a second proxy of origins for `_OccurrenceLayers`. Wrappers must share one backing, rather than independently materialize dictionaries. |
| Layer adapter | `_OccurrenceLayers` (`4840–4856`) translates a negative provider-view ID to its physical source before reading origin.layer; its iterator exposes the origin mapping's order. Negative IDs are not an invitation to allocate an enormous dense array. |
| Graph and failure evidence | `_finalize_plan` (`11189`), `CompiledGraph` construction (`11444,11453`), validation runners, and error publication (`11508`) retain the same captured facts for full/reduced failed builds. `_component_evidence` (`tooling.py:2315`) first reads occurrence IDs, then their graph-view source; `explain` (`2261,2282`) and `explain_decorators` (`2390`) use exact occurrence evidence. |
| Successful reduction | `_reduce_explanation_metadata` (`container.py:5218–5220`) replaces these sidecars with empty mappings. Thus reduced-runtime retention is not an additional index saving. Caller-held callback Components and failed graphs have distinct lifetimes, protected by existing tests and Task 06's lifetime counterexamples. |
| Artifact export | `_Writer.encode` (`graph_artifact.py:196–203`) currently insists on dictionary backing for mapping proxies. `_Writer.ref` memoizes **backing identity**, then emits postorder rows; replacing this with independent proxy-item serialization would duplicate loaded indexes. Unsupported values fail before temporary-file publication (`dump_graph`). |
| Artifact load | `_Reader.decode` (`239–280`) reconstructs dictionary rows and shared proxies through object references; `load_graph` checks schema, exact Python version and source hash before returning a container. Constructors and compiler callbacks are not required to recreate captured evidence. |

## Compatibility boundary used in the executable candidate

The compiler's own writers use exact integer occurrence IDs and only insert or
replace values; no production deletion of either index was found. The stored
values are `DefinitionOrigin` and `_DecoratorExplanation`, not arbitrary
application objects. The candidate keeps this internal append/update path compact.
It does **not** silently narrow the mappings accepted by read-only wrappers.

Any non-exact-int lookup, membership check or write promotes the same backing
object to a real dictionary, preserving `1`, `True`, `1.0`, fractions, int subclasses,
custom equal/hash keys, original inserted key identity, collisions, unhashable-key
errors and normal dictionary behavior. Deletion also promotes. Public iteration
(including keys/items/values view iteration and reverse iteration) promotes before
creating the iterator; dictionary iterators then supply native mutation behavior.
Updating existing values does not reorder keys; deletion/reinsertion and `popitem`
use dictionary semantics. Views remain live; `.copy()` remains a snapshot. Equality,
read-only proxy unions and missing/default behavior are exercised differentially.
The private missing sentinel is not a legal typed index value.

Promotion is permanent for that backing object. Existing proxies stay live and
share its state. Promoted indexes release both dense and order lists and the sparse
fallback; the replacement dictionary retains ordinary CPython deletion capacity.
This conservative adapter makes slow/rare operations correct at a measured memory
cost. It is a private typed-index experiment, not a general substitute for every
`dict` method, representation string, dynamic attribute or pickle interface.

Before promotion, exact nonnegative IDs use reference arrays only when the new
length is below both `4 * entry_count` (minimum allowance 64) and a logical length of `2**20`. Python list spare capacity is included in shallow storage accounting.
Other IDs use the sparse dictionary with a single insertion-order list shared by
all entries. Reverse/gapped/negative/huge-ID screens account for its overhead; this
is bounded, not a promise that every sparse workload benefits. Each compiler/load
owns separate storage. Keys and values are borrowed once, not charged again as
new origin/decorator objects.

The artifact adapter explicitly accepts only `dict` or the candidate's exact backing
class behind a proxy. It serializes compact entries directly, without asking for a
public iterator or constructing a dictionary. Compact rows decode directly into
bounded storage; duplicate/noninteger keys and malformed pairs are rejected. Memoized
backing references preserve all wrappers' sharing. Promoted candidate backings are
encoded as dictionary rows. Probe schema **8008** and source/probe fingerprints
isolate regenerated experimental artifacts from schema 7; there is no migration or
production persistence proposal.

## Additional generic-operation counterexamples

`08-hash-counterexamples.json` records five failures missed by the ordinary
value/order screen. A stateful custom key can permit one hash call for insertion
or removal, or forbid rehashing an already stored key. Native `dict.setdefault`
and `dict.pop` succeed with one call, while inherited `MutableMapping` helpers
perform get-then-write/delete and raise on a second call. Native dictionary copy,
self-equality and dictionary-to-dictionary update reuse stored hashes; the measured
candidate's copy and Mapping equality/update helpers rebuild or retrieve keys and
raise instead. This matters even after backing promotion: the outer methods still
come from the ABC.

These operations are not used by the compiler's integer-only workload, and public
proxies do not expose mutable helpers. Nevertheless the investigation explicitly
covers the broader mapping contract; the measured candidate must **not** be described
as a general drop-in dictionary. The counterexamples are retained rather than
changing the expected result or excluding the keys after seeing failures.

`08-hash-counterexamples.py` also contains an **unmeasured**, slotted subclass
that delegates `setdefault`, `pop`, `copy`, equality and update directly to its
promoted native dictionary. It matches all five outcomes and hash-call counts in
`08-hash-counterexamples-with-refinement.json`. It is a bounded feasibility proof,
not installed in any compiler, codec or repeated measurement. The final
implementation boundary needs either this complete native-delegation adapter or an
explicitly reviewed integer-only internal API with compatible read-only adapters.
A new integrated semantic/artifact/performance comparison is required before calling
that refinement ready.

The extended screen also finds a **read-only proxy equality** counterexample
without inserting any foreign key into the index: a proxy containing integer key
`4000` is compared with a dictionary whose custom key is equivalent to that integer.
Native dictionary/proxy equality uses the other dictionary's stored hash and succeeds.
The measured Mapping equality rebuilds the other dictionary and raises while hashing
its key again. Thus defining the compiler's writes as integer-only does not by itself
resolve all exposed read-only behavior. Native equality delegation is required at
the adapter boundary. The separate native-delegation subclass passes this sixth
counterexample too.


The raw origin/decorator maps are held in **private graph/plan fields**. Public
explanations, manifests, traversal and provider attribution pass the normal contract
checks. The proxy-equality counterexample concerns the requested observable Mapping
behavior of those read-only wrappers; it is not a claim that a new documented public
origin-map API exists. A proposed integer-only internal boundary must make that
scope explicit and preserve the adapter behavior accepted in review.
