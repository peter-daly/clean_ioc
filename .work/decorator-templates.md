# Work item — Registration-driven decorator templates

Status: In progress; M01–M04 accepted, M05 decorator activation next. Feature implementation incomplete.

Created: 2026-09-23

Implementation repository: `/Users/peter.daly/WS/pete/clean_ioc`

Integration test bed: `/Users/peter.daly/WS/bark/bark-core`

Constraint: Do not commit to bark-core. Preserve unrelated changes in both repositories.

Documentation constraint: Do not use bark-core code as a reference for public documentation. Author standalone,
fictional examples from the Clean IoC feature contract; do not copy or adapt bark-core code, imports, identifiers,
resource-tag conventions, or composition patterns into documentation. Bark-core remains an internal integration test
bed. Its references and design sketches in this work item are implementation context, not documentation source material.

## Outcome

A bundle can declare a decorator template once. Each matching source registration supplies a distinct decorator
binding. That binding applies to eligible registrations selected through an explicit service group or a derived-services
declaration, including generic handler families and registrations discovered during build. Bundles supplying sources, targets, and the relationship
can be composed independently and in either declaration order.

For bark-core, each `UnitOfWork` registration contributes a `UnitOfWorkOperationHandlerDecorator`. The decorator wraps
command, query, event, reply, query-result, and data-protection handlers whose undecorated dependencies use resources
associated with that UoW. New handler families participate by contributing registrations to the shared group, without
editing a central list. For explicit groups, inheritance alone does not opt a registration into decoration.

For applications wanting automatic participation, `DerivedServices(OperationHandler)` is a convenient alternative to
an explicit `ServiceGroup`. Both are accepted as a template's `services` target. Choosing the derived-services form opts
that template into automatic matching; it does not add memberships to explicit groups.

Different UoW implementation families can have separate templates. For example, a SQLAlchemy template and a DynamoDB
template both enumerate the `UnitOfWork` service, but each expands only for its own implementation family. Each can
choose its own decorator, arguments, applicability filter, and position.

`when` remains an ordinary `ComponentFilter` over the target component. Resource matching and handler opt-out remain
bark-core policy; Clean IoC does not gain transaction-specific knowledge.

## Findings from the current code

- `bark_core/unit_of_work/bundles.py` has `_OPERATION_HANDLER_SERVICE_TYPES` with eight service origins.
  `RegisterUnitOfWorkOperationHandlersBundle.apply()` repeats a decorator registration for each origin, binds the UoW
  by implementation and name, and combines a resource-descendant filter with the handler opt-out filter.
- `bark_core/db/bundles.py` creates concrete SQLAlchemy UoW types and installs their handler policies. Moving source
  enumeration into the template would remove this per-UoW handler-policy wiring.
- In this checkout, the `UnitOfWork` service protocol itself is non-generic, but its SQLAlchemy implementation is
  `SqlAlchemyUnitOfWork[TSession]`. The database bundle generates a concrete subclass of
  `SqlAlchemyUnitOfWork[self.session_type]` and registers that class under `UnitOfWork`. Source handling must preserve
  this inherited specialization; checking only the service key or the implementation's immediate generic origin loses
  the session binding. Generic source implementations are required scope, independent of generic target handlers.
- `CommandHandler[C]` explicitly derives from `OperationHandler[C, CommandResult]`; `EventHandler[E]` and
  `DataProtectionRequestHandler[R]` derive from `OperationHandler[..., None]`. Query handlers preserve both variables.
- `_RegisterOperationHandlersBundle.apply()` uses deferred `register_generic_subclasses()` for data-protection
  handlers. A snapshot taken when the template is declared would miss later discovery.
- Clean IoC's `_decorator_service_matches()` matches exact service keys or the same generic origin. Registering a rule
  on `OperationHandler` currently does not match registrations under `CommandHandler`.
- `_layer()` materializes discovery; `_Blueprint.decorators()` selects definitions; `_compile_decorators()` evaluates
  ordinary applicability before attaching the current target's decorators. Dependency occurrences can already have
  decorators, and `Component.descendants()` traverses them. Generated-template applicability therefore needs M01's
  recursively undecorated snapshot view; extend these build-time stages without changing ordinary decorator semantics.

## Chosen API direction (M01 accepted; public implementation pending)

M01 settles the spellings below; they are not existing public APIs yet. Implement a registration-to-template factory so a
source's metadata can configure normal decorator options without changing the `ComponentFilter` contract.

```python
# Shared declaration, imported by handler bundles and transaction-policy bundles.
operation_handlers = ServiceGroup("operation-handlers", service_type=OperationHandler)


def transaction_template(source: RegistrationInfo) -> DecoratorTemplate:
    return DecoratorTemplate(
        services=operation_handlers,
        decorator_type=UnitOfWorkOperationHandlerDecorator,
        decorated_arg="handler",
        arguments={"unit_of_work": select(cf.with_id(source.id))},
        when=(
            cf.implementation_matches_type_filter(handler_allows_unit_of_work)
            & cf.has_descendant(
                cf.has_tag(
                    UNIT_OF_WORK_RESOURCE_TAG_NAME,
                    resource_tag_value(source.name),
                )
            )
        ),
        position=OperationHandlerDecoratorPosition.UNIT_OF_WORK,
    )


template_id = builder.register_decorator_template(
    for_each=UnitOfWork,
    template=transaction_template,
)
```

For separate backend policies, declare family-specific templates instead of the catch-all above. Chosen spelling:

```python
sqlalchemy_template_id = builder.register_decorator_template(
    for_each=UnitOfWork,
    source_filter=cf.implementation_matches_type_filter(is_sqlalchemy_unit_of_work),
    template=sqlalchemy_transaction_template,
)

dynamodb_template_id = builder.register_decorator_template(
    for_each=UnitOfWork,
    source_filter=cf.implementation_type_is(DynamoDbUnitOfWork),
    template=dynamodb_transaction_template,
)
```

These factory names represent independently authored callbacks returning `DecoratorTemplate` specifications.
`is_sqlalchemy_unit_of_work` represents an application type predicate that recognizes the SQLAlchemy generic base and
its generated concrete subclasses using the existing type/generic helpers. `implementation_type_is` uses its existing
exact-type semantics; use `implementation_matches_type_filter` when DynamoDB subclasses should also participate.
Both callbacks may reuse the same decorator class while constructing different ordinary `when` component filters.
`source_filter` is a normal `ComponentFilter` selecting UoW sources; each returned specification's `when` is a normal
`ComponentFilter` selecting handler occurrences. Names, tags, lifespans, and other existing filters can be composed in
either location. There is no dedicated implementation-family parameter or new type-matching behaviour hidden in it.

- `RegistrationInfo` is an immutable definition view with ID, service type, implementation type (when known), name,
  and tags, plus resolved generic bindings where statically available. Preserve the specialized implementation type
  and bindings inherited through generated concrete subclasses. Bindings must retain their declaring generic/type
  variable identity, with a way to inspect a particular base such as `SqlAlchemyUnitOfWork`; a flat dictionary keyed
  only by variable name is insufficient. It is not a compiled `Component`, and exposes neither runtime instances nor
  dependency occurrences. Unknown implementation bindings for factories must remain explicitly unknown.
  M01 found no suitable existing definition view. Add `RegistrationInfo.implementation_bindings(base_type)` returning
  an immutable TypeVar-keyed mapping, or `None` when no static binding can be established; an unresolved variable
  remains a TypeVar value. Never infer implementation bindings by activating a factory.
- The factory returns one immutable decorator specification per source. Existing argument policies bind the exact
  source; `select(cf.with_id(source.id))` must never silently fall back to another registration with the same name/type.
- Optional `source_filter: ComponentFilter = cf.all_components` narrows sources before the template factory is invoked.
  It receives a real undecorated source `Component`, not the `RegistrationInfo` metadata view given to the factory.
  Preserve existing filter semantics rather than making metadata-only objects pretend to support graph traversal.
- The specification carries a service target declaration plus the ordinary decorator options: class or typed callable,
  decorated argument, arguments, `when`, position, name, and tags. Accept both `ServiceGroup` for explicit membership
  and `DerivedServices` for automatic matching. The declaration makes the selection policy explicit without an
  `include_derived_services` flag. Ordinary `register_decorator()` stays unchanged.
- The factory may close over source metadata when constructing `when`; `when` itself always accepts one `Component`.
  Do not overload `when` with a two-argument predicate or a filter-factory signature.
- Add the registration API to `ComponentBuilder`, so root, scope, and boundary builders and bundles share it.
- Return a template ID. Add `patch_decorator_template(template_id, *, for_each=UNCHANGED,
  source_filter=UNCHANGED, template=UNCHANGED)` and `remove_decorator_template(template_id)`. Patching replaces supplied
  fields and preserves ID/order; replacing the factory replaces its returned options. Missing IDs raise `KeyError`.
  Overlay patch/removal shadows inherited definitions by ID; generated decorator IDs remain available for inspection.

## Behavioural contract

### Sources and exact binding

1. Enumerate source registrations after queued discovery, using normal composition visibility. For the first version,
   `for_each` selects an exact canonical source service key, including an explicitly closed generic key. Open-generic
   source enumeration and arbitrary registration-generation callbacks are outside this item. This restriction concerns
   enumeration of source service keys, not generic implementations registered under those keys: closed generic
   implementations and generated concrete subclasses of them are supported.
2. Class, factory, and instance registrations under that source key are supported without activating them.
   Two registrations of the same implementation are two sources; graph occurrences of one registration are one source.
3. Zero sources generates no decorators. Every matching source generates a candidate definition, but target `when`
   decides whether it is used. Source registration conditions remain enforced when the decorator dependency compiles;
   an ineligible or invisible selected source must not be replaced by a different UoW.
4. Expansion runs at build time and cannot mutate the builder. Factories must be pure; failed-build diagnostics or
   rebuild attempts may evaluate them again. Enumeration alone cannot instantiate a UoW or open a database connection.

### Source component-filter context

1. Evaluate `source_filter` against the completed undecorated source subtree, before invoking the template factory.
   Support ordinary composition of type, name, tag, generic, lifespan, and descendant filters. Dependencies introduced
   only by decorators are excluded. Generated-template target `when` also excludes attached decorator branches
   recursively through the separate M01 snapshot view; ordinary decorator predicates retain their existing behavior.
2. Chosen context: the source's canonical root occurrence within its declaring composition area for the current
   build, with no consumer parent. `parent(...)` therefore does not match there. Selection does not vary with whichever
   handler first happens to request the UoW. Respect boundary visibility and overlay ownership when identifying this
   occurrence, and deduplicate selected sources by registration identity rather than dependency occurrence. The source
   definition's own contextual `when` is not used to discard this parentless inspection root: actual injection must
   satisfy that condition. Dependency conditions still run under their normal parents during inspection.
3. Source selection and target applicability are separate decisions. Evaluating `source_filter` once per source context
   does not bypass registration-level conditions or argument policies at the actual injected source occurrence.
   Target `when` continues to evaluate independently for each handler occurrence.
4. This requires compiled source-subtree information, so expansion cannot be a metadata-only loop immediately after
   `_layer()`. M01 establishes a disposable, recursively undecorated compiler pass after ordinary boundary visibility
   is prepared. Its frozen Components are inspection metadata only; normal runtime compilation starts fresh after
   expansion. A source may depend on a target candidate: this does not recursively expand templates. If generated
   decorator injection closes an activation cycle, reject it with the existing deterministic `circular-dependency`
   diagnostic plus template/source provenance. Boundary Use/Expose filters can themselves inspect decorated trees;
   after expansion, recheck visibility once against the expanded blueprint. Changed or newly invalid selections fail
   with `template-visibility-cycle`, preserving the original boundary cause. Never iterate user callbacks to a fixed
   point or silently use a different source visibility snapshot.
5. Keep filter evaluation and expansion build-time only, including failed-build retry behaviour. Record selection
   evidence for inspection without rerunning filters. Resolve the canonical-root context and compiler phase in the
   spike before accepting this API; do not silently restrict `ComponentFilter` to a metadata-only subset. M01
   implementation decisions and probes are recorded in `decorator-templates/01-handoff.md`.

### Independent source-family policies

1. Express SQLAlchemy/DynamoDB family selection with existing component filters and application type predicates.
   SQLAlchemy predicates must recognize closed implementations and generated concrete subclasses of
   `SqlAlchemyUnitOfWork[TSession]`; immediate generic-origin comparison alone is insufficient.
2. Preserve existing exact-type versus type-predicate semantics. Callers can select by type, name, tag, or a composed
   condition without adding special-purpose template parameters. Preserve source generic metadata after filtering.
3. Use the source component's statically compiled metadata and dependencies. Do not instantiate a factory to determine
   the runtime result's concrete backend. If its declared type is too broad for a type predicate, callers can use
   explicit registration tags or other ordinary filters. Keep existing component-filter truth/error semantics rather
   than introducing a separate indeterminate-family matching protocol.
4. Multiple templates are independent and additive, with no implicit most-specific-wins or registration-order override.
   If both a catch-all and a family template match one source, both generate definitions. Existing application validation
   may reject duplicate UoW boundaries; the compiler must retain both template identities so that cause is explainable.
   Use disjoint family policies when one transaction boundary per source is intended.
5. A handler using both SQLAlchemy and DynamoDB resources can receive one boundary from each matching source/template.
   A handler using only one backend receives only the boundaries allowed by those templates' `when` filters.
6. Each integration bundle can install its own template independently of source registration order. Removing or
   replacing the SQLAlchemy template leaves the DynamoDB template intact. Reapplying a bundle follows existing run-once
   policy; templates are not deduplicated merely because their decorator classes happen to be equal.

### Generic sources and independent bindings

1. Preserve `SqlAlchemyUnitOfWork[OrdersSession]` and `SqlAlchemyUnitOfWork[AuditSession]` as distinct source
   registrations when both are registered under `UnitOfWork`. The template binds the existing source registration,
   including its session selection arguments, name, lifespan, and generic specialization; it must not recreate a UoW
   from its generic origin or resolve the default `UnitOfWork` again.
2. Recognize both a directly registered closed implementation alias, where supported by normal registration, and
   bark-core's generated concrete subclass. Generic bindings may be inherited through multiple levels. Discovery,
   metadata inspection, and exact dependency binding must agree on which specialization is being used.
3. Keep source bindings separate from target bindings. `TSession -> OrdersSession` belongs to the source; operation
   and result variables come from the concrete handler's `OperationHandler` base. Do not merge by variable name,
   positional index, or coincidental type equality. Each source can contribute to many handler specializations.
4. Two named UoWs using the same `SqlAlchemyUnitOfWork[OrdersSession]` specialization still produce distinct source
   identities and must select their own configured session registration. Specialization alone is not a binding key.
5. Generic source metadata may be used to construct an ordinary component filter. Resource tags remain bark-core's
   default relationship mechanism: the feature must not assume equal session types imply equal database ownership.
6. A source registered under a closed generic service key must still obey ordinary dependency service selection.
   An ID filter alone does not change the decorator parameter's requested service type. Validate incompatible bindings
   clearly; do not silently alias closed service keys to their origin. Automatic enumeration/specialization of an open
   source definition needs a separately specified finite set of requests and is not implied by this feature.

### Explicit service groups and generic mapping

Chosen name: `ServiceGroup`. It is a shared identity for a set of opted-in registrations and declares their common
service contract. It borrows the explicit contribution model from `ProviderMapGroup`, but needs no map keys, provider
factories, or injectable collection. For this item its consumer is a decorator template; generalizing other Clean IoC
APIs to consume groups is not required. Keep existing `ProviderMapGroup` and its `contributes` API compatible.

```python
operation_handlers = ServiceGroup("operation-handlers", service_type=OperationHandler)

# Command bundle contributes its concrete registrations.
builder.register(
    CommandHandler[CreateOrder],
    CreateOrderHandler,
    groups=[operation_handlers],
)

# Data-protection bundle contributes every registration produced by discovery.
builder.register_generic_subclasses(
    DataProtectionRequestHandler,
    groups=[operation_handlers],
)

# SQLAlchemy and DynamoDB template factories independently target the same group.
DecoratorTemplate(
    services=operation_handlers,
    decorator_type=UnitOfWorkOperationHandlerDecorator,
    decorated_arg="handler",
    arguments={"unit_of_work": select(cf.with_id(source.id))},
    when=resource_matches_source,
)
```

The declaration is not separately registered as a service. Bundle authors import the same group object. Membership is
stored on each builder's registration definitions, not in a mutable global list on the declaration. Thus later bundles,
deferred discovery, and overlays contribute through normal composition. `groups=` is the chosen API spelling.

1. Groups use object identity, as provider-map groups do. Same-name declarations are different groups; names are
   diagnostic labels. Multiple registrations can join one group and one registration can join multiple groups. Repeated
   membership in the same group is idempotent and does not produce duplicate decorator layers.
2. Membership belongs to the registration, not its class or service type. Two registrations of the same implementation
   can make different membership choices. Nonmembers remain undecorated by group templates even if their service
   derives from `OperationHandler`. Source filtering and target `when` remain independent decisions.
3. Validate a contribution against the group's declared contract. Follow the registered service's explicit generic
   bases to establish compatibility; merely having an implementation with a `handle` method is insufficient. Group
   membership does not make an incompatible service valid. Reject incompatibility transactionally at declaration time
   when knowable, otherwise during discovery/specialization with group and registration context in the error.
4. Project the concrete member service onto the group's contract before specializing the decorator. For example,
   `CommandHandler[CreateOrder]` gives `OperationHandler[CreateOrder, CommandResult]`, while a data-protection request
   handler gives `OperationHandler[DeleteData, None]`. Preserve the original service key and actual wrapped component;
   do not register synthetic public `OperationHandler` aliases or resolve a second handler through the base contract.
5. Cover multiple inheritance levels, fixed/reordered generic arguments, aliases, and both supported generic syntaxes.
   Reuse the existing generic mapping machinery. Reject unresolved/conflicting mappings with a build diagnostic;
   do not guess from TypeVar names or choose an arbitrary inheritance path.
6. A source/template pair applies at most once per member occurrence. Distinct deliberately registered templates remain
   independent policies even if they target the same group. Reusing group declarations across builders cannot leak
   membership or build state. An empty group simply supplies no targets.
7. Support `groups=` on explicit registration, subclass and generic-subclass discovery, and structural-pattern
   registration. Discovery propagates membership onto each generated registration; closed specializations inherit
   membership from their selected definition. Factory/instance registration follows the same contract checks. Do not
   enumerate all possible closed generic services in advance or infer membership from an implementation's other uses.
8. Membership neither changes normal resolution/collection selection nor grants visibility across boundaries. An
   override has the groups explicitly declared on that override; it does not inherit membership merely because it
   replaces a grouped registration under the same service key. Preserve metadata through blueprint snapshots and
   inherited registrations in overlays. Parent-owned singleton activation remains anchored.
9. Here, dynamic means discovered/generated before build or introduced through a scope builder. Runtime `resolve()`
   still cannot compile an unseen type, add group members, or mutate the container.

### Derived-services convenience

Both declarations implement the same internal target-selection contract and are interchangeable in `services=`:

```python
# Explicit membership controlled by contributing bundles.
operation_handlers = ServiceGroup("operation-handlers", service_type=OperationHandler)

# Alternative: automatically select registered services derived from this contract.
operation_handlers = DerivedServices(OperationHandler)

DecoratorTemplate(
    services=operation_handlers,
    decorator_type=UnitOfWorkOperationHandlerDecorator,
    decorated_arg="handler",
    arguments={"unit_of_work": select(cf.with_id(source.id))},
    when=resource_matches_source,
)
```

- `DerivedServices(Base)` includes registrations under the base contract and explicitly derived service contracts,
  including their closed generic forms. It examines registered service types, not unrelated implementation classes
  or arbitrary structural protocol matches. It does not discover/register classes on its own.
- Selection happens against available definitions and concrete requests during compilation, including deferred
  discovery and overlay additions. No eager membership snapshot is taken when the declaration is constructed.
- Reuse the explicit group's generic contract projection, visibility, per-template deduplication, and anchored ownership
  rules. Only candidate selection differs; the target `when` filter and generated decorator semantics stay the same.
- Explicit `ServiceGroup` membership and `DerivedServices` selection remain independent. The convenience declaration
  does not mutate groups, require `groups=` on registrations, or add public aliases for the base service. Use explicit
  groups to include only selected registrations; use derived selection when all matching service contracts should qualify.
- Both declarations are immutable and reusable across builders. A private shared selection interface is sufficient for
  this item; arbitrary user-defined provider plugins or unions of target declarations are not prerequisites.
- Different templates targeting the two forms remain additive if they select the same registration. Reuse existing
  template identity and ordering rules; do not collapse independently declared policies.

### Applicability, ordering, and identity

1. Every generated-template `when` sees the same completed, recursively undecorated target subtree via
   `_undecorated_component_view(core)`. Resources introduced only by a decorator, including a dependency's decorator,
   cannot activate a template. Preserve original target parent/argument context, occurrence identity, selected
   dependencies, and ownership metadata; do not recompile a target as a new root to obtain this view. Ordinary
   decorator predicates keep their existing view and semantics.
2. Existing position ordering is unchanged: higher positions are outside. At equal positions, use template declaration
   order relative to ordinary decorator declarations, then source registration declaration order within a template,
   outside to inside. Deferred sources follow existing explicit-before-discovered ordering. Do not order by UUID,
   dependency traversal, or the time a closed generic specialization happens to compile.
3. Identify generated definitions from the template identity and source registration identity, retaining any necessary
   specialization identity without conflating definition ID and occurrence ID. Diagnostic retries and inherited
   re-expansion must not create duplicate definitions.
4. Generated definitions remain normal decorators for lifespan, async activation, disposal, dependency selection,
   graph validation, and inspection. The source retains its declared lifespan; the decorator follows the target's.

### Scopes, boundaries, and diagnostics

1. Inherited templates apply to eligible new overlay-owned plans and visible source registrations. New overlay sources
   may contribute decorators to plans the overlay recompiles; parent-owned singleton activation stays anchored.
2. Plain runtime scopes reuse compiled plans. They do not re-enumerate sources or rerun factories/filters.
3. Follow existing boundary-local decorator policy and source visibility. A root template is not permission to decorate
   private boundary components or bind private sources. Cover explicit exports/imports through existing contracts.
4. Retain templates in the blueprint so overlays and failed-build retries can reproduce expansion. Removing an inherited
   template suppresses its generated definitions for overlay-owned plans without rewiring parent-owned objects.
5. Build errors identify the template, source registration, target service, and relevant argument or generic mapping.
   Inspection can explain which template/source produced a decorator without rerunning user callbacks. Preserve existing
   manifest redaction and semantic identity conventions; do not export closure contents or runtime object values.

## Implementation sequence

Follow the [sequential milestone plan](decorator-templates/README.md). This document remains the feature contract;
the individual milestone files define bounded assignments, model/effort settings, checks, and handoffs.

| Order | Milestone | Implementation recommendation |
| --- | --- | --- |
| 01 | [Contract and compiler feasibility](decorator-templates/01-contract-and-feasibility.md) | Astra High |
| 02 | [Explicit service-group membership](decorator-templates/02-service-groups.md) | Sol High |
| 03 | [Generic projection and DerivedServices](decorator-templates/03-target-selection-and-generics.md) | Astra High |
| 04 | [Source filtering and template expansion](decorator-templates/04-source-filtering-and-expansion.md) | Astra High |
| 05 | [Decorator compilation and activation](decorator-templates/05-decorator-compilation.md) | Astra High |
| 06 | [Composition edits, scopes, and boundaries](decorator-templates/06-scopes-boundaries-and-edits.md) | Astra High |
| 07 | [Diagnostics and inspection](decorator-templates/07-diagnostics-and-inspection.md) | Sol High |
| 08 | [Local bark-core integration proof](decorator-templates/08-bark-core-test-bed.md) | Astra High |
| 09 | [Standalone documentation and comprehension](decorator-templates/09-documentation.md) | Sol High |
| 10 | [Regression checks and completion](decorator-templates/10-final-verification.md) | Sol High |

Every milestone uses a separate **Luna Low code-search agent**, the listed implementation agent, and an independent
**Astra High review agent**. Every passed gate within a milestone requires a **local clean-ioc checkpoint commit**
before continuing to the next gate. This includes search, implementation verification, independent review, applicable
documentation comprehension, and final handoff. Proceed to the next milestone only after all its predecessor's gates
pass and their commits are recorded. Stage only task-owned changes/evidence; do not push or commit to bark-core.
Exact model IDs and delegation instructions are in the milestone plan.
Current execution status and gate evidence are recorded in the milestone directory.

Public documentation changes additionally require a **new Luna Low reader with no feature history**, followed by a
quiz sent only after its initial review. Follow the [fresh-reader protocol](decorator-templates/documentation-review.md):
give the reader only an isolated public-documentation packet, keep the answer rubric hidden, have Astra grade its
understanding, and repeat with a new reader after substantive revisions. Do not use bark-core code as a documentation
reference. Milestone 09 must pass both technical and comprehension review.

Likely implementation areas: `clean_ioc/container.py`, `components.py`, generic helpers, public exports, and tooling
provenance; add `tests/test_decorator_templates.py` plus focused boundary/scope/generic regressions. Keep template
models/helpers in a dedicated module if that avoids further enlarging the compiler.

## Acceptance tests

| Scenario | Required result |
| --- | --- |
| Two UoWs using the same class, with distinct registrations | Two exact bindings; no collapse by implementation/name |
| Generic UoWs for OrdersSession and AuditSession registered under UnitOfWork | Each decorator uses the existing correctly specialized UoW and session |
| Generated concrete subclass of a closed generic UoW | Inherited source bindings remain available and correct |
| Two named databases use the same session type and UoW specialization | Exact registration/configuration retained; generic type alone cannot select ownership |
| Generic source and generic handler use distinct variables with the same name | Independent source/target bindings; no accidental unification |
| SQLAlchemy and DynamoDB sources share the UnitOfWork service key | Each family template expands only for its own sources |
| Separate family templates use different decorators, positions, and filters | Each policy's options are preserved; mixed-resource handler composes both |
| Catch-all and family-specific templates overlap | Both definitions retained with distinct provenance; no silent precedence |
| Source filter combines type, name, and tag conditions | Existing component-filter semantics select only intended sources |
| Source filter inspects descendants or parent | Completed undecorated source graph; documented canonical-root parent context |
| Source factory exposes only a broad service type | No activation for type discovery; explicit tags remain usable for selection |
| Expansion changes boundary visibility or creates an activation cycle | Deterministic build diagnostic, not incomplete plans or order-dependent selection |
| One family template is removed or replaced | Other families' generated definitions remain unchanged |
| Handler uses DB A; another uses DB B; a third uses both | One A boundary, one B boundary, and both boundaries respectively |
| Several repository dependencies use the same DB | One boundary per source/template, not per matching resource occurrence |
| Handler uses no associated resource or opts out | No boundary; unrelated decorators still apply |
| Resource appears only in another decorator's dependencies | Does not enable the template |
| Command/query/event/reply/query-result/data-protection service | Correct operation/result binding and original service key |
| New compatible handler family explicitly joins the group | Participates without adding it to a service list |
| Compatible OperationHandler registration does not join the group | Not decorated by group templates |
| Two registrations of the same class, only one joins | Only the member is eligible |
| Same-name group declarations, repeated membership, and multiple groups | Identity isolation, idempotent membership, and independent group participation |
| Shared group used by backend templates and independent builders | Independent definitions; no leaked membership or build state |
| Incompatible service attempts to join | Clear contract-validation error; no partially added contribution |
| Empty group or group registered before/after templates | No targets or identical membership-based eligibility respectively |
| Handler found during build by a group-contributing discovery rule | Inherits membership and receives applicable decorators |
| DerivedServices selects a compatible registration with no group membership | Eligible automatically, including closed generics and deferred discovery |
| DerivedServices sees an unrelated service with a compatible implementation | Not selected; matching uses the registered service contract |
| Both target forms select the same registration in separate templates | Independent additive policies; no implicit cross-template deduplication |
| DerivedServices reused across builders or alongside an explicit group | No leaked state and no mutation of explicit memberships |
| Closed factory/instance target, open registration, pattern-backed target | Same matching and filter semantics where the request is compiled |
| Ambiguous generic inheritance or unresolved decorator variable | Actionable build error rather than wrong specialization |
| Template and ordinary decorator share positions | Deterministic existing outside-to-inside ordering |
| Failed build, repaired build, diagnostic retries | No accumulated definitions or duplicate layers |
| Scope overlay adds source/handler; parent singleton already exists | New plans decorated; anchored parent unchanged |
| Boundary-private target/source and explicit imported/exported contracts | Existing visibility enforced; no cross-boundary shortcut |
| Template removed/replaced before build or suppressed in an overlay | Only the intended generated policy is changed |
| Async handler succeeds or raises | Existing coordinator commit/rollback behaviour and cleanup preserved |
| Frozen graph inspection and runtime resolution | No template factory/filter re-execution for composition |

## bark-core test-bed procedure and baseline

Initial state was clean on bark-core branch `v1_rc`. Its project pins Clean IoC b14, but the existing Python 3.14.4
environment reports installed b12; this checkout is b16. Do not assume installed package metadata proves which code
tests imported. Verify `clean_ioc.__file__` each time.

For the planning baseline, a process-local import override used this checkout directly without changing bark-core's
dependency files or installed environment:

```sh
cd /Users/peter.daly/WS/bark/bark-core
PYTHONPATH=/Users/peter.daly/WS/pete/clean_ioc .venv/bin/python -c 'import clean_ioc; print(clean_ioc.__file__)'
PYTHONPATH=/Users/peter.daly/WS/pete/clean_ioc .venv/bin/python -m pytest \
  tests/unit/bundles/test_application.py \
  tests/unit/bundles/test_unit_of_work.py \
  tests/unit/bundles/test_sqlalchemy.py \
  tests/unit/bundles/test_sagas.py -q --disable-warnings --maxfail=5
```

Result on 2026-09-23: imported `/Users/peter.daly/WS/pete/clean_ioc/clean_ioc/__init__.py`; **110 passed in 8.19s**.
This verifies compatibility of the current checkout with the focused baseline, not the proposed feature.

Continue with this override for the implementation experiment. A local editable dependency is also user-authorized if
needed, but must reconcile the b14 pin/b16 checkout and remain uncommitted. Avoid an automatic environment sync
silently restoring the published dependency. Record all test-bed changes and restore only task-owned temporary wiring
when no longer needed; do not discard unrelated user changes.

Run new targeted tests first, then the existing focused bark-core set plus relevant generated-handler and SQLite
transaction tests. Record any external-service test requirements rather than treating a unit-only run as database
integration coverage. For clean-ioc, run `make ci` and required pre-commit checks after implementation, with supported
Python versions covered by the existing CI matrix. No implementation checks are claimed complete by this plan.

## Definition of done

- [ ] Public API and the behaviour above have executable portable coverage.
- [ ] All ten sequential milestones have actual implementation/check evidence and independent Astra High acceptance.
- [ ] Every passed gate in each milestone has a local clean-ioc checkpoint commit recorded in its handoff; no task commits were made in bark-core.
- [ ] Explicit `ServiceGroup` and automatic `DerivedServices` targets share generic/visibility semantics and keep distinct selection policies.
- [ ] Independent SQLAlchemy and DynamoDB templates select their own sources and compose correctly on mixed-resource handlers.
- [ ] bark-core demonstrates UoW-driven decoration across explicit group members from existing and new handler families,
  including deferred discovery, without its per-service decorator loop or per-UoW handler-policy registration.
- [ ] Resource/opt-out validation and async transaction behaviour remain correct in the local experiment.
- [ ] Existing decorator semantics, boundary visibility, source identity, and anchored ownership remain intact.
- [ ] Documentation and required clean-ioc checks pass; actual verification results and limitations are recorded.
- [ ] Public documentation uses independently authored standalone examples and does not reference or adapt bark-core code.
- [ ] A fresh Luna Low documentation reader has reviewed the final docs and passed the subsequent uncoached comprehension quiz.
- [ ] bark-core has no task-created commits; any remaining local test-bed changes are explicitly listed.

Out of scope: runtime hot registration, structural protocol discovery, infinite/open-generic source expansion, generic
registration event hooks, automatic distributed transactions, and a committed bark-core migration.
