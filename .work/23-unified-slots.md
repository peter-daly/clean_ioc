# 23 — Unified container and scoped slots

Created: 2026-10-16\
Status: Implemented and independently reviewed — APPROVE / KEEP (target-only API)\
Assignment: GPT-6.1 Sol (`gpt-6.1-sol`), high reasoning; `/root/unified_slots`\
Prerequisite: Existing scoped provisions, compiled contextual selection and reduced runtimes

## Superseding API follow-up (2026-10-16)

The maintainer requested `declare_slot(..., target="scoped"|"container")` and
complete removal of `declare_scope_slot()` and the old `scope=` declaration
keyword. This overrides the initial compatibility direction. Runtime ownership,
selection and provision semantics remain the contract below. Duplicate implicit
declarations are errors everywhere, including overlays. Framework bundle guards
prevent same-builder repeats; overlays inherit setup without reapplying bundles.
Initial review, cost data, validation and source hashes remain historical snapshots;
the result report appends the follow-up verification separately.

## Outcome

Provide one slot declaration API for values supplied after compilation, with
explicit container or scoped lifetime. This supports application-startup instances
such as environment-derived configuration and externally created clients in
ordinary containers built with `ContainerBuilder.build()`.

The maintainer requested this standalone work item on 2026-10-16. Deliver the
feature even if pre-compilation is never implemented. Artifact export/loading,
codecs, packaging and cross-process benchmarks are outside its acceptance gate.
The APIs below are implemented. On 2026-10-16 the maintainer
assigned design refinement, implementation and verification to GPT-6.1 Sol with
high reasoning. Record the remaining decisions before implementing them.

## Design questions (resolved by recorded decisions)

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
  point with ordinary resolution and declared warmup plans. Future artifact
  loading must reuse this contract.
- Specify slot-versus-registration precedence and implicit provisioning lookup
  for conditional slots so a shorthand cannot bypass contextual selection.
- Set the rule for new container slots in normal `ScopeBuilder` overlays after
  an ancestor begins resolving. Ordinary overlays belong to this item; artifact
  overlay support remains a separate delivery decision.

These are design refinements; no further approval of the already-agreed rules is
needed. Record the answers here before marking the task ready for implementation.
This item owns the ordinary slot contract. Future artifact integration consumes
that contract and cannot block this delivery.

## Recorded implementation decisions (2026-10-16)

- Keep registration selection, including existing fallback registrations, ahead
  of slots. Slots fill a remaining hole. Collections use matching slots only
  when no registrations match; this deliberately extends the former empty-slot
  collection behaviour without changing registration collection cardinality.
  Provider/collection wrapper components remain real selection parents.
- Explicit bindings are non-empty strings. A binding has exactly one canonical
  service type and lifetime. Distinct name/tag/conditional views may deliberately
  share it. Matching views of one binding supply one scalar value or one
  collection member (first matching view determines inspection metadata).
  Repeated unconditional identical views and repeated implicit identities are
  declaration errors. An implicit identity cannot collide with any explicit
  binding view, because that would make the implicit input unprovisionable.
  Every implicit declaration is unique; repeating one locally or redeclaring an
  inherited input in an overlay is an error. The maintainer's follow-up removes
  the former idempotent shorthand rather than retaining a compatibility alias.
  Conditional duplicates are assessed in compiled contexts, without comparing
  callback identity. Different matching bindings always fail scalar compilation.
- Implicit provisioning considers every declaration for the canonical type/name,
  including conditional declarations; it requires exactly one binding. Explicit
  binding provisioning ignores selection names/tags, but validates the type.
  Provisioning never executes a selection predicate.
- Supplied values are caller-owned, following existing instance/scoped values;
  no entry, exit or finalizer is inferred from the supplied object's type.
- Required container inputs are the selected container bindings reachable from
  frozen public roots, declared/generated provider roots (including deferred
  targets), and declared warmup targets. A declared input with no executable
  occurrence is optional. There is currently no optional WarmupTarget API; a
  compiled startup target contributes its dependencies even if the application
  elects not to call that warmup. Architecture-only private boundary roots do
  not make an input required. Readiness uses captured inputs, never callbacks.
- Before ordinary resolution or warmup first activates anything, check all those
  required container inputs together. A missing-input failure leaves inputs open
  for repair. On success, seal the owning container even when activation begins
  through a descendant. Scoped inputs retain per-supplying-scope locks.
- Container inputs belong to the root Container. ScopeBuilder overlays may use
  inherited container declarations and add scoped declarations; a new container
  declaration in an overlay is rejected clearly, before or after ancestors
  activate. This intentionally avoids introducing a second container owner or
  mutating/reopening the ancestor. Private boundary slots remain unsupported;
  existing root-slot Use visibility remains supported. Conditional root-slot
  boundary imports require a clear unsupported error rather than predicate
  evaluation against a preparation-only component without its consumer.
- Unconditional slots expose ordinary public roots and provider families, with
  registration precedence preserved for scalar/collection selection and boundary
  imports. Conditional slot root eligibility has no parent; provider targets have
  the actual provider wrapper parent. Runtime root filters remain dynamic; an
  ambiguous root filter raises ScopeProvisionError rather than choosing a binding.
  This does not relax build-time scalar dependency ambiguity checks.
- Conservative managed adapters are not themselves public input demand. Readiness
  traverses frozen public/deferred/warmup closures, adding internal managed root
  adapters only if a reachable managed ResolutionContext can call them. Private
  architecture-only roots therefore cannot make an optional input required.
- A container slot can be a direct warmup target, with no ownership transfer or
  acquisition inferred from its instance. Scoped warmup targets retain ordinary
  non-singleton policy findings in verify().
- Captive scoped-slot checks stay in verify(), consistent with the current
  execution-only build contract. Slot ambiguity and incompatible binding are
  impossible wiring and therefore fail build() as well as verify().

## Public API

The unified method accepts a service type, an explicit target, optional name and
tags, an optional stable binding key, and an optional contextual `when` predicate.
Reuse the existing `Tag` model and component filters.

```python
builder.declare_slot(AppConfig, target="container")
builder.declare_slot(RequestContext, target="scoped", tags=[Tag("request")])

builder.declare_slot(
    Client,
    target="container",
    name="primary",
    tags=[Tag("external")],
    binding="payments.client",
    when=cf.parent(cf.service_type_is(PaymentsWorker)),
)
builder.declare_slot(
    Client,
    target="container",
    name="primary",
    tags=[Tag("external")],
    binding="refunds.client",
    when=cf.parent(cf.service_type_is(RefundsWorker)),
)
```

Normally built containers use the ordinary provisioning API:

```python
container.provide(AppConfig, AppConfig.from_env())
container.provide(Client, payments_client, binding="payments.client")
container.provide(Client, refunds_client, binding="refunds.client")

with container.new_scope() as scope:
    scope.provide(RequestContext, request_context)
    worker = scope.resolve(PaymentsWorker)
```

The required `target` keyword selects `"scoped"` or `"container"`.
The maintainer's follow-up removes `declare_scope_slot()` and the former `scope=`
keyword entirely. Neither remains an accepted spelling or compatibility alias.
Keep simple
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
3. A binding identifies an application input across declaration, compilation and
   provisioning. It is independent of internal registration/component IDs and graph
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
   execution plan. Resolution does not rerun `when`.

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
identification. Names, tags, target and binding declarations are immutable after
compilation and cannot be changed by `provide()`.

Container slots must be supplied on their owning container; descendant scopes
must not create competing container values. Define and validate the behaviour of
new container-slot declarations in scope-builder overlays, particularly after an
ancestor has started resolving. Never mutate or reopen a sealed ancestor binding.

Plan a readiness check that reports missing required container bindings together
before activation/warmup. Scoped values remain supplyable when their respective
scopes are created; readiness checks cannot require future request values.
Specify which frozen targets make a container binding required, including deferred
providers, so this rule does not depend on replaying application callbacks.

The proposed initial ownership policy is caller-owned supplied instances. Do not
automatically close or enter a provided object. Container-managed ownership would
need an explicit policy. Confirm and document this against existing instance and
scoped-provision behaviour during implementation.

## Compiler and runtime work

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
- Reuse ordinary provisioning, activation and warmup paths. Supplied values
  change runtime inputs without changing frozen dependency selection.
- Preserve useful slot metadata in graph inspection, activation obligations and
  lifetime diagnostics. Public reports must not expose supplied values.

## Delivery stages

1. Resolve the remaining semantics above and record examples and failure rules.
2. Add frozen slot definitions and the unified builder API. The follow-up removes
   the old shorthand and requires target=. Compile selection, ambiguity checks
   and lifetime validation.
3. Implement container-owned provision lookup and sealing alongside existing
   scoped inheritance. Integrate required-input checks and warmup behaviour.
4. Verify normal builds, scope-builder overlays, full/reduced runtimes and
   supported dependency paths. Document the public API with executable examples.
5. Record implementation, validation and review results before marking complete.

## Starting points

- [Scope documentation](../docs/scopes.md) and
  [lifetime validation](../docs/lifespans.md).
- `_Blueprint.slot_definitions`, `_matching_slot`, `_ProvidedStep`, declaration
  methods, `Scope.provide`, `_find_provision` and singleton capture validation in
  [container.py](../clean_ioc/container.py).
- Component metadata in [components.py](../clean_ioc/components.py) and
  [component filters](../clean_ioc/component_filters.py).
- Existing cases in [test_container.py](../tests/test_container.py),
  [alias lookup tests](../tests/test_type_alias_lookup_paths.py) and
  [reduced-runtime tests](../tests/test_optional_explanation_metadata.py).
- [Warmup plans](../docs/warmup-plans.md) and
  [warmup tests](../tests/test_warmup_plans.py).

## Verification and acceptance

- [x] Normal compilation supports the unified declaration API, names/tags,
  stable bindings and both lifetimes; only target= is accepted and the old alias
  is absent from builder APIs.
- [x] A `when` without a binding fails. Identical type/name/tags with disjoint
  parent conditions succeeds; overlapping eligible slots fail compilation with
  useful evidence. Different keys do not hide overlap.
- [x] Duplicate implicit identities and incompatible binding contracts fail
  before build success; no successful plan contains unresolved slot ambiguity.
- [x] Singleton/container sharing, scoped inheritance/overrides, provision locks,
  missing values, warmups and cleanup ownership behave as documented across
  ordinary scopes, overlays and sync/async resolution.
- [x] Tests cover aliases, named and tagged selection, parent contexts, providers
  and maps, and boundaries where supported. Unsupported combinations fail clearly.
- [x] Full and reduced metadata modes, with diagnostics on/off, preserve the
  same binding choices and runtime behaviour without callback replay.
- [x] Normal `build()` followed by `provide()` and `resolve()` demonstrates
  both lifetimes without using artifact export or loading.
- [x] Required container-input checks report missing bindings at the agreed
  activation boundary, including defined deferred-provider and warmup cases;
  they do not require future request-scoped values.
- [x] Focused build/resolution checks record any material cost of the new slot
  model, including ordinary scope creation and workloads without slots.
- [x] Required checks, executable documentation and a result report are complete
  before the task is marked implemented.

## Relationship to pre-compilation

Extracted from [pre-compilation task 01](pre-compilation/01-unified-slots.md).
That task now owns only artifact integration: persisting frozen slot declarations
and selected bindings, loading fresh unprovided state, and proving parity with
ordinary containers. It depends on this feature and the artifact contract.
This item has no reverse dependency on pre-compilation.

## Initial implementation and review result

Implemented on 2026-10-16 by GPT-6.1 Sol with high reasoning. A separate
GPT-5.6 Sol high reviewer recommends **APPROVE / KEEP**; all six findings and
the final provision-lookup adjustment are resolved. [Result](23-result.md),
[independent review](23-review.md), [exact validation](23-validation.txt), and
[focused cost evidence](23-slot-cost-evidence.json) record the delivery.

Final `make ci` passes on Python 3.11–3.14: 2,594 passed / 8 skipped on 3.11;
2,599 passed / 3 skipped on 3.12; 2,602 passed on 3.13 and 3.14. The new suite
has 77 cases; executable documentation and strict documentation builds pass.
There is measured additional compilation cost, including a larger public slot
root/provider surface. Scope creation and no-slot resolution show no consistent
material runtime change; no performance saving is claimed. Sources remain local
and uncommitted; artifact integration remains a separate follow-on.

## Superseding follow-up result

The target-only API migration is complete and independently reviewed:
**APPROVE / KEEP**, with no open findings. `declare_scope_slot()` is absent;
`target=` is required on all builder/protocol declarations, and `scope=` is
rejected. Duplicate implicit declarations are no longer idempotent, including
inherited redeclarations. ASGI/FastAPI bundle guards preserve repeated application
on a builder; overlays inherit setup without reapplying those bundles.

The current unified-slot suite has **83 cases**. Focused slot/framework checks
pass **104 tests**. Current Python 3.14.4 `make ci` passes **2,610 tests**, including
Ruff/format/ty, executable docs and benchmark discovery. Strict MkDocs passes.
[Focused independent review](23-target-review.md), appended
[validation](23-validation.txt), and separate
[source hashes](23-target-source-hashes.json) record this follow-up. Initial
matrix/performance/review snapshots remain intact and are superseded only where
they describe the earlier API spelling. No matrix or performance rerun was needed
for this follow-up; no new performance claim is made. No commit or push.
