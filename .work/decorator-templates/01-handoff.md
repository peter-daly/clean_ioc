# M01 — implementation verification handoff

Status: Implementation verification passed; independent technical review and final handoff remain pending.
Feature delivery is incomplete. No public API or public explanatory documentation is introduced in M01.

Implementation agent: `/root/m01_implementation`, `gpt-6-astra`, high reasoning, fresh explicit handoff.
Code-search agent: `/root/m01_search`, `gpt-6-luna`, low reasoning. Coordinator: `/root`.
Branch: `codex/decorator-templates`. Baseline/search checkpoint: `da20679d89cf0779c8c30365196375901f62e8b5`.
Implementation checkpoint: coordinator to record after committing this gate. No task commits made by implementation agent.
Review identity, acceptance, and checkpoint: pending in `01-review.md`. Documentation comprehension: not applicable;
only internal work-item records changed. No bark-core files, dependencies, environments, or commits changed.
Pre-existing unrelated untracked `.work` files remain untouched.

## API decisions for subsequent milestones

These spellings are settled for implementation, subject to independent M01 review. They are not exported yet.

- `ServiceGroup(name, *, service_type=Contract)` is immutable and compares by object identity. Its declaration stores
  no members. `groups: Iterable[ServiceGroup] = ()` is accepted by direct class/factory/instance registration, structural
  patterns, subclass discovery, and generic-subclass discovery. Consume an iterable once, deduplicate identities,
  validate known contracts transactionally, and store a frozen membership set against each definition ID.
- `DerivedServices(Contract)` is an immutable, stateless automatic target selector, distinct from group membership.
  Both selectors project the **registered service** onto their declared contract; implementation inheritance cannot
  enroll an unrelated service. Neither creates runtime aliases or changes an injected parameter's service key.
- `RegistrationInfo` is the immutable definition view: ID, exact canonical service key, statically known implementation
  type (including closed constructor aliases/generated classes), name and immutable tags.
  `implementation_bindings(base_type)` returns an immutable mapping keyed by the base's actual TypeVars, or `None`
  if no static binding is established. Unresolved bindings retain TypeVar values. A broad factory return annotation
  is not evidence of a concrete backend; no factory is activated to discover it. Preserve known alias specialization
  separately from `Component.implementation_type`, which deliberately normalizes aliases to a class.
- `DecoratorTemplate(services=group_or_derived, decorator_type=..., decorated_arg=None, arguments=None, when=cf.all_components,
  position=0, name=None, tags=())` is immutable, with defensive immutable copies of arguments/tags. The normal callable,
  argument-policy, filter, and decorator-position semantics apply. `when` accepts exactly one target Component.
- `ComponentBuilder.register_decorator_template(*, for_each, template, source_filter=cf.all_components) -> str` declares
  a pure synchronous `Callable[[RegistrationInfo], DecoratorTemplate]`. `for_each` is an exact canonical closed service
  key, not open-generic or pattern enumeration. Closed generic implementations under a nongeneric key are supported.
- `patch_decorator_template(template_id, *, for_each=UNCHANGED, source_filter=UNCHANGED, template=UNCHANGED)` replaces
  supplied fields while preserving ID/order. Replacing the factory replaces its returned options.
  `remove_decorator_template(template_id)` removes/suppresses that identity. Missing IDs raise `KeyError`; overlays
  shadow inherited templates by ID. Existing ordinary decorator APIs remain unchanged.

## Proven compiler staging

```text
explicit registrations + discovery materialization -> normalized immutable definition snapshot
  -> ordinary boundary Use/Expose preparation (no generated definitions)
  -> for each visible exact source identity in each template declaration area:
       fresh _Compiler._compile_source_core(id, exact_definition_service_key)
       -> complete, frozen, recursively undecorated Component at declaring-area root
       -> source_filter(Component) -> RegistrationInfo -> template factory
  -> immutable generated definitions + selection/provenance evidence
  -> one boundary visibility consistency check with generated definitions included
  -> fresh normal compiler -> generated target when on _undecorated_component_view(core)
       (ordinary decorator when keeps its existing view)
  -> decorator dependencies -> frozen runtime plans
```

The new internal `_Compiler._compile_source_core` is the reusable phase seam. It consumes a fresh compiler containing
an already-normalized, visibility-prepared blueprint, build arguments, and (for overlays) the same anchored singleton,
pre-configuration, owner, and inherited-explanation inputs as normal compilation. The caller first obtains IDs from
normal visibility enumeration; this low-level method is not a public visibility bypass. It validates the exact closed
source service key, compiles in the definition's area with `parent=None`, and freezes only its private component graph.
The disposable compiler refuses subsequent runtime `compile()` calls. No inspection steps are retained or published.

All recursive `_compile_decorators` calls return no definitions in inspection mode, including ordinary decorators.
Thus descendant filters cannot match resources contributed only by decorators on source dependencies. Pre-configuration
metadata/dependencies retain existing Component traversal semantics; their application functions are not activated.
Build-time argument derivations/filters remain ordinary compiler callbacks, subject to the existing purity contract.

Anchored singleton handling is deliberately different from recompilation: clone the frozen parent component tree,
omitting every decorator branch, while preserving the parent's selected dependencies, owner metadata, and untouched
activation step. Definition-side root name/tags/service key are restored when the anchored view used a public alias.
The canonical source root's `argument` is explicitly reset to `None`, even when the first anchored singleton step was
captured from a consumer dependency; descendant argument names remain unchanged.
This avoids both leaking decorator-only descendants into the source predicate and rewiring a parent singleton to
an overlay resource. New non-anchored source contexts use the current overlay blueprint normally.

A source definition's own `when` is **not** an enumeration filter. Its canonical inspection root has no parent;
root exclusion would incorrectly discard a valid contextual source before its decorator injection exists. The source
filter sees that parentless core; its dependencies still apply contextual conditions normally. Actual injection applies
the source definition's `when`, argument filters, and visibility again. An exact `select(cf.with_id(source.id))` failure
never falls back to another registration. Inspection failure in a source dependency is an ordinary build failure, not
an incomplete metadata fallback.

## Generated-target applicability view: review-corrected M05 interface

Ordinary `_compile_decorators` receives a core without its own attached decorators, but its selected dependencies may
already have decorators. `Component.descendants()` traverses those branches. The original M01 contract overstated
what that existing seam excludes; ordinary behavior must remain compatible.

The internal `components._undecorated_component_view(core) -> Component` now supplies the required generated-template
view. At the existing applicability seam, after core dependencies/pre-configurations complete and before attaching
target decorators, M05 skips snapshot creation when there are no generated candidates; otherwise it takes one
snapshot and reuses it for every generated-template `when` at that occurrence.
Ordinary `when` still receives the original component. The helper copies current graph records into a separate frozen
inspection graph with all attached `decorator_ids` removed. Original occurrence IDs, parent links, argument names,
selected dependency identities, boundary metadata, generic facts and ownership metadata remain intact. No dependency
selection, filters, constructors, factory functions, or activation plans run while making the snapshot. Parent context
is exactly the context available at that compilation point; it is not re-rooted or artificially completed.

The helper accepts both in-progress draft graphs and already frozen graphs. Later compiler mutations cannot attach
decorators to its snapshot. It retains the original parent/context nodes to support ordinary parent filters; removing
attached decorator pipelines does not erase a real decorator parent when the target itself is its dependency.
This metadata snapshot is separate from runtime plan publication. The M01 helper copies the whole currently known
graph; M05 must assess restricting copies to relevant occurrence context to avoid work scaling with unrelated roots.
Do not copy once per template. M05 may optimize copying reachable records, but
must retain these semantics and the new probe. The helper is not yet wired into generated definitions because the
public template pipeline belongs to M04/M05.

## Cycles and boundary feedback: resolved decisions

A source depending on a target candidate is legal. Inspection traverses its undecorated target core without expansion
recursion. The probe succeeds when the candidate generated decorator does not match. If a selected target decorator
injects the same source, normal compilation detects the actual activation cycle; repeated failed builds produce the
same `circular-dependency` codes and witness paths. Keep that existing code and add template/source provenance when
generated definitions exist in M04/M05. Do not reject all source-to-target edges or add a speculative expansion stack.

Boundary preparation is a separate real dependency: `_compiled_boundary_component` currently includes ordinary
decorators while Use/Expose filters inspect its temporary graph. Preserve that existing semantics for the initial
visibility snapshot. After expanding templates once, run `_prepare_boundary_visibility` once on the normalized
expanded definition snapshot (not on a partially resolved boundary cache). Compare each boundary's ordered
`resolved_uses` and `resolved_exposes` tuples against the initial prepared snapshot. If preparation newly fails or
those tuples differ, raise `template-visibility-cycle`, retaining the original boundary issue/path and affected
boundary/template/source provenance. Do not re-enumerate sources or rerun template factories to find a fixed point.
If equal, normal compilation uses the initially agreed visibility plus generated definitions.

The executable boundary probe shows a descendant filter that initially selects one source but becomes ambiguous
when a generated-equivalent decorator contributes a marker dependency. The recheck deterministically catches it.
This is the concrete unsupported expansion/visibility feedback case; an ordinary source-to-target dependency alone
is not one. M04 implements the recheck with expansion; M06 extends coverage to boundary aliases and overlays.
No unresolved phase ordering choice is delegated to those milestones.

## Generic feasibility and M02/M03 interface

`generic_utils._project_service_type(registered_service, contract)` follows explicit immediate generic bases and returns
that base with inherited arguments, `None` if unrelated, or raises `ValueError` for conflicting inheritance paths.
It normalizes aliases; it never consults an implementation to infer service membership. Each inheritance edge maps
actual TypeVar objects, not their names. Own `__orig_bases__` are used instead of accidentally inheriting stale bases
from a grandparent; plain generated subclasses correctly follow their real class bases. Independent source and target
maps never merge. Known consistent diamond inheritance is accepted; conflicting arguments are rejected.

The using-typetoolbox skill was applied. Existing `GenericTypeMap` remains unchanged for existing consumers; its
internally name-keyed representation is unsuitable for this new identity-preserving projection seam. M01 therefore
adds an internal helper rather than changing existing generic behavior globally. The helper accepts open projections
and preserves unresolved variables. It does not yet unify a projection with a closed contract, specialize a decorator,
or promise ParamSpec/TypeVarTuple inference. Those checks belong to M03.

M02 must call this helper for known nominal compatibility before adding any contribution. A `None` projection rejects
an incompatible registration transactionally. A conflicting projection rejects with a contract-validation error.
A projection containing unresolved arguments records a deferred constraint for M03; it must not guess concrete types.
Closed contract arguments must be checked when already concrete (do not accept `Base[str]` for `Base[int]` merely
because origins match). No generic mapping should use variable names as keys. M03 completes nested constraint checks,
DerivedServices matching, and target-to-decorator binding.

## Ordering, identity, retention, and retries

- Enumerate from the post-discovery snapshot, with explicit registrations preceding discovered registrations as today.
  Deduplicate within a template by source registration ID and canonical definition request/owner context, not class,
  name, specialization, or occurrence. Imported/exposed views of the same source do not create extra bindings.
  Different template IDs remain independent and additive.
- Reserve a shared declaration ordinal for ordinary decorators and templates. Generated activation ordering extends
  the existing `(position, layer_index, -definition.order)` key with `-source_ordinal` for equal declaration ordinals;
  ordinary definitions use zero. Earlier-declared sources are consequently outermost at equal position, matching
  existing outside-to-inside declaration semantics. Do not manufacture large integer intervals for expansion counts.
- Generated logical definition identity is `uuid5(UUID(template_id), source_registration_id)` (one per source/template).
  Closed target occurrences preserve that logical ID and retain the original target registration ID/service key;
  existing occurrence IDs distinguish uses. Additional specialization keys, if needed internally, derive from this
  logical ID and the existing runtime type-key machinery, never from display names or global mutable counters.
- `_Layer` must retain group memberships, template declarations/origins/shared ordinals, and removed template IDs.
  `_Blueprint` retains normalized discovery results, visibility, owner layers, original declarations and generated
  provenance (template/source IDs, declaration area, source ordinal, projected target contract). Successful plans must
  retain original templates so overlay builds can expand them against new visible sources without reusing stale
  generated definitions as declarations.
- Source core results can be cached within a build by exact source identity/request and owner context; source predicates
  remain per-template. Factories execute once per matched source/template in an expansion attempt. Keep evidence for
  inspection without callback replay. Discard generated definitions after failure and regenerate from the immutable
  original snapshot on retry; never append them to builder state. During expansion `_assert_mutable` must reject
  builder mutation and build/preview reentry. No generated state survives a failed build.

## Delivered files and actual verification

- `clean_ioc/container.py`: disposable exact source-core compilation, recursion-wide decorator suppression, and
  decorator-free anchored metadata cloning. Normal compilation is unchanged unless the private seam is invoked.
- `clean_ioc/components.py`: immutable recursively undecorated occurrence snapshot for generated-template predicates.
- `clean_ioc/generic_utils.py`: identity-based nominal service projection seed for M02 contract validation/M03 binding.
- `tests/test_decorator_template_feasibility.py`: 13 portable probes for completed/frozen source graphs, no constructor
  or factory activation, decorator-descendant exclusion, exact closed keys, contextual conditions/exact binding,
  safe source-to-target traversal versus actual cycles/retries, local/exported boundary visibility, anchored overlay
  ownership, stable discovery identities, visibility feedback, aliases/generated classes and independent variables.
- `.work/decorator-templates.md`: chosen spellings and resolved source-context/cycle contract.
- `.work/decorator-templates/01-handoff.md`: this implementation evidence and next-step interfaces.

Executed with repository `.venv` Python 3.14.4; imports resolve to this working checkout:

1. Initial feasibility run: 9 passed, 2 failed due to incorrect test API names (`CompiledGraph.find`, `cf.named`);
   corrected to existing APIs. No production behavior was changed to satisfy those mistakes.
2. Focused compiler/generic/ownership regression command, before the final two exact-key/alias probes:
   `.venv/bin/python -m pytest tests/test_decorator_template_feasibility.py tests/test_provider_maps.py
   tests/test_closed_generic_constructors.py tests/test_bundles.py tests/test_complex_dependencies.py
   tests/test_boundaries.py tests/test_resource_ownership.py tests/test_compiler_tooling.py -q --disable-warnings --maxfail=3`
   — **277 passed in 2.63s**.
3. Final feasibility plus ordinary container suite:
   `.venv/bin/python -m pytest tests/test_decorator_template_feasibility.py tests/test_container.py -q --disable-warnings --maxfail=3`
   — **98 passed in 0.45s**, including all **13 feasibility probes**.
4. `.venv/bin/ruff check clean_ioc/container.py clean_ioc/generic_utils.py tests/test_decorator_template_feasibility.py`
   — **passed**. The changed Python files were formatted with Ruff.
5. `.venv/bin/ty check clean_ioc/container.py clean_ioc/generic_utils.py tests/test_decorator_template_feasibility.py`
   — **passed**. Intentional same-name TypeVars and conflicting inheritance fixture carry narrow diagnostic ignores.

No full `make ci`, full Python matrix, or bark-core integration claimed; those remain assigned to later milestones.
Checkpoint pre-commit hooks are coordinator-run and must be recorded separately. Public documentation comprehension
has not run because no public documentation changed. Independent review is required before M01 acceptance/M02.

## Independent-review repairs (implementation verification reopened)

The reviewer requested two bounded corrections; both are implemented, pending independent recheck:

1. Canonical anchored source root retained a dependency argument from the first selected parent step. Reset only
   its root argument to `None`. The strengthened overlay probe registers a Consumer before its singleton Source,
   verifies the anchor retains `argument="source"`, the canonical view has no parent/argument, its resource retains
   `argument="resource"`, cache/cleanup ownership is preserved, and runtime resolution returns the existing singleton.
2. Ordinary descendant traversal includes decorators attached to dependency nodes. Add the separate immutable
   `_undecorated_component_view` helper and a probe showing `Target -> Dependency -> DependencyDecorator -> Marker`:
   ordinary `when` still sees Marker, generated-template view does not. The probe checks in-progress and frozen graph
   inputs, non-root parent filters, selected named dependency identity, argument/ownership facts, immutable snapshots,
   and ordinary runtime decorator application. Update the parent contract and M05 interface accordingly.

Repair verification: feasibility suite **14 passed in 0.18s**. Ruff and ty pass for `components.py`, `container.py`,
and the feasibility tests. Format and diff checks pass. The focused repair regression command
`.venv/bin/python -m pytest tests/test_decorator_template_feasibility.py tests/test_container.py
tests/test_compiler_tooling.py tests/test_resource_ownership.py tests/test_boundaries.py -q --disable-warnings --maxfail=3`
passed **277 tests in 2.41s**. No commits, M02
implementation, public documentation, or bark-core changes were made by this repair turn.
