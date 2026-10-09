---
description: Classify dependency graph changes and enforce acceptance policies in tests and CI.
---

# Graph-change policies

Use a graph-change policy when a newly compiled dependency graph must be compared with a previously accepted graph.
Ordinary validation rules check the current architecture. A `DiffPolicy` checks the changes between two architectures:
both graphs can build successfully while the comparison rejects a changed lifespan, removed decorator, or new capability.

## Compare and evaluate

This complete example replaces a repository implementation and permits that specific kind of change beneath the
checkout entry point:

```python
from clean_ioc import ContainerBuilder
from clean_ioc.tooling import ChangeAllowance, ChangeRisk, DiffPolicy, GraphChangeKind, GraphManifest


class Repository:
    pass


class SqlRepository(Repository):
    pass


class NewRepository(Repository):
    pass


class Checkout:
    def __init__(self, repository: Repository):
        self.repository = repository


def make_graph(implementation):
    builder = ContainerBuilder()
    builder.register(Repository, implementation)
    builder.register(Checkout, root_policy="entrypoint")
    return builder.build().graph


baseline = GraphManifest.from_json(make_graph(SqlRepository).manifest().to_json())
graph = make_graph(NewRepository)
difference = graph.diff(baseline)

report = difference.evaluate(DiffPolicy(fail_at=ChangeRisk.high))
assert not report.is_valid
assert report.violations[0].kind is GraphChangeKind.implementation_changed

policy = DiffPolicy(
    fail_at=ChangeRisk.medium,
    deny_kinds=frozenset({GraphChangeKind.lifespan_changed}),
    allowances=(
        ChangeAllowance(
            kind=GraphChangeKind.implementation_changed,
            path_glob="root:*Checkout:default:0/dependency:repository:*",
            maximum_risk=ChangeRisk.high,
        ),
    ),
)
accepted = difference.evaluate(policy)
assert accepted.is_valid
assert accepted.changes == report.changes
print(accepted.to_text())
```

`CompiledGraph.diff(baseline, all_roots=False)` includes the current graph's known entry-point context.
`GraphManifest.diff(baseline)` also classifies changes, using only the information in the two manifests.
Comparisons and policy evaluation use captured graph metadata without running constructors, factories, filters,
derivations, or validation rules again. Building the graph follows the normal compilation rules.

Use `difference.semantic_changes`, `to_semantic_dict()`, `to_semantic_json()`, or `to_semantic_text()` to inspect the
classification. Every `SemanticGraphChange` includes its occurrence path, kind, risk, changed fields, before/after
metadata, affected root paths, affected entry-point paths, and entry-point knowledge status.
Text groups identical changes under several roots; JSON retains every occurrence for precise policy evaluation.

`DiffPolicyReport` exposes `changes`, `violations`, and `is_valid`, with `to_dict()`, `to_json()`, and `to_text()` renderers.
It retains permitted changes as well as violations. The existing raw `GraphDiff` renderers, fields, and JSON shape
remain available, including the earlier boundary findings in raw `semantic_changes` JSON.
The Python `GraphDiff.semantic_changes` property now contains the complete classified records.

## Classification and risk

One changed component may produce several findings. A lifespan change and a new capability tag are independent
concerns, even when they occur at the same path. Implementation and implementation-type fields belong to one concern.
Renamed dependency paths at the same parent relationship and ordinal are compared as replacements when their component
roles match; their original added and removed paths remain in the raw diff.

| Change | Default risk |
| --- | --- |
| Root or dependency removed | High |
| Implementation, activation, lifespan, async requirement, or cleanup changed | High |
| Service type replaced | High |
| Decorator or pre-configuration removed or replaced | High |
| Capability tag added, removed, or changed | High |
| Root, dependency, decorator, or pre-configuration added | Medium |
| Name, ordinary tags, position, or ordering changed | Medium |
| Unknown metadata changed or an unknown relationship added | Medium |
| Added root known to be unmarked and unreachable from every marked entry point | Low |

Provider mode, deferred target, and per-call scope policy changes are activation changes. Cache-owner changes are
lifespan changes; cleanup-owner and promoted-owner-path changes are cleanup changes.
Tags named `capability` are classified separately from ordinary selection tags. A capability introduced on a new
component still produces a high-risk capability finding.
Unknown metadata values are omitted from classified reports; their field names remain visible, and raw diffs retain
the original data.

Boundary additions, removals, access declarations, exposure declarations, component movement, and newly observed
visibility bypasses are classified too. Existing raw boundary risks remain unchanged. Classified bypasses use the
high tier, which is the highest `ChangeRisk`, instead of the earlier raw `critical` label.

Risk is a conservative description of wiring changes. It does not prove application behavior is compatible and does
not inspect changes inside implementation source code or package versions.

## Acceptance rules

`DiffPolicy()` defaults to `fail_at=ChangeRisk.medium`: medium and high changes fail. A high threshold permits low and
medium changes. A low threshold flags every classified change.

- `deny_kinds` always rejects those kinds, even if an allowance matches.
- An allowance matches an optional exact kind and a case-sensitive shell-style path glob.
- `maximum_risk` is the highest tier that the matching allowance permits above the normal threshold.
- The path with the most literal characters wins. Wildcards and character classes do not count as literal characters.
- Equally specific matching allowances use declaration order, with the first match winning.

Allowances do not lower the normal threshold or remove findings. Use `deny_kinds` to reject a kind that would otherwise
fall below the threshold. Keep allowances narrow: permitting an implementation-change kind at a path permits any
replacement of that kind at that path, rather than pinning a particular implementation.

Policy definitions use `GraphChangeKind` and `ChangeRisk` enum values. Invalid definitions raise `ValueError` with
`diff-policy-invalid`. Policy records are frozen; supplied rule collections are captured as tuples and frozensets.

## Entry-point knowledge

The default manifest view includes marked entry points when any are declared. Changes beneath those roots identify
the affected entry points. Comparing through `CompiledGraph.diff()` additionally knows the current markers in an
all-roots view, and can identify low-risk additions of unreachable, unmarked roots.
Named and collection entry-point requests retain their marker paths in these comparisons, even when their ordinary
all-roots paths use a different requested type.

An all-roots saved manifest does not retain the old markers. For a removed occurrence from such a baseline,
`affected_roots` still identifies its old root, but `affected_entrypoints` is empty and `entrypoint_status` is
`"unknown"`. Text reports that membership is unknown. An empty list with unknown status must not be interpreted as
proof that no entry point was affected. Standalone all-roots manifest comparisons also treat current membership as
unknown and keep additions at medium risk when reachability cannot be established.

## CLI and CI

Save a baseline using the existing graph command, then classify changes or evaluate a policy:

```console
clean-ioc graph my_app.composition:make_builder --format json -o baseline.json
clean-ioc diff my_app.composition:make_builder baseline.json --classify
clean-ioc diff my_app.composition:make_builder baseline.json --fail-on high --format json -o changes.json
clean-ioc diff my_app.composition:make_builder baseline.json --policy my_app.architecture:graph_diff_policy
```

`--fail-on` and `--policy` imply classified output and cannot be combined. The policy locator names a `DiffPolicy`
object. The composition target supports the same builders, built scopes, and zero-argument factories as other tooling
commands. Use `--all` consistently when saving and comparing an all-roots baseline.

| Mode | Exit 0 | Exit 1 | Exit 2 |
| --- | --- | --- | --- |
| Raw diff or `--classify` | No changes | Any graph change or build failure | Invalid input or output |
| `--fail-on` or `--policy` | Policy passes, including permitted changes | Policy violation or build failure | Invalid policy, locator, manifest, or output |

Text and JSON formats are supported. Failed builds return their normal build findings; they do not produce a partial
graph comparison. `-o` writes a successful comparison or policy report to a file; it does not update the baseline.

For PR checks, CI can build the base revision and save its manifest, then build the PR revision and compare it with that
file. It can also download a matching baseline artifact previously produced by the target branch. Checkout and artifact
management belong to the workflow; Clean IoC consumes the baseline file. Review a baseline change explicitly when an
architectural change is accepted.

Graph manifests, classified JSON, and policy JSON remain unversioned in this release candidate. No policy or risk metadata is added
to graph manifests or fingerprints. Reports derived from compiled graphs retain the existing exclusion of configured
values, build arguments, provenance, runtime identities, and absolute source paths.
