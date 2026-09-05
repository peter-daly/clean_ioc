# Semantic graph-change policy

Status: Proposal
Priority: P1
Dependencies: Compilation provenance; architecture policy conventions

## Summary

Classify manifest changes by architectural meaning and default risk, identify the roots or entry points affected by each
change, and let CI evaluate those changes against an explicit `DiffPolicy`. Existing schema-version-1 manifests and the
current raw `GraphDiff` interface remain valid.

## Problem and differentiation

The current diff reports paths as added, removed, or changed. A reviewer must inspect raw before/after metadata to learn
whether the change swaps an implementation, changes ownership, adds cleanup, or alters a decorator pipeline. CI can only
fail on every change or none.

A compiler already knows the semantic role of each node and field. Classifying those changes makes the graph manifest a
reviewable architecture contract rather than a generic JSON snapshot.

## Goals

- Classify changes to roots, dependencies, activation, lifespan, async behavior, cleanup, decorators,
  pre-configurations, names, tags, ordering, and future module boundaries.
- Associate each change with affected compiled roots and marked entry points when that information is available.
- Supply conservative default risk levels and an explicit policy override mechanism.
- Keep existing manifests readable and keep the raw diff API/output available.
- Make policy evaluation deterministic, redacted, and suitable for CI.

## Non-goals

- Proving application-level behavioral compatibility.
- Inspecting implementation source diffs or package versions.
- Automatically approving a graph change because its risk is low.
- Storing reviewer approvals inside a graph manifest.
- Assigning risk from runtime telemetry.

## User stories

- CI permits new unreferenced roots but rejects a lifespan or cleanup-owner change.
- A reviewer sees that replacing one repository affects four command handlers and two HTTP entry points.
- A platform team rejects newly introduced `capability=network` tags.
- An old schema-version-1 baseline remains usable after semantic classification ships.

## Public model

Add these immutable types to `clean_ioc.tooling`:

```python
from dataclasses import dataclass
from enum import Enum


class GraphChangeKind(str, Enum):
    root_added = "root-added"
    root_removed = "root-removed"
    dependency_added = "dependency-added"
    dependency_removed = "dependency-removed"
    implementation_changed = "implementation-changed"
    activation_changed = "activation-changed"
    lifespan_changed = "lifespan-changed"
    async_requirement_changed = "async-requirement-changed"
    cleanup_changed = "cleanup-changed"
    decorator_changed = "decorator-changed"
    pre_configuration_changed = "pre-configuration-changed"
    selection_metadata_changed = "selection-metadata-changed"
    capability_changed = "capability-changed"
    order_changed = "order-changed"
    unknown_metadata_changed = "unknown-metadata-changed"


class ChangeRisk(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


@dataclass(frozen=True, slots=True)
class SemanticGraphChange:
    path: str
    kind: GraphChangeKind
    risk: ChangeRisk
    fields: tuple[str, ...]
    affected_roots: tuple[str, ...]
    affected_entrypoints: tuple[str, ...]
    before: dict[str, object] | None
    after: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class ChangeAllowance:
    kind: GraphChangeKind | None = None
    path_glob: str = "*"
    maximum_risk: ChangeRisk = ChangeRisk.high


@dataclass(frozen=True, slots=True)
class DiffPolicy:
    fail_at: ChangeRisk = ChangeRisk.medium
    deny_kinds: frozenset[GraphChangeKind] = frozenset()
    allowances: tuple[ChangeAllowance, ...] = ()


@dataclass(frozen=True, slots=True)
class DiffPolicyReport:
    changes: tuple[SemanticGraphChange, ...]
    violations: tuple[SemanticGraphChange, ...]

    @property
    def is_valid(self) -> bool: ...
```

`GraphDiff.semantic_changes` exposes the deterministic classification. `GraphDiff.evaluate(policy)` returns a
`DiffPolicyReport`. The existing `added`, `removed`, `changed`, `to_dict()`, `to_json()`, and `to_text()` retain their
current shapes. New `to_semantic_dict()`, `to_semantic_json()`, and `to_semantic_text()` methods opt into the richer
format so existing snapshot consumers do not break.

## Classification

Classification compares nodes with the same stable manifest path and expands one raw changed node into one semantic
change per independent concern. For example, changing both lifespan and tags creates two semantic changes.

The default risk table is conservative:

| Change | Default risk |
| --- | --- |
| Removed root or dependency | High |
| Implementation, activation, lifespan, async requirement, or cleanup changed | High |
| Decorator or pre-configuration removed or replaced | High |
| Capability tag added, removed, or changed | High |
| Root, dependency, decorator, or pre-configuration added | Medium |
| Name, non-capability tags, position, or behaviorally significant order changed | Medium |
| New unrecognized metadata field | Medium |
| Added root that is not a marked entry point and is unreachable from all marked entry points | Low |

An addition and removal at the same parent relationship and ordinal position is classified as a replacement when the
semantic role matches. It still retains the raw added and removed paths.

`Tag("capability", value)` receives special treatment. Other tags remain selection metadata because they may affect
filters. Unknown fields never default to low risk.

## Affected roots and entry points

Every manifest path is rooted below a compiled root, so classification always supplies `affected_roots`. When both
manifests use the default `entrypoints` view, those roots are also reported as `affected_entrypoints`.

`CompiledGraph.diff(baseline)` enriches the current side with its marked-entrypoint set. This allows an all-roots diff to
identify current marked entry points affected by an added or changed occurrence. For a removed occurrence present only
in an old schema-version-1 all-roots baseline, the entry-point status is unknowable; `affected_entrypoints` is empty and
the root remains in `affected_roots`. Reports say `unknown`, never `unaffected`.

Occurrence-specific manifest paths mean a shared registration changed under multiple roots appears once for each
affected root. Text output groups identical semantic changes and lists all affected roots, while JSON preserves every
path for exact automation.

## Policy evaluation

Risk ordering is `low < medium < high`. `fail_at=medium` fails on medium and high changes. A denied kind always fails,
regardless of risk. An allowance matches an exact kind or every kind and uses shell-style path matching; it may raise
the accepted risk only for matching changes. The most specific matching allowance wins, measured by the number of
non-wildcard path characters; equal specificity follows declaration order.

Policies never mutate or suppress the underlying diff. `DiffPolicyReport.changes` contains everything and `violations`
contains the failing subset.

## CLI

Existing behavior remains the default:

```bash
clean-ioc diff my_app.composition:application_builder baseline.json
```

Opt into classification or policy evaluation:

```bash
clean-ioc diff my_app.composition:application_builder baseline.json --classify
clean-ioc diff my_app.composition:application_builder baseline.json --fail-on high
clean-ioc diff my_app.composition:application_builder baseline.json --policy my_app.architecture:graph_diff_policy
```

`--policy` loads a `DiffPolicy` from an import locator and is mutually exclusive with `--fail-on`. Both imply
`--classify`. Without a policy, `--classify` retains the current exit behavior: `1` for any change. With a policy, exit
`1` means at least one violation, even if allowed changes remain. Invalid policies and unsupported manifest schemas exit
`2`.

Text and JSON formats are supported. Raw output is unchanged unless classification is requested. Classified JSON has its
own `schema_version: 1` independent of the graph manifest schema.

## Manifest compatibility and privacy

- The classifier reads existing graph-manifest schema version 1 without migration.
- No provenance, policy, risk, or approval data is written into the graph manifest or fingerprint.
- Unknown node fields are preserved in raw changes and conservatively classified.
- Values, build inputs, runtime IDs, absolute source paths, and callable representations remain absent.
- A future manifest schema must ship an explicit classifier adapter; unsupported versions fail clearly.

## Errors and failure modes

- `diff-policy-invalid`: the imported policy has an invalid type, risk, glob, or allowance.
- `diff-classification-unknown`: an unknown structural relationship is conservatively classified; it does not abort.
- `diff-entrypoint-unknown`: informational output for removed nodes whose old entry-point status cannot be recovered.
- A build failure continues to return the normal structured build report rather than a misleading partial diff.

## Rejected alternatives

- **Change the existing `GraphDiff` JSON shape:** existing CI and snapshots should keep working.
- **Treat additions as safe:** a dependency, decorator, or capability addition can change behavior materially.
- **Use a numeric risk score:** named levels are easier to review and keep stable.
- **Store allowlists in the baseline:** a baseline records architecture, while a policy records organizational intent.
- **Guess removed entry-point status:** unknown provenance must remain explicit.

## Rollout

1. Add field-level classification and the semantic Python renderers.
2. Add affected-root grouping and `CompiledGraph.diff(...)` enrichment.
3. Add `DiffPolicy`, deterministic allowances, and CLI controls.
4. Integrate capability and module-boundary kinds as those proposals ship.

## Acceptance tests

- Classify each known node field and relationship independently with the documented default risk.
- Split multi-field changes into deterministically ordered semantic changes.
- Group replacements while preserving raw added and removed paths.
- Identify affected entry points in default manifests and report unknown status for old all-roots baselines.
- Evaluate thresholds, denied kinds, glob allowances, specificity, and declaration-order ties.
- Read current schema-version-1 baselines and reject unsupported schemas.
- Prove the existing raw API and default CLI text/JSON remain byte-for-byte compatible.
- Verify classified JSON schema, import-locator errors, and exit status with allowed and violating changes.
- Prove reports contain no configured values, build inputs, runtime identities, provenance, or absolute paths.
