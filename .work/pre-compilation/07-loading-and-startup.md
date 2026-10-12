# 07 — Loading, provisioning and startup

Created: 2026-10-09\
Status: Not ready — required-input and startup lifecycle needs refinement\
Assignment: Unassigned\
Prerequisites: Slot contract in 01; state/format contracts in 04 and 06

## Outcome

Give loaded containers an explicit path from verified artifact to supplied inputs,
validated readiness and optional warmup, with equivalent normal-build behaviour.
Loading itself must not activate application services or acquire resources.

## Readiness and remaining decisions

- Define what makes a container slot required: all exported roots, declared
  startup roots, warmup targets, deferred providers or another frozen contract.
  Coordinate with task 01; unused/request-only inputs must have deliberate rules.
- Decide the public validation/startup entry points and when supplying values is
  sealed. Preserve the agreed lock before first resolution/warmup through any
  descendant; startup checks must not create an override path.
- Specify retry behaviour after missing provisions, failed validation or failed
  warmup, using existing warmup semantics where applicable.
- Decide whether warmup support is required in the first delivery and how named
  frozen plans are selected without replaying their declaration callbacks.

Record a state-transition table and failure behaviour before implementation.
Startup validation and provisioning should use the same contracts for normal and
loaded containers rather than two competing APIs.

## Proposed sequence

1. Task 06 checks artifact compatibility/integrity and task 03 resolves symbols.
2. Task 04 reconstructs the frozen plan with fresh state and empty provisions.
3. The application supplies task 01's container bindings.
4. An explicit check reports all required missing container bindings together.
5. The application optionally runs selected compiled warmup plans, then serves.

Scoped/request values remain supplyable when those scopes are created. Loading
cannot require values for requests that do not yet exist. Import execution is
distinct from service activation and must be documented accurately.

## Work

- Carry a compact required-binding contract and frozen warmup targets into the
  artifact. Runtime checks consume those facts without traversal of build-only
  metadata, callback replay or dependency selection.
- Implement the agreed public lifecycle and errors, including missing bindings,
  wrong scope, duplicate/late provisions, closed containers and failed warmup.
- Preserve warmup ordering, shared singleton initialization, concurrent requests,
  failure aggregation, retry and resource ownership for the supported subset.
- Keep pre-configurations at their existing activation points; loader validation
  cannot execute one merely to prove an artifact is usable.
- Provide executable application-startup examples for both normal compilation
  and artifact loading, using runtime slot values and ordinary child scopes.

## Verification and acceptance

- [ ] A reviewed lifecycle table covers successful startup and each recoverable
  or terminal failure, including provisioning locks through descendant scopes.
- [ ] Missing required container bindings are reported together before the
  agreed activation boundary; request-scoped values are not required at load.
- [ ] Load and binding validation execute no application factory, initializer,
  resource acquisition, build callback or graph compilation.
- [ ] Warmup, first request and later scopes preserve ordinary cache/ownership
  behaviour, including supported sync/async failures and retries.
- [ ] Useful error context remains available with reduced explanation metadata.

## Starting points

- [Slot task](01-unified-slots.md), [scope documentation](../../docs/scopes.md),
  [warmup documentation](../../docs/warmup-plans.md) and
  [warmup tests](../../tests/test_warmup_plans.py).
- Provisioning, resolution locks, warmup planning and execution in
  [container.py](../../clean_ioc/container.py).
