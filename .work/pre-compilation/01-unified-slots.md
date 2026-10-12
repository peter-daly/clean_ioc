# 01 — Unified container and scoped slots

Created: 2026-10-09\
Status: Not ready — remaining slot semantics need refinement\
Assignment: Unassigned\
Prerequisite: Existing scoped provisions, compiled contextual selection and reduced runtimes

## Outcome

Provide one slot declaration API for values supplied after compilation, with
explicit container or scoped lifetime. This supports application-startup instances
such as environment-derived configuration and externally created clients without
serializing those instances into a precompiled artifact.

Implement normal compilation and provisioning first, then extend the local
artifact experiment to preserve the same declaration, binding and execution
semantics. This is a task plan only; no implementation has been requested yet.

## Readiness and remaining decisions

The unified declaration direction, names/tags, explicit binding for `when`, and
build-time ambiguity failure are agreed. Preserve those rules. Before
implementation, refine these remaining cases in this task:

- When may compatible declarations intentionally share a binding, and when is
  that an accidental duplicate? Specify how named/tagged views of one binding
  behave in single-value and collection selection.
- Confirm caller-owned supplied values as the initial ownership policy and
  preserve existing scoped-provision behaviour.
- Define which frozen targets make a container input required, including
  deferred providers and optional startup targets. Coordinate the enforcement
  point with [task 07](07-loading-and-startup.md).
- Specify slot-versus-registration precedence and implicit provisioning lookup
  for conditional slots so a shorthand cannot bypass contextual selection.
- Set the rule for new container slots in normal `ScopeBuilder` overlays after
  an ancestor begins resolving. Artifact overlay support remains a separate
  first-delivery decision in [task 02](02-feature-coverage.md).

These are design refinements; no further approval of the already-agreed rules is
needed. Record the answers here before marking the task ready for implementation.
Normal slot support can then proceed independently of the artifact codec; artifact
integration depends on [task 06](06-artifact-format-and-packaging.md).

## Proposed public API

The unified method accepts a service type, an explicit scope, optional name and
tags, an optional stable binding key, and an optional contextual `when` predicate.
Reuse the existing `Tag` model and component filters.

```python
builder.declare_slot(AppConfig, scope="container")
builder.declare_slot(RequestContext, scope="scoped", tags=[Tag("request")])

builder.declare_slot(
    Client,
    scope="container",
    name="primary",
    tags=[Tag("external")],
    binding="payments.client",
    when=cf.parent(cf.service_type_is(PaymentsWorker)),
)
builder.declare_slot(
    Client,
    scope="container",
    name="primary",
    tags=[Tag("external")],
    binding="refunds.client",
    when=cf.parent(cf.service_type_is(RefundsWorker)),
)
```

Both compiled and loaded containers use the same provisioning API:

```python
container.provide(AppConfig, AppConfig.from_env())
container.provide(Client, payments_client, binding="payments.client")
container.provide(Client, refunds_client, binding="refunds.client")

with container.new_scope() as scope:
    scope.provide(RequestContext, request_context)
    worker = scope.resolve(PaymentsWorker)
```

Preserve `declare_scope_slot(service_type, name=None)` as the compatibility
shorthand for `declare_slot(..., scope="scoped")`. Keep simple
`provide(service_type, value, name=...)` calls when they identify one binding.
Do not silently choose or populate multiple bindings when that shorthand is
ambiguous. A typed `SlotKey[T]` may be considered as a convenience; a stable
application-defined key is the required concept, not a builder-only object handle.

## Agreed selection and binding rules

1. **A slot with `when` must have an explicit `binding`.** Reject an explicit
   conditional declaration without one before the build can succeed.
2. Type, name, tags and `when` determine slot eligibility in a dependency's
   compiled context. Evaluate `when` against the contextual slot Component,
   following the existing `cf.parent(...)` semantics. Provider and collection
   wrapper nodes remain real parents; do not add implicit ancestor searching.
3. A binding identifies an application input across compilation, export and
   loading. It is independent of internal registration/component IDs and graph
   occurrence numbers. Several occurrences can refer to the same binding.
4. Names and tags are selection metadata, not unique slot identity. Slots may
   share a service type, name and tags when contextual selection is unambiguous
   and their supplied values have distinct, stable binding identities.
5. Without an explicit binding, retain `(service_type, name)` as the implicit
   provisioning identity. Validate ambiguous implicit identities before build
   success; do not defer declaration ambiguity to application startup.
6. **Before a build succeeds, fail ambiguous slot selection.** For each compiled
   single-valued dependency satisfied by slots, exactly one eligible slot must
   remain. Different binding keys do not break selection ties, and declaration
   order must not choose between overlapping eligible slots.
7. Check actual compiled dependency contexts. Do not compare callback identity,
   serialize predicate closures, or claim to prove arbitrary predicates disjoint
   for every possible future parent. Later scope-builder compilation must run
   the same validation for its new contexts.
8. Binding contracts must be consistent. Reject incompatible service types or
   lifetimes attached to the same explicit binding. Define intentional reuse of
   compatible declarations separately from accidental duplicate declarations.
9. Successful compilation freezes the selected binding on the dependency's
   execution plan. Resolution and artifact loading do not rerun `when`.

Ambiguity errors should identify the consumer, parameter, service, matching slot
names/bindings and available declaration origins. Existing failed-build evidence
and error aggregation must remain useful with diagnostics enabled or disabled.

## Lifetime and provisioning contract

| Behaviour | Container slot | Scoped slot |
| --- | --- | --- |
| Stored value | One binding per owning container | One binding per supplying scope |
| Descendants | Receive the same instance | Inherit unless overridden locally |
| Child-scope override | Rejected | Allowed before that scope starts resolving |
| Singleton capture | Allowed | Rejected under existing captive-scope checks |
| Provision lock | Before first resolution or warmup through the container or any descendant | Before the supplying scope's first resolution |

The declaration fixes the lifetime; supplying a scoped slot on the root container
does not convert it into a container slot. Preserve existing undeclared-slot,
duplicate-provision, closed-scope and locked-provision errors with clear binding
identification. Names, tags, scope and binding declarations are immutable after
compilation and cannot be changed by `provide()`.

Container slots must be supplied on their owning container; descendant scopes
must not create competing container values. Define and validate the behaviour of
new container-slot declarations in scope-builder overlays, particularly after an
ancestor has started resolving. Never mutate or reopen a sealed ancestor binding.

Plan a readiness check that reports missing required container bindings together
before activation/warmup. Scoped values remain supplyable when their respective
scopes are created; loading cannot require request values that do not yet exist.
Specify which frozen targets make a container binding required, including deferred
providers, so this rule does not depend on replaying application callbacks.

The proposed initial ownership policy is caller-owned supplied instances. Do not
automatically close or enter a provided object. Container-managed ownership would
need an explicit policy. Confirm and document this against existing instance and
scoped-provision behaviour during implementation.

## Compiler and artifact work

- Replace the bare scoped `(type, name)` declaration model with frozen slot
  definitions containing the required selection, lifetime and binding metadata.
  Normalize aliases consistently with existing registration and provision lookup.
- Define slot-versus-registration selection precedence explicitly. Preserve
  existing scope-slot fallback behaviour unless an intentional change is
  documented; slot ambiguity checks must not silently alter unrelated registration
  selection or collection cardinality rules.
- Compile container and scoped lookup steps with the correct ownership proof.
  Ensure slots work through constructors, decorators, argument selectors and
  deferred provider/map targets without changing sharing or cleanup semantics.
- Retain names/tags/context required by runtime filters with
  `explain_metadata=False`; do not retain complete explanation histories solely
  to support late provisioning.
- Extend the private artifact codec from its current no-slot subset. Persist
  declarations, required-binding contracts, imported type references and selected
  execution bindings. Never persist supplied instances, environment values,
  sockets, live scope state or runtime caches.
- Load into an unprovided runtime, then use the ordinary provisioning path.
  No registration construction, dependency inspection, selection callback replay
  or graph recompilation may be needed to connect a supplied value.
- Compile-time environment choices that change registrations/decorators still
  need separate graph variants or another explicit design. Slots change values
  within frozen wiring; they do not make wiring environment-dependent at load.

## Starting points

- [Scope documentation](../../docs/scopes.md) and
  [lifetime validation](../../docs/lifespans.md).
- `_Blueprint.slot_definitions`, `_matching_slot`, `_ProvidedStep`, declaration
  methods, `Scope.provide`, `_find_provision` and singleton capture validation in
  [container.py](../../clean_ioc/container.py).
- Component metadata in [components.py](../../clean_ioc/components.py) and
  [component filters](../../clean_ioc/component_filters.py).
- Existing cases in [test_container.py](../../tests/test_container.py),
  [alias lookup tests](../../tests/test_type_alias_lookup_paths.py) and
  [reduced-runtime tests](../../tests/test_optional_explanation_metadata.py).
- The [artifact codec](../../benchmarks/graph_artifact.py),
  [artifact tests](../../tests/test_graph_artifact_experiment.py) and
  [previous retest](../graph-memory-optimization/artifact-retest-post05.md).

## Verification and acceptance

- [ ] Normal compilation supports the unified declaration API, names/tags,
  stable bindings and both lifetimes; existing scoped APIs remain compatible.
- [ ] A `when` without a binding fails. Identical type/name/tags with disjoint
  parent conditions succeeds; overlapping eligible slots fail compilation with
  useful evidence. Different keys do not hide overlap.
- [ ] Duplicate implicit identities and incompatible binding contracts fail
  before build success; no exported artifact contains unresolved slot ambiguity.
- [ ] Singleton/container sharing, scoped inheritance/overrides, provision locks,
  missing values, warmups and cleanup ownership behave as documented across
  ordinary scopes, overlays and sync/async resolution.
- [ ] Tests cover aliases, named and tagged selection, parent contexts, providers
  and maps, and boundaries where supported. Unsupported combinations fail clearly.
- [ ] Full and reduced metadata modes, with diagnostics on/off, preserve the
  same binding choices and runtime behaviour without callback replay.
- [ ] Independent-process export/load accepts different startup values without
  recompilation. Tests guard compilation/selection entry points during loading
  and verify that instances and their values are absent from the artifact.
- [ ] A fresh repeated artifact comparison includes container and scoped slots,
  preserves previous evidence, and records preparation time, current/peak RSS,
  traced retention/peak and resolution behaviour separately.
- [ ] Required checks, executable documentation and a result report are complete
  before the task is marked implemented. No agent is assigned by this document.
