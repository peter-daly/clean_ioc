# 01 — Artifact integration for unified container and scoped slots

Created: 2026-10-09\
Updated: 2026-10-16\
Status: Not ready — ordinary slot support implemented; artifact contracts remain\
Assignment: Unassigned\
Prerequisites: [Standalone item 23](../23-unified-slots.md); artifact format in task 06

## Standalone feature extracted

The original unified-slot proposal now lives in
[item 23 — Unified container and scoped slots](../23-unified-slots.md).
On 2026-10-16 the maintainer requested it as an ordinary container feature,
useful even if pre-compilation is never implemented. That item is the canonical
source for the public API, selection and binding rules, lifetime contract,
recorded design decisions and normal-runtime acceptance criteria.

The agreed rules are preserved there: a slot with `when` requires an explicit
stable binding, and ambiguous slot selection fails before build success.
Normal slot support does not depend on this artifact task. Item 23 is implemented
and independently reviewed; its [result](../23-result.md) and frozen readiness
contract are the ordinary baseline. This artifact task remains unassigned.

## Outcome

Preserve the standalone slot contract across artifact export and loading.
Loaded containers accept startup instances through the same `provide()` API as
normally built containers, without serializing those instances or recompiling.

## Readiness and remaining decisions

- Reuse item 23's implemented slot semantics and normal runtime contract; that
  ordinary-feature prerequisite is complete.
- Agree task 06's representation of type references, frozen bindings and required
  inputs. Reuse item 23's contracts rather than defining artifact-only lifetimes.
- Coordinate supported feature combinations with task 02 and loaded startup
  transitions with task 07. Ordinary overlay semantics belong to item 23;
  artifact-backed overlays remain a separate first-delivery decision.

## Artifact work

- Extend the private codec from its current no-slot subset. Persist frozen slot
  definitions, selection metadata, lifetime and stable binding identities,
  imported type references, required-input contracts and selected execution bindings.
- Never persist supplied instances, environment values, sockets, live scope
  state or runtime caches.
- Load fresh, unprovided runtime state and use ordinary provisioning. Loading
  must not construct registrations, inspect dependencies, replay selection
  callbacks or recompile a graph to connect a supplied value.
- Preserve normal container/scoped ownership, inheritance, override rules,
  singleton capture validation, locks and errors in all supported metadata modes.
- Slots change values within frozen wiring. Environment choices that change
  registrations or decorators remain task 05's graph-variant concern.

## Verification and acceptance

- [ ] Independent-process export/load accepts different startup values without
  recompilation, using the same public provisioning API as ordinary builds.
- [ ] Tests guard compiler and selection entry points during loading and prove
  supplied instances and values are absent from the artifact.
- [ ] Normal and loaded containers agree on binding choices, required-input
  checks, lifetime rules, provider behaviour, warmup and provision failures.
- [ ] Full/reduced metadata and diagnostics modes preserve supported semantics.
- [ ] Repeated artifact comparisons include both slot lifetimes and separately
  record preparation time, current/peak RSS, traced retention/peak and resolution.
- [ ] Unsupported combinations fail clearly; documentation and results identify
  the supported subset without blocking standalone item 23's delivery.

## Starting points

- [Standalone slot contract](../23-unified-slots.md).
- [Artifact codec](../../benchmarks/graph_artifact.py),
  [artifact tests](../../tests/test_graph_artifact_experiment.py) and
  [previous retest](../graph-memory-optimization/artifact-retest-post05.md).
- [Artifact format](06-artifact-format-and-packaging.md) and
  [loading and startup](07-loading-and-startup.md).
