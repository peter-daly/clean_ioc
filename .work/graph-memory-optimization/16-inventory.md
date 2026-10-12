# Task 16 — callback snapshot copying and ownership

This inventory starts from the exact accepted task 15 source. Tasks 10–15 remain
in force. Only `_ComponentDraft.freeze` and `_undecorated_component_view` change;
source compilation, preview dictionaries and callback lifetimes do not.

## Snapshot creation and escape paths

| Path | Required state and publication | Owners and last consumer |
| --- | --- | --- |
| Registration template source filter / lazy inspection | Definition-side identity, closed source type, metadata and lazily compiled relationships. `finish_inspection()` completes/closes inspection before the source is retained. | Expansion selections and blueprint own completed Components; callbacks may independently save them. Already requested relationships remain available; unrequested lazy graph properties still reject access after the filter closes. No earlier release here. |
| Decorator template source / `_Compiler._compile_source_core` | Disposable compiler builds the exact source without decorators, enriches definition-side name/tags/type and freezes its graph. Inherited singleton source views preserve parent runtime context. | Source selections, template expansion, caller-held filters and factories. The disposable execution steps must never become runtime plans. No copying or lifetime change here. |
| Generated target / `_undecorated_component_view` | Walk the connected occurrence graph through parent, dependencies, pre-configurations, decorated and owner links. Preserve all occurrence IDs, generic contracts, boundaries, ownership and ancestor facts; erase attached decorator IDs everywhere. Unrelated roots and hidden decorator-only subgraphs stay excluded. | `_compile_decorators` reuses one target snapshot for that occurrence's generated predicates. User callbacks can retain it indefinitely. Each snapshot owns a fresh dictionary and detached records. |
| Frozen target records | Existing record copied even when decorator IDs are already empty. Existing populated generic map is inherited by `replace`; empty cache slots remain independently populated later. | Original frozen graph and each snapshot own separate records, sharing immutable definitions and captured referents. No new back reference, memo or history chain. |
| Mutable target drafts | Previously `draft.freeze()` then `replace(..., decorator_ids=())`: two records for one published record. Now `draft.freeze(include_decorators=False)` creates the single detached record directly. | The draft and new record independently own their definition. Later draft changes replace definitions or occurrence fields without changing the snapshot. No draft is published in a snapshot. |
| Provider/context projections / `_ComponentViewRecord.freeze` | Remap occurrence/parent/owner/dependency/pre-configuration/decorated IDs, preserve contextual ownership reason and explicitly reset the generic cache. | Existing projection freeze and following undecorated copy are unchanged. A projected record has no source graph back reference once frozen. |
| Dynamic position preview | Copy the target snapshot's dictionary, share its existing detached records, add one `-1` preview record and a replaced definition containing decorator metadata. Preview retains its historical parent/owner/argument fields and points `decorated_id` at the actual core. | Position callback can retain both preview and target Component. Dictionary sharing here is shallow, with no graph parent link; all shared records were already detached. Current cache-sharing semantics between preview and target stay unchanged. |
| Final graph freezing / runtime reduction | Freeze retained executable closure, applying task 14's existing ordered-Tag final normalization only here. | Runtime owns retained graph; analysis additionally retains inspection/composition. Default `include_decorators=True` preserves all pipelines. No task 17 lifetime pruning. |

All source snapshot callbacks run at their original positions. Exceptions keep the
original invocation results; no evidence recovery invokes callbacks again. Failed
builders remain retryable. Public analysis may perform its existing independent
root retries; tests preserve its supported behavior rather than requiring equal
failure counts across modes. Public run inspection graph expiration under task 11
is separate from detached Component snapshots, which remain caller-owned.

## Immutable definitions and mutable caches

Task 14 already shares `_ComponentDefinition` among drafts and snapshots by exact
referent identity, including the exact live tags tuple. Definitions contain no
graph, pool, draft or preceding snapshot reference. The graph-local pool is weak;
record creation keeps its existing owners and does not create another index.
Overwritten facts are released when their actual last draft/record owner goes
away. Existing hostile equality/hash and weak-owner regressions remain applicable.

Records are frozen dataclasses but contain a lazy `_generic_mapping` cache.
`dataclasses.replace` preserves an already-populated cache because this field is
`init=True`. An unpopulated source yields new empty cache slots in every snapshot.
The installed typetoolbox metaclass separately caches maps with weak mapped-type
keys and strong map values, so distinct empty records do not guarantee distinct
public map identities. The regression checks cache state, inherited populated
references and TypeVar bindings without making that false identity assumption.
The draft fast path always makes a new record with an empty slot, exactly as the
previous unpublished `freeze` plus `replace` sequence did.

Sharing frozen records wholesale would couple later cache population and ownership.
It is unnecessary for this change. Persistent/copy-on-write record dictionaries
would also need mutation/version bookkeeping for connected ancestry and preview
contexts, plus proof against chains retaining obsolete graphs. No such machinery
is adopted. This does not revive task 04 subtree sharing, merge occurrences, alter
transient activation sharing, or add task 07 slots changes.

## Measurement boundaries

The unchanged task 12 shared harness supplies uninstrumented normal time/RSS and
separate traced whole-build retained/peak bytes. Verified task 15 AFTER supplies
its baseline. Runtime source, fixture and harness stay frozen during comparison.

The separate constructor census adds destructors/counters to library classes and
tracks target snapshot graph identities without owning their objects. It reports
created, maximum live and retained records/definitions/drafts/graphs, plus target
snapshot counts. It is excluded from all time/byte claims. Snapshot counts identify
only generated-target snapshots, while all-graph counts also include source,
primary and position-preview graphs; those populations are not interchangeable.

A separate phase observer resets only its own segment high-water mark and reports
live/preceding-segment peak bytes at named compiler boundaries. Segment peaks are
never summed or substituted for the unmodified whole-build peak.

The bounded escaped-view fixture saves 64 target callbacks, 64 position previews
and their target views, plus one source view. Before/after use the same source
loader and imports, with three fresh normal and three separate traced processes
per public mode/policy. It measures build, first/repeated inspection, runtime
release while snapshots remain, and final snapshot release. Generic inspection
happens late; callbacks do not replay. This is deliberately separate from the
large fixture, which holds neither caller snapshots nor its builder.
