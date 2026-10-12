# Task 05 retained-data inventory and ownership boundary

Source: task-04 rollback at `2679234`, followed by the task-05 implementation.
Counts and shallow sizes are captured outside measured intervals by
`graph_memory_evidence.census()`; total retained Python allocation and RSS are
measured separately. A dictionary's shallow size excludes its keys and referents.
The result report links the repeated observations; do not add overlapping sizes.

## Plan fields and their readers

| `_PlanSet` field/category | Actual readers / purpose | Reduced retention |
| --- | --- | --- |
| `graph`, component records, definitions, `_views` | `_select_root`, `_select_roots`, `has_component`, `_provider_selection_component`, application runtime filters, `ResolutionContext`, managed target metadata and overlay tree cloning | Required root/execution relationship closure; all fields on retained Components survive |
| `roots`, `default_roots`, `default_root_groups` | Ordinary and collection sync/async selection; default fast paths; named and fallback roots | Keep exact roots, order, fallback bits and shared steps |
| `provider_roots`, `managed_provider_roots` | Public and acquisition-specific deferred selection; provider/map targets | Keep; include their Components and steps in closure |
| `warmup_steps`, `warmup_infos`, `warmup_fingerprint` | `warmup`, `warmup_async`, their result reporting | Keep named execution roots and scalar descriptors; fingerprint is computed before release |
| `_blueprint` | `_compilation_snapshot`, future overlay declarations, visibility preparation and template expansion | Only when `allow_scope_builders=True`; retain layers/boundaries, release completed `template_selections` and `generated_decorators` |
| `architecture_roots` | Full inspection; `_anchored_singletons` and `_anchored_pre_configurations` for overlays, including private boundaries | Only with scope builders; without them private architecture-only execution and records are removable |
| `build_args` | Public build settings and Component filter facts; specialization/overlay inputs | Keep immutable inputs; caller-owned values can themselves retain arbitrary objects |
| `slots` | `has_scope_slot`, `provide`, `_find_provision`, missing-provision errors | Keep exact canonical keys and names |
| `ensured_import_modules` | Public import-discovery receipts | Keep the small existing public descriptor tuple |
| `diagnostics`, `explain_metadata`, reachability checked/offset flags | Requested mode and stored build-report semantics | Keep scalar state; diagnostics never restore successful inspection |
| `build_report` | Existing captured build findings, text/JSON/SARIF/assertion | Keep scalar issues/root count; remove graph, explanation and failure-evidence context |
| `compiler_issues` | Final validation's temporary findings, duplicated by successful report | Drop |
| `compiled_graph` | Traversal, rendering, explanations, manifests, census, graph analysis, validation rules, instrumentation preparation | Required during final validation/warmup/observation; then expire escaped build views and release roots, all maps, caches and analysis index |
| `root_candidates`, `area_root_candidates` | Entry-point selection, root explanations and census | Build-only after successful validation; drop both indexes and rejected/unused record roots |
| `occurrence_explanations`, `parameter_explanations`, `generic_explanations`, `decorator_explanations` | Explanation readers, build safety rules, cloning captured inspection facts | Drop all successful sidecars, not merely API access |
| `occurrence_origins`, `occurrence_layers` | Failure/source evidence, selected-origin inspection, manifests and full-mode inherited sidecars | Drop successful occurrence indexes; optional composition keeps declaration origins needed by future builds |
| `census_sources`, `census_definitions`, `census_ids` | Diagnostic selection census; compilation's orphan-definition pruning | Drop after compilation's orphan pruning and required validation |
| `fallback_ids` | Full selected-decision explanations; inherited compiler selection classification | Keep only for future scope-builder anchoring; runtime root fallback bits remain regardless |
| `selected_registrations` | Public static registration catalogue | Omit construction in reduced mode and reject its getter |
| `validation_rules` | Later `validation_report()` | Validation-only declarations explicitly reject reduced builds; build-mode rules still run before release |

The captured plan-field census reports each field's type, entry count and shallow
backing storage. Shared dictionaries/objects must not be summed twice. Full-mode
origins, root records and sidecars also share referents with the compiled graph.

## Executable and scope state

Runtime steps need the constructor/factory/instance, activator, selected dependencies,
ordered decorators/pre-configurations, collection members, provider targets,
provider-map key indices, provision keys and declared resolution requests. Lifespan
steps retain registration IDs, service type (including cycle errors), lifetime and
owner token. Cleanup descriptors retain owner category/token; scopes retain their
instance caches, coordinators, provisions, acquired scopes and finalizer stacks.
None of these are merged or reconstructed by metadata reduction.

Fresh registration steps use a five-field `_RuntimeRegistration` carrier in reduced
mode: ID, service type, implementation, activator class and lifespan. A build-local
identity memo preserves shared registration identity. Legacy dependency settings,
parent selection filters, generic compilation caches, names/tags and unused
composition flags are released from the executable carrier; Component definitions
still expose names/tags and generic bindings for runtime filters. Fresh decorator
activations retain the implementation, activator and decorated argument, release
the build definition/`when` callback and parsed dependency settings, and execute
through their already compiled dependency steps. Fresh pre-configurations retain
ID, activation function and continue-on-failure behavior, plus their original state,
owner and selected dependencies. Their build applicability callbacks, arguments,
origin and declaration metadata are released from execution.

Only carriers whose Component belongs to the new primary graph are trimmed.
Inherited ancestor steps and their carriers are not mutated. Steps themselves keep
their identity, including instrumentation's calling-edge attribution; activation
and pre-configuration state retain their identity. Composition retained for enabled
overlays keeps its own original declarations separately. Implementations, actual
argument values and declared runtime request filters may retain application data;
those references are required by their enabled runtime behavior.

## Successful graph reduction

The closure starts from ordinary/default/filtered roots, all ordinary/managed provider
roots, warmup roots and every Component captured by their executable steps. Private
architecture roots additionally survive when future overlays are enabled. An
identity-only walk of library executable dataclasses and built-in containers finds
embedded map/provider/declared-request targets. It does not traverse arbitrary
application objects, call user equality/repr, or evaluate callbacks.

Follow parent, dependencies, decorators, decorated target, pre-configurations and
owner relationships in both directions supplied by those records. Parents lead to
siblings: retaining only forward dependency trees would break supported filters.
Negative provider view IDs retain their physical source and contextual parent,
then their remapped links. Graph-qualified inherited references are left in their
owner graph. Never infer occurrence equivalence from shared executable steps.

Reduced primary compilation validates its read-only Component views over private
build drafts. After all validation, template visibility checks, orphan-definition
pruning and warmup planning succeed, only required drafts are frozen. Failed final
validation freezes the complete graph before publishing evidence. Source inspection,
diagnostic retries and full-mode compilation retain their normal freeze boundary.
All architecture roots survive this first freeze so optional instrumentation can
capture private activation paths from the successful inspection view. After that
capture, final reduction drops architecture-only roots when scope builders are
disabled and expires the inspection view. No pruning, graph walk or compilation
is added to ordinary resolution.

## Callback escape choices

Detaching every callback Component would need a complete connected snapshot to
preserve its existing parents, siblings, descendants and owners. The task-03
forwarding example alone reached 600 extra primary records and two separate source
graphs at two routes; preserving every escape requires tracking/copying graphs and
can eliminate the intended saving. A scalar snapshot would silently change those
relationships. Neither is used for primary graph views.

Instead, reduced mode explicitly permits successful-build invalidation. A Component
keeps its graph and occurrence ID; metadata access to a discarded primary record
raises `RuntimeError` with `explain-metadata-disabled`. Retained records keep their
entire relationship closure. No dangling object reference is introduced and no
per-escape cache or tombstone index survives. Separate existing source snapshots
remain application-owned and valid. A saved build-validation `CompiledGraph`
explicitly expires and releases its captured context and caches; previously created
scalar manifests/reports remain caller-owned snapshots. Ancestors are never expired.
Full mode retains the original escape semantics.

Caller-owned builders, callback views, actual runtime values/functions, full parent
runtimes and profiling reports are separate owners. The memory runner explicitly
records builder/callback ownership and counts all collected graphs in those cases.
The callback-release regression proves a reduced execution carrier no longer keeps
a build-only predicate alive after its caller releases the builder/predicate.

## Capability decisions

`components`, filters, resolution, providers/maps, scopes, provisions, warmups,
build settings and profiling remain enabled. Full graph access, architecture and
validation reports, manifests, census and the selected registration catalogue fail
clearly. Validation-only rules reject the build explicitly. Deferred unreachable
warnings remain unchecked with `check_unreachable=False`, and later validation is
unavailable; eager checks still run when requested. Build matrices still request
full metadata and diagnostics; no reduced matrix API is added. Static class-level
`CompiledGraph.type_ast(type)` is independent of any runtime graph.

A full parent supports either child mode. A reduced parent requires a reduced
child, rejecting the default/full request instead of claiming recovered parent
facts. Ordinary descendants reuse their plan's mode. The private schema-5 artifact
experiment rejects reduced plans before writing; full artifact round trips remain
supported. No task-04 contextual subtree representation is reintroduced.
