# Resource ownership proof

Status: Done
Priority: P0
Dependencies: None
Blocks: Typed deferred dependencies

## Summary

Compile an explicit cache and cleanup owner for every component occurrence, close gaps around cleanup-bearing transient
dependencies and runtime-context capture, and expose a redacted `OwnershipReport` that proves why every resource owner
is safe.

## Problem and differentiation

V2 validates static captive lifespans and assigns generator/context-manager finalizers to runtime owners. Two cases need
stronger semantics:

- a cleanup-bearing transient may be created while activating a cached component whose owner differs from the current
  resolving scope, especially with scope overlays and inherited singletons;
- `Scope` and `ResolutionContext` allow later dynamic resolution, so their effective lifetimes must participate in
  captive validation rather than being treated as ordinary values.

Resource ownership should be a compiler result, not an inference made from mutable activation stacks. An inspectable
proof distinguishes Clean IoC from containers that merely promise cleanup when a scope exits.

## Goals

- Assign cache, instance, and cleanup owners to every occurrence during compilation.
- Keep cleanup-bearing transients below singletons valid when ownership can be promoted safely.
- Reject cached capture of a shorter-lived `Scope` or `ResolutionContext`.
- Make runtime finalizer routing execute the compiled ownership decision.
- Show ownership and complete justification paths without runtime identities or values.
- Attempt every finalizer in reverse activation order even when earlier finalizers fail.

## Non-goals

- Garbage-collection finalizers or weak-reference cleanup.
- Automatically closing arbitrary user objects that were not created by a generator or context manager.
- Tracking resources created outside compiled activation steps.
- Extending a scope's lifetime because an object or provider escaped it.
- Treating cleanup success as proof of application-level transaction correctness.

## User stories

- A singleton owns a transient context-manager client and both are finalized by the singleton's declaring container.
- A scoped repository owns a transient session helper and both close with the request scope.
- A build fails because a singleton captures `Scope` or a scoped object captures `ResolutionContext`.
- Tooling shows the cache and cleanup owner for every component under an entry point.
- Multiple cleanup failures do not prevent remaining resources from being finalized.

## Ownership model

Add stable public owner categories:

```python
from dataclasses import dataclass
from enum import Enum


class RuntimeOwnerKind(str, Enum):
    none = "none"
    resolution = "resolution"
    scope = "scope"
    singleton = "singleton"
    supplied = "supplied"


@dataclass(frozen=True, slots=True)
class OwnershipRecord:
    component: Component
    path: tuple[str, ...]
    cache_owner: RuntimeOwnerKind
    cleanup_owner: RuntimeOwnerKind
    owner_component: Component | None
    reason: str


@dataclass(frozen=True, slots=True)
class OwnershipReport:
    records: tuple[OwnershipRecord, ...]
    issues: tuple[BuildIssue, ...]

    @property
    def is_valid(self) -> bool: ...
    def to_text(self) -> str: ...
    def to_json(self, *, indent: int | None = 2) -> str: ...
```

`CompiledGraph.ownership_report()` returns the frozen report produced during the successful build. It does not walk
runtime caches. `ContainerBuildError.report` remains the authoritative failure report; an invalid partial ownership
report is available only in structured diagnostic tooling.

The categories mean:

| Component behavior | Cache owner | Cleanup owner |
| --- | --- | --- |
| Plain transient | None | None |
| Cleanup-bearing transient below a singleton activation | None | That singleton's owner |
| Other cleanup-bearing transient | None | Current resolving scope |
| Once per graph without cleanup | Resolution | None |
| Once per graph with cleanup | Resolution | Current resolving scope |
| Scoped | Scope | Current resolving scope |
| Singleton | Singleton | Declaring root or overlay singleton owner |
| Scope-slot supplied value | Supplied | None |

Decorators inherit the effective instance and cleanup owner of the registration they decorate. Pre-configuration
resources retain the owner token of the layer that declared the definition, as V2 already requires.

`owner_component` is the nearest compiled cached ancestor that caused owner promotion. It is `None` when ownership comes
directly from the resolving scope, resolution context, or external provision.

## Compiler algorithm

Ownership is calculated after the component graph and captive-lifespan paths are complete but before `_PlanSet` is
frozen:

1. Traverse each occurrence with its nearest cached ancestor and declaring owner token.
2. Assign the component's cache owner from its lifespan or synthetic kind.
3. Assign cleanup to the nearest owner guaranteed to outlive the created resource.
4. Promote a cleanup-bearing transient below a singleton to that singleton's declaring owner, including through plain
   transient components and decorators.
5. Keep scoped and ordinary transient cleanup on the current scope; both close at that scope boundary.
6. Validate special runtime-context edges using their effective lifespans.
7. Freeze an owner descriptor directly into every activation step that may register a finalizer.

Runtime `add_finalizer()` receives that descriptor. It no longer decides ownership by inspecting the declared lifespan
and current activation stack. Owner tokens remain private runtime identifiers and never enter public reports.

If one registration appears in different contexts, each occurrence may have a different compiled cleanup owner. This is
why ownership belongs to the occurrence graph rather than the mutable registration definition.

## Runtime-context capture

Treat special runtime dependencies as explicit component lifetimes:

- `ResolutionContext` has effective lifespan `once_per_graph`. A scoped or singleton component cannot capture it,
  directly or transitively. It remains valid in transient and once-per-graph components during their activation call.
- `Scope` has effective lifespan `scoped`. A singleton cannot capture it. Scoped, once-per-graph, and transient
  components may receive the current scope.
- Scope-slot values retain their declared graph position and effective scope lifetime. Singletons cannot depend on them.
- A runtime context may select only already compiled roots, but that fact does not extend the context's lifetime.

The same rules apply through constructors, factories, decorators, collections, argument-selected edges, and
pre-configuration dependencies. Error paths include the complete semantic route to the special component.

Typed providers do not capture `ResolutionContext`; they bind an explicit `Scope`. Their additional singleton-target
restrictions are defined in the deferred-dependency proposal.

## Closing and failure behavior

Scopes and singleton owners remain idempotently closeable. On close:

- finalizers run in reverse successful-acquisition order;
- every finalizer is attempted even if another fails;
- one finalizer failure is re-raised unchanged after remaining finalizers run;
- multiple failures are raised as a native Python 3.11 `ExceptionGroup` in finalization order;
- async close awaits each finalizer in order and applies the same aggregation;
- a synchronous close encountering an async finalizer retains the existing explicit error, continues eligible sync
  finalizers, and includes all failures in the final aggregation.

After close, `resolve`, `resolve_async`, `provide`, `new_scope`, and typed-provider calls fail with `ScopeClosedError`.
Closing a parent does not silently close independently owned children; framework integrations remain responsible for
properly nesting scope contexts.

## Graph manifests

Ownership changes executable cleanup behavior and must be reviewable. Introduce graph-manifest schema version 2 with
these additional node fields:

- `cache_owner`: one `RuntimeOwnerKind` value;
- `cleanup_owner`: one `RuntimeOwnerKind` value;
- `owner_path`: the semantic manifest path of the owning component when applicable.

`GraphManifest.from_json()` continues to read schema version 1. Missing ownership fields in a v1 baseline are classified
as unknown ownership, not inferred. Writing uses schema version 2 once the ownership compiler ships. Fingerprints change
because ownership is executable architecture. No runtime owner token, scope ID, object ID, or value is serialized.

## Diagnostics and error codes

- `captive-resolution-context`: scoped or singleton capture of `ResolutionContext`.
- `captive-runtime-scope`: singleton capture of `Scope` or a scope slot.
- `unsafe-cleanup-owner`: no owner can be proven to outlive a cleanup-bearing occurrence.
- `cleanup-owner-conflict`: cloned or anchored activation metadata disagrees with its frozen owner descriptor.
- `ScopeClosedError`: a runtime operation targets a closed owner.

Captive errors aggregate with existing `captive-dependency` findings but retain their more specific codes. The full path
is present in `BuildIssue.path` and the ownership report.

## Privacy and security

- Reports contain public component metadata, semantic paths, and owner categories only.
- Owner tokens, scope UUIDs, runtime cache keys, object identities, values, finalizer representations, and build inputs
  are excluded.
- Cleanup exception objects are propagated to the caller but are never copied into graph reports or manifests.
- Source links, when available, follow the provenance proposal and remain outside fingerprints.

## Compatibility

Most valid graphs retain their behavior. Newly rejected runtime-context captures are intentional hardening during the V2
beta. Cleanup-bearing transients below singletons remain supported through explicit owner promotion. The manifest writer
moves to schema version 2 while retaining v1 read compatibility.

## Rejected alternatives

- **Reject every cleanup-bearing transient below a singleton:** occurrence-specific owner promotion is safe and preserves
  useful transient construction semantics.
- **Attach all finalizers to the current scope:** an overlay descendant could close before a parent-owned singleton.
- **Infer ownership from runtime stacks:** the static graph would not describe the actual cleanup path.
- **Let cached components capture `ResolutionContext`:** a per-resolution object cannot safely outlive its resolution.
- **Stop cleanup on the first error:** later resources would leak and obscure the complete failure.

## Rollout

1. Add the ownership compiler and compare its decisions with current runtime routing in tests.
2. Enforce runtime-context capture rules and compiled finalizer routing.
3. Add complete cleanup failure aggregation and closed-scope enforcement.
4. Publish `OwnershipReport`, manifest schema 2, renderers, and semantic diff support.
5. Unblock typed deferred dependencies after every ownership acceptance test passes.

## Acceptance tests

- Prove cache and cleanup owners for every lifespan at root, ordinary child scope, nested scope, and compiled overlay.
- Cover cleanup-bearing transients directly and transitively below scoped and singleton components.
- Verify inherited parent singleton cleanup stays with the root owner when first resolved from an overlay descendant.
- Verify overlay singleton cleanup stays with the built overlay when first resolved from a nested ordinary scope.
- Validate `Scope`, `ResolutionContext`, and scope-slot capture through every compiled edge type.
- Run all sync and async finalizers in reverse acquisition order and aggregate one or multiple failures correctly.
- Reject all runtime operations after close and preserve idempotent repeated close.
- Render deterministic ownership reports without activating components.
- Read schema-v1 manifests, write schema v2, classify ownership changes, and reject unsupported schemas.
- Prove reports and manifests contain no owner tokens, UUIDs, cache keys, values, finalizers, or build inputs.
