"""Classification and acceptance policies for captured graph manifests."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Any, Literal, Mapping

if TYPE_CHECKING:
    from .tooling import GraphChange


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
    boundary_added = "boundary-added"
    boundary_removed = "boundary-removed"
    boundary_use_added = "boundary-use-added"
    boundary_use_removed = "boundary-use-removed"
    boundary_exposure_added = "boundary-exposure-added"
    boundary_exposure_removed = "boundary-exposure-removed"
    boundary_component_moved = "boundary-component-moved"
    boundary_bypassed = "boundary-bypassed"


class ChangeRisk(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


_RISK_ORDER = {ChangeRisk.low: 0, ChangeRisk.medium: 1, ChangeRisk.high: 2}


@dataclass(frozen=True, slots=True)
class SemanticGraphChange:
    path: str
    kind: GraphChangeKind
    risk: ChangeRisk
    fields: tuple[str, ...]
    affected_roots: tuple[str, ...]
    affected_entrypoints: tuple[str, ...]
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    entrypoint_status: Literal["known", "unknown"] = "unknown"

    @property
    def category(self) -> str:
        """The spelling used by the earlier boundary-only classifier."""

        return self.kind.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "risk": self.risk.value,
            "fields": list(self.fields),
            "affected_roots": list(self.affected_roots),
            "affected_entrypoints": list(self.affected_entrypoints),
            "entrypoint_status": self.entrypoint_status,
            "before": self.before,
            "after": self.after,
        }


def _validate_glob(value: str) -> None:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("diff-policy-invalid: an allowance requires a non-empty path glob")
    index = 0
    while index < len(value):
        if value[index] == "[":
            end = index + 1
            if end < len(value) and value[end] in "!^":
                end += 1
            if end < len(value) and value[end] == "]":
                end += 1
            closing = value.find("]", end)
            if closing < end:
                raise ValueError("diff-policy-invalid: an allowance has an unclosed character class")
            index = closing
        index += 1


@dataclass(frozen=True, slots=True)
class ChangeAllowance:
    kind: GraphChangeKind | None = None
    path_glob: str = "*"
    maximum_risk: ChangeRisk = ChangeRisk.high

    def __post_init__(self) -> None:
        if self.kind is not None and not isinstance(self.kind, GraphChangeKind):
            raise ValueError("diff-policy-invalid: allowance kind must be a GraphChangeKind")
        if not isinstance(self.maximum_risk, ChangeRisk):
            raise ValueError("diff-policy-invalid: allowance maximum_risk must be a ChangeRisk")
        _validate_glob(self.path_glob)


@dataclass(frozen=True, slots=True)
class DiffPolicy:
    fail_at: ChangeRisk = ChangeRisk.medium
    deny_kinds: frozenset[GraphChangeKind] = frozenset()
    allowances: tuple[ChangeAllowance, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.fail_at, ChangeRisk):
            raise ValueError("diff-policy-invalid: fail_at must be a ChangeRisk")
        try:
            denied = frozenset(self.deny_kinds)
            allowances = tuple(self.allowances)
        except TypeError:
            raise ValueError("diff-policy-invalid: deny_kinds and allowances must be iterable") from None
        if any(not isinstance(kind, GraphChangeKind) for kind in denied):
            raise ValueError("diff-policy-invalid: deny_kinds must contain GraphChangeKind values")
        if any(not isinstance(allowance, ChangeAllowance) for allowance in allowances):
            raise ValueError("diff-policy-invalid: allowances must contain ChangeAllowance values")
        object.__setattr__(self, "deny_kinds", denied)
        object.__setattr__(self, "allowances", allowances)


def semantic_text(changes: tuple[SemanticGraphChange, ...]) -> str:
    if not changes:
        return "Dependency graph is unchanged."
    lines = ["Dependency graph changes:"]
    groups: dict[str, list[SemanticGraphChange]] = {}
    for change in changes:
        # Group identical changes under different roots, retaining their full
        # occurrence paths in JSON and policy evaluation.
        relative = next(
            (change.path[len(root) :] for root in change.affected_roots if change.path.startswith(root)),
            change.path,
        )
        key = json.dumps(
            [relative, change.kind.value, change.risk.value, change.fields, change.before, change.after], sort_keys=True
        )
        groups.setdefault(key, []).append(change)
    for group in groups.values():
        first = group[0]
        roots = sorted({root for item in group for root in item.affected_roots})
        entrypoints = sorted({root for item in group for root in item.affected_entrypoints})
        unknown = any(item.entrypoint_status == "unknown" for item in group)
        lines.append(f"- {first.kind.value} [{first.risk.value}] {first.path}")
        lines.append(f"  Fields: {', '.join(first.fields) or 'structure'}")
        lines.append(f"  Affected roots: {', '.join(roots) or 'none'}")
        membership = ", ".join(entrypoints) or "none"
        lines.append(f"  Affected entry points: {membership}{'; unknown membership' if unknown else ''}")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class DiffPolicyReport:
    changes: tuple[SemanticGraphChange, ...]
    violations: tuple[SemanticGraphChange, ...]

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.is_valid,
            "changes": [change.to_dict() for change in self.changes],
            "violations": [change.to_dict() for change in self.violations],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        status = "passed" if self.is_valid else "failed"
        lines = [f"Graph-change policy {status}: {len(self.violations)} violation(s).", semantic_text(self.changes)]
        if self.violations:
            lines.append("Policy violations:")
            lines.extend(f"- {change.kind.value} [{change.risk.value}] {change.path}" for change in self.violations)
        return "\n".join(lines)


def evaluate(changes: tuple[SemanticGraphChange, ...], policy: DiffPolicy) -> DiffPolicyReport:
    if not isinstance(policy, DiffPolicy):
        raise ValueError("diff-policy-invalid: policy must be a DiffPolicy")
    violations: list[SemanticGraphChange] = []
    for change in changes:
        denied = change.kind in policy.deny_kinds
        matching = [
            allowance
            for allowance in policy.allowances
            if (allowance.kind is None or allowance.kind is change.kind)
            and fnmatchcase(change.path, allowance.path_glob)
        ]
        # max() preserves declaration order when specificity is tied.
        selected = max(
            matching,
            key=lambda item: len(re.sub(r"\[[^]]*\]|[?*]", "", item.path_glob)),
            default=None,
        )
        exceeds_threshold = _RISK_ORDER[change.risk] >= _RISK_ORDER[policy.fail_at]
        allowed = selected is not None and _RISK_ORDER[change.risk] <= _RISK_ORDER[selected.maximum_risk]
        if denied or (exceeds_threshold and not allowed):
            violations.append(change)
    return DiffPolicyReport(changes=changes, violations=tuple(violations))


_CHILD_FIELDS = ("dependencies", "decorators", "pre_configurations")
_KNOWN_FIELDS = frozenset(
    {
        "path",
        "order",
        "argument",
        "boundary",
        "source_boundary",
        "service",
        "implementation",
        "implementation_type",
        "kind",
        "activation",
        "lifespan",
        "name",
        "position",
        "tags",
        "requires_async",
        "manages_cleanup",
        "cache_owner",
        "cleanup_owner",
        "owner_path",
        "provider_mode",
        "deferred_target",
        "scope_policy",
        "key_type",
        "requested_type",
    }
)


def validate_manifest(data: dict[str, Any]) -> None:
    """Validate structure without adding fields or changing manifest fingerprints."""

    def invalid(message: str) -> None:
        raise ValueError(f"Invalid graph manifest: {message}")

    if not isinstance(data, dict) or not isinstance(data.get("roots"), list):
        invalid("roots must be a list")
    if data.get("view", "all_roots") not in ("all_roots", "entrypoints"):
        invalid("view must be all_roots or entrypoints")
    seen: set[str] = set()

    def visit(node: Any, parent: str | None = None) -> None:
        if not isinstance(node, dict) or not isinstance(node.get("path"), str) or not node["path"]:
            invalid("every node must have a non-empty path")
        path = node["path"]
        for key in ("service", "implementation", "implementation_type", "kind", "activation", "lifespan"):
            if not isinstance(node.get(key), str) or not node[key]:
                invalid(f"every node must have a non-empty {key}")
        if path in seen:
            invalid("node paths must be unique")
        seen.add(path)
        if parent is not None and not path.startswith(f"{parent}/"):
            invalid("child paths must be below their parent")
        for key in ("requires_async", "manages_cleanup"):
            if key in node and not isinstance(node[key], bool):
                invalid(f"{key} must be a boolean")
        for key in _KNOWN_FIELDS - {"tags", "order", "position", "requires_async", "manages_cleanup"}:
            if key in node and node[key] is not None and not isinstance(node[key], str):
                invalid(f"{key} must be a string or null")
        for key in ("order", "position"):
            if (
                key in node
                and node[key] is not None
                and (not isinstance(node[key], int) or isinstance(node[key], bool))
            ):
                invalid(f"{key} must be an integer or null")
        tags = node.get("tags", [])
        if not isinstance(tags, list):
            invalid("tags must be a list")
        for tag in tags:
            if not isinstance(tag, dict) or not isinstance(tag.get("name"), str):
                invalid("tags must have string names")
            if tag.get("value") is not None and not isinstance(tag["value"], str):
                invalid("tag values must be strings or null")
        for key in _CHILD_FIELDS:
            children = node.get(key, [])
            if not isinstance(children, list):
                invalid(f"{key} must be a list")
            for child in children:
                visit(child, path)

    for root in data["roots"]:
        visit(root)
    boundaries = data.get("boundaries", [])
    if not isinstance(boundaries, list):
        invalid("boundaries must be a list")
    names: set[str] = set()
    for boundary in boundaries:
        if not isinstance(boundary, dict) or not isinstance(boundary.get("name"), str):
            invalid("boundaries must have string names")
        if boundary["name"] in names:
            invalid("boundary names must be unique")
        names.add(boundary["name"])
        for key in ("uses", "exposures"):
            entries = boundary.get(key, [])
            if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
                invalid(f"boundary {key} must be a list of objects")


def classify(
    current: dict[str, dict[str, Any]],
    baseline: dict[str, dict[str, Any]],
    current_data: dict[str, Any],
    baseline_data: dict[str, Any],
    boundary_changes: tuple[GraphChange, ...],
    *,
    entrypoint_paths: Mapping[str, tuple[str, ...]] | None = None,
    reachable_root_paths: frozenset[str] | None = None,
) -> tuple[SemanticGraphChange, ...]:
    # A renamed parameter changes its path. Match the same relationship and
    # ordinal before classifying, preserving added/removed paths in the raw diff.
    baseline = dict(baseline)
    for path in sorted(current.keys() - baseline.keys(), key=lambda value: (value.count("/"), value)):
        if path in baseline or "/" not in path:
            continue
        parent, _, relationship = path.rpartition("/")
        role, _, ordinal = relationship.partition(":")
        ordinal = ordinal.rsplit(":", 1)[-1]
        candidates = [
            old_path
            for old_path, node in baseline.items()
            if old_path not in current
            and old_path.rpartition("/")[0] == parent
            and old_path.rpartition("/")[2].partition(":")[0] == role
            and old_path.rsplit(":", 1)[-1] == ordinal
            and node.get("kind") == current[path].get("kind")
        ]
        if len(candidates) != 1:
            continue
        old_path = candidates[0]
        for descendant in tuple(baseline):
            if descendant == old_path or descendant.startswith(f"{old_path}/"):
                replacement = f"{path}{descendant[len(old_path):]}"
                node = dict(baseline.pop(descendant))
                node["path"] = replacement
                owner = node.get("owner_path")
                if isinstance(owner, str) and (owner == old_path or owner.startswith(f"{old_path}/")):
                    node["owner_path"] = f"{path}{owner[len(old_path):]}"
                baseline[replacement] = node
    current_roots = tuple(root["path"] for root in current_data["roots"])
    old_roots = tuple(root["path"] for root in baseline_data["roots"])
    current_marked = (
        {root: (root,) for root in current_roots} if current_data.get("view") == "entrypoints" else entrypoint_paths
    )
    old_marked = {root: (root,) for root in old_roots} if baseline_data.get("view") == "entrypoints" else None
    changes: list[SemanticGraphChange] = []

    def root_at(path: str, roots: tuple[str, ...]) -> str | None:
        return next((root for root in roots if path == root or path.startswith(f"{root}/")), None)

    def record(
        path: str,
        kind: GraphChangeKind,
        risk: ChangeRisk,
        fields: tuple[str, ...],
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        *,
        roots: tuple[str, ...] | None = None,
    ) -> None:
        if roots is None:
            root = root_at(path, current_roots if after is not None else old_roots)
            roots = () if root is None else (root,)
        marked = current_marked if after is not None else old_marked
        known = marked is not None
        affected = tuple(
            sorted({entrypoint for root in roots for entrypoint in (() if marked is None else marked.get(root, ()))})
        )
        changes.append(
            SemanticGraphChange(
                path, kind, risk, fields, roots, affected, before, after, "known" if known else "unknown"
            )
        )

    def metadata(node: dict[str, Any]) -> dict[str, Any]:
        # Unknown metadata is reported by field name, without copying arbitrary
        # values into the classified report. Raw diffs retain the original data.
        return {key: value for key, value in node.items() if key in _KNOWN_FIELDS and key != "path"}

    for path in sorted(current.keys() - baseline.keys()):
        node = current[path]
        root = path in current_roots
        relation = path.rsplit("/", 1)[-1].partition(":")[0]
        kind = (
            GraphChangeKind.root_added
            if root
            else GraphChangeKind.decorator_changed
            if relation == "decorator"
            else GraphChangeKind.pre_configuration_changed
            if relation == "pre_configuration"
            else GraphChangeKind.dependency_added
            if relation == "dependency"
            else GraphChangeKind.unknown_metadata_changed
        )
        risk = ChangeRisk.medium
        if root and reachable_root_paths is not None and path not in reachable_root_paths:
            risk = ChangeRisk.low
        record(path, kind, risk, tuple(sorted(metadata(node))), None, metadata(node))
        capabilities = [tag for tag in node.get("tags", []) if tag["name"] == "capability"]
        if capabilities:
            record(path, GraphChangeKind.capability_changed, ChangeRisk.high, ("tags",), None, {"tags": capabilities})

    for path in sorted(baseline.keys() - current.keys()):
        node = baseline[path]
        relation = path.rsplit("/", 1)[-1].partition(":")[0]
        kind = (
            GraphChangeKind.root_removed
            if path in old_roots
            else GraphChangeKind.decorator_changed
            if relation == "decorator"
            else GraphChangeKind.pre_configuration_changed
            if relation == "pre_configuration"
            else GraphChangeKind.dependency_removed
            if relation == "dependency"
            else GraphChangeKind.unknown_metadata_changed
        )
        record(path, kind, ChangeRisk.high, tuple(sorted(metadata(node))), metadata(node), None)

    concerns = (
        (GraphChangeKind.implementation_changed, ChangeRisk.high, {"implementation", "implementation_type"}),
        (
            GraphChangeKind.activation_changed,
            ChangeRisk.high,
            {"activation", "kind", "provider_mode", "deferred_target", "scope_policy"},
        ),
        (GraphChangeKind.lifespan_changed, ChangeRisk.high, {"lifespan", "cache_owner"}),
        (GraphChangeKind.async_requirement_changed, ChangeRisk.high, {"requires_async"}),
        (GraphChangeKind.cleanup_changed, ChangeRisk.high, {"manages_cleanup", "cleanup_owner", "owner_path"}),
        (
            GraphChangeKind.selection_metadata_changed,
            ChangeRisk.medium,
            {"service", "requested_type", "name", "argument", "key_type"},
        ),
        (GraphChangeKind.order_changed, ChangeRisk.medium, {"order", "position"}),
        (GraphChangeKind.boundary_component_moved, ChangeRisk.high, {"boundary", "source_boundary"}),
    )
    for path in sorted(current.keys() & baseline.keys()):
        before, after = baseline[path], current[path]
        changed = {
            key
            for key in before.keys() | after.keys()
            if before.get(key) != after.get(key) or (key in before) != (key in after)
        } - {"path"}
        for kind, risk, concern in concerns:
            fields = tuple(sorted(changed & concern))
            if not fields:
                continue
            changed.difference_update(fields)
            if kind is GraphChangeKind.implementation_changed:
                relation = path.rsplit("/", 1)[-1].partition(":")[0]
                if relation == "decorator":
                    kind = GraphChangeKind.decorator_changed
                elif relation == "pre_configuration":
                    kind = GraphChangeKind.pre_configuration_changed
            if kind is GraphChangeKind.selection_metadata_changed and {"service", "requested_type"} & set(fields):
                risk = ChangeRisk.high
            record(
                path,
                kind,
                risk,
                fields,
                {key: before[key] for key in fields if key in before},
                {key: after[key] for key in fields if key in after},
            )
        if "tags" in changed:
            changed.remove("tags")
            for capability in (False, True):
                old_tags = [tag for tag in before.get("tags", []) if (tag["name"] == "capability") == capability]
                new_tags = [tag for tag in after.get("tags", []) if (tag["name"] == "capability") == capability]
                if old_tags != new_tags:
                    record(
                        path,
                        GraphChangeKind.capability_changed
                        if capability
                        else GraphChangeKind.selection_metadata_changed,
                        ChangeRisk.high if capability else ChangeRisk.medium,
                        ("tags",),
                        {"tags": old_tags},
                        {"tags": new_tags},
                    )
        if changed:
            record(path, GraphChangeKind.unknown_metadata_changed, ChangeRisk.medium, tuple(sorted(changed)), {}, {})

    # Boundary contracts already have a raw classifier. Reuse its findings,
    # normalizing the earlier critical bypass label to the high policy tier.
    for change in boundary_changes:
        if change.category == "boundary-component-moved":
            continue  # Already classified with all changed boundary fields.
        roots = None
        if change.path.startswith("boundary:"):
            name = change.path.removeprefix("boundary:").split(":", 1)[0]
            roots = tuple(
                sorted(
                    {
                        root
                        for path, node in current.items()
                        if (node.get("boundary") == name or node.get("source_boundary") == name)
                        and (root := root_at(path, current_roots)) is not None
                    }
                )
            )
            if not change.after:
                roots = tuple(
                    sorted(
                        set(roots)
                        | {
                            root
                            for path, node in baseline.items()
                            if node.get("boundary") == name and (root := root_at(path, old_roots)) is not None
                        }
                    )
                )
        record(
            change.path,
            GraphChangeKind(change.category),
            ChangeRisk.high if change.risk == "critical" else ChangeRisk(change.risk),
            tuple(sorted(change.before.keys() | change.after.keys())),
            change.before or None,
            change.after or None,
            roots=roots,
        )
    return tuple(
        sorted(
            changes,
            key=lambda change: (
                change.path,
                change.kind.value,
                change.fields,
                json.dumps(change.to_dict(), sort_keys=True),
            ),
        )
    )
