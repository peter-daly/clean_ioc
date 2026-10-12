# Task 14 — mutable draft definition inventory

This inventory covers the current accepted tasks 10–13 source and the scoped
shared-draft-definition candidate. No indexes, topology, activation eligibility,
callback graph copying, or occurrence lifetimes are changed.

## Fields and mutation paths

Eleven definition fields move behind an immutable `_ComponentDefinition`:
`service_type`, `implementation`, `implementation_type`, `lifespan`, `name`,
`tags`, `build_args`, `kind`, `activation`, `boundary`, and
`declared_service_type`. The shared key uses **identity of every referent,
including the exact tags tuple**. It never evaluates application equality,
hashing, repr, or type whitelist membership.

Registration ID and occurrence ID stay on each draft. So do async/cleanup flags,
cache and cleanup owner kinds, owner occurrence ID and reason, provider mode,
position, argument, parent/dependency/decorator/decorated/pre-configuration links.
No topology or registration/ownership identity is inferred from a definition.
Draft generic mapping remains computed as before; frozen records retain their
independent lazy `_generic_mapping` slots. No generic cache moves into definitions.

All construction goes through `_ComponentDraft.__init__`. `_Compiler._draft`
supplies its graph's pool to look up a definition before constructing one. The
three small standalone source/registration view construction paths still call
`graph.add`, which interns their just-created definitions. Construction passes
aliases, specialized service contracts, build arguments, implementation evidence
and origin boundary explicitly as before.

Every assignment to a definition field is a property setter replacing only that
draft's immutable definition. Assigning the same referent is a no-op. Assigning
a new referent makes or reuses a definition, without changing other occurrences.
The source mutation audit, including destructuring assignments, found:

| Function/path | Definition writes | Other occurrence writes |
| --- | --- | --- |
| `_compiled_boundary_component` | Service/name/tags from source, then requested name/tags/public alias | Context stays existing |
| `_Compiler._compile_source_core` | Requested source service/name/tags; enriched implementation type | Root argument reset |
| `_Compiler._compile_candidates`, boundary visibility | Source service/name/tags before definition-side eligibility; public service/name/tags restored in `finally` | Temporary parent reset in `finally` |
| Both preference evaluation branches | Service/name/tags from registration preview; previous exact referents restored in `finally` | Previous parent restored |
| `_Compiler._compile_registration`, cached-root rebinding | Requested service/name/tags | Existing selected contextual occurrence retained |
| `_Compiler._clone_component_tree` | Definition fields copied by `_draft`, then boundary copied | All ownership and relationships remain occurrence-local |
| Frozen decorator position preview | Existing `replace(record, _definition=replace(...))` | Existing frozen-record copy; no draft/pool mutation |

No production draft assignments target implementation, lifespan, build arguments,
kind, activation or declared-service spelling after construction. They nonetheless
have the same safe setter path, and each of all eleven setters has an independent
mutation/restoration test. Registration/dependency normalization writes in legacy
and generic preparation target separate registration objects and are unchanged.

## Exact tag identity is a callback obligation

The first candidate incorrectly reused final-freeze ordered-Tag normalization in
live drafts. Two registrations with distinct `(same_tag,)` tuples then gave a
`when` callback the same tags tuple and changed selection in run and analysis.
That candidate and its interrupted timing log are explicitly superseded.

The corrected live pool uses `id(tags)`. Callbacks, setters, restoration and
individual detached snapshots retain the exact captured tuple. Only final graph
freeze uses the established task 02 key of ordered Tag referents, preserving the
existing published graph contract and definition count. Neither the original
freeze contract nor equal tag contents authorizes changing a live callback's
object identities.

Registration metadata already captures tags as a tuple. `_draft`'s `tuple(tags)`
therefore reuses that tuple across occurrences, including cloned source tuples.
The separate tagged eight-route screen adds one shared Tag to each direct
registration using distinct declaration tuples. Of 88,558 primary drafts,
29,972 have nonempty tags, with 28 exact tuples / two ordered patterns; the live
pool still has 116 definitions. This does not establish behavior for arbitrary
higher-diversity inputs; their separate control is required.

## Pool and referent lifetime

Each graph owns a `_DraftDefinitionPool`, containing a standard
`WeakValueDictionary`. Keys are tuples of eleven built-in integer identities.
Values are weak references to immutable definitions. Every live definition owns
all referents whose identities occur in its key. Its weak removal callback
removes the integer-only key before recycled identities could return a different
live value. Neither weak values nor keys invoke application hash/equality.

Drafts own one definition and their pool, but the pool does not own drafts,
graphs, or definitions strongly. Definitions never reference a pool or graph.
Replacing a field releases the old definition immediately when no other draft,
record or detached snapshot legitimately owns it. An overwritten opaque value is
not kept alive merely by the index. Escaped graphs may retain the weak index but
not abandoned facts. Ordinary exception traceback owners remain unchanged.

Final freeze pops drafts as before and reuses their immutable definitions in
records, with a temporary strong final-normalization dictionary. The graph's
weak index and the final-normalization keys are explicitly cleared at completion.
Detached records/snapshots retain definitions without either index. Graph/record
retention and run expiration remain exactly the task 10/11 policies. There is no
new runtime graph traversal or transient-instance sharing.

## Introspection, snapshots and artifact adapter

The private draft remains a slotted dataclass, now with `_definition` and
`_definitions` instead of eleven stored metadata fields. Its explicit constructor
accepts existing positional/keyword definition arguments and the stored fields
used by `dataclasses.replace`; replacement metadata overrides remain supported.
Private `dataclasses.fields` intentionally exposes the new representation.
The existing freeze-capacity test now flattens fields from the definition while
checking every original occurrence/definition fact and excluding only the pool.
Production dataclass walkers traverse execution carriers, never require the old
draft field list. The benchmark graph census examines frozen records; intrusive
new draft census reads the private definition explicitly.

Public Component properties and `_ComponentViewRecord.__getattr__` still read the
same names. Draft `freeze()` used by detached snapshot paths reuses the immutable
definition while copying all occurrence fields into a new record. It does not
normalize tag tuple identity; later draft writes replace the definition and cannot
mutate the snapshot. Context remapping and generic cache reset remain unchanged.
This changes definition sharing, not callback graph/record copy counts.

The parked artifact codec never serializes drafts. It enumerates graph slots, so
its adapter explicitly excludes `_definitions` and creates an empty local pool
when loading a graph. The serialized schema and payload fields remain unchanged;
no loading feature or precompilation capability is promoted.
