# 04 — Frozen execution plans and fresh runtime state

Created: 2026-10-09\
Status: Not ready — mutable-state and ownership model needs refinement\
Assignment: Unassigned\
Prerequisites: Task 02's inventory; task 06's contract before loader integration

## Outcome

Persist execution descriptions and construct fresh state for each loaded
container. Preserve intended sharing within a container, isolation between loads,
and existing lifetime, initialization, failure and cleanup behaviour.

## Readiness and remaining refinement

A read-only state audit can proceed when assigned and should inform task 06.
Implementation is not ready until that audit defines the reconstruction model:

- Identify state owned by the container, a scope, a resolution, an initializer
  or an observer, including state currently embedded inside compiled records.
- Define how artifact-local references map to fresh ownership identities while
  preserving shared initializer and cleanup relationships.
- Decide the export boundary: the recommendation is an unresolved, unprovided
  plan, with no snapshotting of a live application. Specify how eligibility is
  checked when provision or pre-configuration state exists without cached services.
- Define whether multiple containers may share an immutable decoded plan safely;
  do not add a decoded-plan cache as part of this task without separate evidence.

The audit feeds the artifact design; reconstruction implementation follows it.
This is a staged dependency, not a requirement that the final codec already exist
before the state model can be investigated.

## Work

1. Inventory fields reachable from the exported plan and classify them as frozen
   execution data, optional metadata or mutable runtime state. Record ownership
   and sharing, not merely whether the field is a dataclass or has slots.
2. Separate pre-configuration descriptions from `_PreConfigurationState` locks,
   completion and in-flight futures. Preserve existing retry/concurrency rules
   and shared initialization within the same owning container.
3. Reconstruct fresh caches, locks, scope/owner identities, provision storage,
   resource/finalizer tracking, warmup state and profiling collectors as needed
   by the supported subset. Persist logical ownership relationships rather than
   carrying a running container's identity into another load.
4. Integrate runtime factory/resource and pre-configuration activation with task
   02's supported steps. Loading creates execution machinery but must not invoke
   application constructors, factories, initializers or resource acquisition.
5. Validate supported sharing and cleanup descriptors before exposing a loaded
   container. Ensure failure while reconstructing a plan does not publish a
   partially usable runtime.

## Verification and acceptance

- [ ] An ownership/state inventory identifies every fresh allocation and every
  deliberately shared immutable record used by the supported feature subset.
- [ ] Two loads of the same artifact in one process have independent singletons,
  slots, locks, initializer completion, observations and cleanup state.
- [ ] Within each load, singleton/scoped/per-resolution sharing and shared
  pre-configuration coordination match ordinary compilation.
- [ ] Supported sync/async activation failures, cancellation, retries, scope
  closing and resource cleanup retain normal semantics.
- [ ] Export rejects disallowed live state and no artifact contains acquired
  resources, cached instances, in-flight operations or observer recordings.
- [ ] Independent-process tests and memory comparisons verify reconstruction
  does not retain the compiler or full explanation graph unnecessarily.

## Starting points

- `_CompiledPreConfiguration`, `_PreConfigurationState`, `_CleanupOwnerDescriptor`,
  `Container` and `Scope` in [container.py](../../clean_ioc/container.py).
- [Pre-configuration documentation](../../docs/pre-configurations.md),
  [managed provider tests](../../tests/test_managed_providers.py) and
  [warmup tests](../../tests/test_warmup_plans.py).
- [Current export/load construction](../../benchmarks/graph_artifact.py) and
  [artifact format task](06-artifact-format-and-packaging.md).
