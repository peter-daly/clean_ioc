"""Compile, validate, and compare explicitly supported application variants."""

from __future__ import annotations

import inspect
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, TypeAlias

from .container import ContainerBuilder, ContainerBuildError, ScopeBuilder, _valid_build_issue
from .sarif import _location, _unique_source
from .tooling import (
    BuildIssue,
    BuildReport,
    CompiledGraph,
    DiffPolicy,
    GraphDiff,
    GraphManifest,
    IssueSeverity,
    qualified_name,
)

__all__ = [
    "BuildMatrix",
    "BuildVariant",
    "MatrixContext",
    "MatrixPolicy",
    "MatrixReport",
    "VariantReport",
    "require_valid_variants",
    "same_entrypoints",
    "semantic_drift",
]

_NAME = re.compile(r"[A-Za-z0-9_.-]+", re.ASCII)
_CONFIGURATION_CODES = frozenset({"matrix-factory-error", "matrix-reused-builder"})


def _issue(code: str, message: str, *, variant: str | None = None, path: tuple[str, ...] = ()) -> BuildIssue:
    return BuildIssue(code, IssueSeverity.error, message, root=variant, path=path)


def _synchronous(callback: Any) -> bool:
    return callable(callback) and not (
        inspect.iscoroutinefunction(callback)
        or inspect.isasyncgenfunction(callback)
        or inspect.iscoroutinefunction(getattr(callback, "__call__", None))
        or inspect.isasyncgenfunction(getattr(callback, "__call__", None))
    )


@dataclass(frozen=True, slots=True)
class BuildVariant:
    """A fresh builder factory and private, captured compilation inputs."""

    name: str
    builder_factory: Callable[[], ContainerBuilder | ScopeBuilder] = field(repr=False, compare=False)
    build_args: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or _NAME.fullmatch(self.name) is None:
            raise ValueError("matrix-invalid-name: variant names require ASCII letters, digits, _, -, or .")
        if not _synchronous(self.builder_factory):
            raise ValueError("matrix-factory-error: a variant requires a synchronous builder factory")
        if not isinstance(self.build_args, Mapping) or any(not isinstance(key, str) for key in self.build_args):
            raise ValueError("matrix-invalid-inputs: build inputs require a mapping with string keys")
        object.__setattr__(self, "build_args", MappingProxyType(dict(self.build_args)))


@dataclass(frozen=True, slots=True)
class VariantReport:
    name: str
    build_report: BuildReport
    fingerprint: str | None = None
    difference: GraphDiff | None = None
    entrypoints: tuple[tuple[str, str | None], ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.build_report.is_valid

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "valid": self.is_valid,
            "build_report": self.build_report.to_dict(),
            "fingerprint": self.fingerprint,
            "difference": None if self.difference is None else self.difference.to_semantic_dict(),
            "entrypoints": [{"service": service, "name": name} for service, name in self.entrypoints],
        }


@dataclass(frozen=True, slots=True)
class MatrixContext:
    """Redacted policy inputs, with detached manifest snapshots on request."""

    reference: str
    variants: tuple[VariantReport, ...]
    _manifests: Mapping[str, str] = field(default_factory=dict, repr=False, compare=False)

    @property
    def reference_report(self) -> VariantReport:
        return next(variant for variant in self.variants if variant.name == self.reference)

    def manifest(self, name: str) -> GraphManifest | None:
        captured = self._manifests.get(name)
        return None if captured is None else GraphManifest.from_json(captured)

    def issue(
        self,
        variant: str,
        code: str,
        message: str,
        *,
        severity: IssueSeverity = IssueSeverity.error,
        path: tuple[str, ...] = (),
    ) -> BuildIssue:
        if not any(report.name == variant for report in self.variants):
            raise ValueError("matrix-policy-error: issue variant is not in this matrix")
        return BuildIssue(code, severity, message, root=variant, path=path)


MatrixPolicy: TypeAlias = Callable[[MatrixContext], Iterable[BuildIssue]]


def _require_valid(context: MatrixContext) -> Iterable[BuildIssue]:
    for variant in context.variants:
        if not variant.is_valid:
            yield context.issue(variant.name, "matrix-build-failed", "Variant did not pass compilation and validation.")


def require_valid_variants() -> MatrixPolicy:
    """Implicitly enforced for every matrix; it cannot be disabled."""

    return _require_valid


def same_entrypoints() -> MatrixPolicy:
    """Require the same marked requested types and selected names."""

    def rule(context: MatrixContext) -> Iterable[BuildIssue]:
        reference = context.reference_report
        if not reference.is_valid:
            return
        for variant in context.variants:
            if variant.name != reference.name and variant.is_valid and variant.entrypoints != reference.entrypoints:
                yield context.issue(
                    variant.name, "matrix-entrypoint-drift", "Marked entry points differ from the reference."
                )

    return rule


def semantic_drift(policy: DiffPolicy) -> MatrixPolicy:
    """Evaluate each valid variant's changes against the named reference."""

    if not isinstance(policy, DiffPolicy):
        raise ValueError("diff-policy-invalid: semantic_drift requires a DiffPolicy")

    def rule(context: MatrixContext) -> Iterable[BuildIssue]:
        if not context.reference_report.is_valid:
            return
        for variant in context.variants:
            if variant.name == context.reference or variant.difference is None:
                continue
            for change in variant.difference.evaluate(policy).violations:
                yield context.issue(
                    variant.name,
                    "matrix-graph-drift",
                    f"{change.kind.value} [{change.risk.value}] violates the graph-change policy.",
                    path=(change.path,),
                )

    return rule


def _policy_issues(policy: MatrixPolicy, context: MatrixContext) -> Iterable[BuildIssue]:
    try:
        result = policy(context)
        if inspect.iscoroutine(result):
            result.close()
            raise TypeError
        for issue in result:
            if not _valid_build_issue(issue):
                raise TypeError
            yield replace(issue, _occurrence_path=())
    except Exception:
        yield _issue("matrix-policy-error", "Matrix policy failed or returned malformed findings.")


@dataclass(frozen=True, slots=True)
class MatrixReport:
    variants: tuple[VariantReport, ...]
    issues: tuple[BuildIssue, ...] = ()
    reference: str = ""
    _sarif: tuple[str, ...] = field(default=(), repr=False, compare=False)
    _locations: Mapping[tuple[str, str], str] = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_valid(self) -> bool:
        return all(variant.is_valid for variant in self.variants) and not any(
            issue.severity is IssueSeverity.error for issue in self.issues
        )

    @property
    def exit_code(self) -> int:
        if any(
            issue.code in _CONFIGURATION_CODES for variant in self.variants for issue in variant.build_report.issues
        ):
            return 2
        return 0 if self.is_valid else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.is_valid,
            "reference": self.reference,
            "variants": [variant.to_dict() for variant in self.variants],
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        lines = [
            f"Build matrix {'passed' if self.is_valid else 'failed'} "
            f"({len(self.variants)} variants; reference {self.reference})."
        ]
        for variant in self.variants:
            lines.append(f"\nVariant {variant.name}:")
            lines.append(variant.build_report.to_text())
            if variant.fingerprint is not None:
                lines.append(f"Graph fingerprint: {variant.fingerprint}")
            if variant.difference is not None:
                lines.append(variant.difference.to_semantic_text())
        if self.issues:
            lines.append("\nMatrix findings:")
            lines.extend(f"- {issue.root + ': ' if issue.root else ''}{issue}" for issue in self.issues)
        return "\n".join(lines)

    def to_sarif(self, *, indent: int | None = 2) -> str:
        # Captured SARIF documents contain sources, never live graphs or inputs.
        document = json.loads(BuildReport(self.issues).to_sarif())
        policy_run = document["runs"][0]
        policy_run["properties"]["reference"] = self.reference
        policy_run["properties"]["matrixPolicies"] = True
        for result, issue in zip(policy_run["results"], self.issues, strict=True):
            if issue.root in {variant.name for variant in self.variants}:
                result["properties"]["variant"] = issue.root
            if issue.root is not None and issue.path:
                source = self._locations.get((issue.root, issue.path[0])) or self._locations.get(
                    (self.reference, issue.path[0])
                )
                if source is not None:
                    location = json.loads(source)
                    result["locations"] = [location]
                    result["codeFlows"][0]["threadFlows"][0]["locations"][0]["location"] = location
        runs: list[dict[str, Any]] = []
        for index, variant in enumerate(self.variants):
            value = self._sarif[index] if index < len(self._sarif) else variant.build_report.to_sarif()
            run = json.loads(value)["runs"][0]
            run["properties"].update({"variant": variant.name, "reference": self.reference})
            run["properties"].pop("graphFingerprint", None)
            if variant.fingerprint is not None:
                run["properties"]["graphFingerprint"] = variant.fingerprint
            for result in run["results"]:
                result["properties"]["variant"] = variant.name
            runs.append(run)
        if self.issues or not runs:
            runs.append(policy_run)
        document["runs"] = runs
        return json.dumps(document, indent=indent, sort_keys=True)

    def assert_valid(self) -> None:
        if not self.is_valid:
            raise AssertionError(self.to_sarif())


def _redacted_manifest(graph: CompiledGraph) -> GraphManifest:
    data = graph.manifest().to_dict()

    def visit(node: dict[str, Any]) -> None:
        if node["kind"] == "value":
            # A supplied argument's actual Python value type is private input
            # metadata. Keep its declared dependency type and structural edge.
            node["implementation"] = node["service"]
            node["implementation_type"] = node["service"]
        for relationship in ("dependencies", "decorators", "pre_configurations"):
            for child in node[relationship]:
                visit(child)

    for root in data["roots"]:
        visit(root)
    return GraphManifest(data)


def _capture(
    name: str,
    report: BuildReport,
    graph: CompiledGraph | None = None,
) -> tuple[VariantReport, str, dict[str, str], str | None]:
    # Ordinary validation callback errors may contain arbitrary exception text.
    # Preserve their code and location with a fixed matrix-safe explanation.
    report = replace(
        report,
        issues=tuple(
            replace(issue, message="A validation callback failed.") if issue.code == "validation-rule-error" else issue
            for issue in report.issues
        ),
    )
    manifest = _redacted_manifest(graph) if graph is not None and report.is_valid else None
    document = json.loads(report.to_sarif())
    properties = document["runs"][0]["properties"]
    properties.pop("graphFingerprint", None)
    if manifest is not None:
        properties["graphFingerprint"] = manifest.fingerprint
    sarif = json.dumps(document, sort_keys=True)
    entrypoints = (
        ()
        if graph is None
        else tuple(
            sorted(
                ((qualified_name(root.requested_type), root.component.name) for root in graph.entrypoints),
                key=lambda item: (item[0], item[1] or ""),
            )
        )
    )
    safe_report = BuildReport(
        tuple(replace(issue, _occurrence_path=()) for issue in report.issues),
        checked_roots=report.checked_roots,
    )
    locations: dict[str, str] = {}
    if graph is not None:
        for path, component in graph._component_paths(all_roots=False).items():
            explanation = graph._occurrence_explanations.get(component.occurrence_id)
            selected = () if explanation is None else explanation.selected
            source = _unique_source(item.origin.location for item in selected if item.component_id == component.id)
            locations[path] = json.dumps(_location(qualified_name(component.service_type), source), sort_keys=True)
    return (
        VariantReport(name, safe_report, None if manifest is None else manifest.fingerprint, entrypoints=entrypoints),
        sarif,
        locations,
        None if manifest is None else manifest.to_json(indent=None),
    )


def _build_variant(
    variant: BuildVariant,
    used: list[ContainerBuilder | ScopeBuilder],
) -> tuple[VariantReport, str, dict[str, str], str | None]:
    try:
        builder = variant.builder_factory()
        if inspect.iscoroutine(builder):
            builder.close()
        if not isinstance(builder, (ContainerBuilder, ScopeBuilder)):
            raise TypeError
    except Exception:
        report = BuildReport((_issue("matrix-factory-error", "Factory did not return an unbuilt builder."),))
    else:
        if any(builder is previous for previous in used):
            report = BuildReport(
                (_issue("matrix-reused-builder", "A builder was already returned by another variant."),)
            )
        elif builder._built:
            report = BuildReport((_issue("matrix-factory-error", "Factory returned an already built builder."),))
            used.append(builder)
        else:
            used.append(builder)
            try:
                with builder.build(build_args=variant.build_args) as scope:
                    graph = scope.graph
                    captured = _capture(variant.name, scope.validation_report(), graph)
                return captured
            except ContainerBuildError as error:
                report = error.report or BuildReport((_issue("matrix-build-failed", "Variant compilation failed."),))
            except Exception:
                report = BuildReport(
                    (_issue("matrix-build-failed", "Variant compilation, validation, or cleanup failed."),)
                )
    return _capture(variant.name, report)


@dataclass(frozen=True, slots=True, init=False)
class BuildMatrix:
    variants: tuple[BuildVariant, ...]
    reference: str
    policies: tuple[MatrixPolicy, ...] = field(default=(), repr=False)

    def __init__(self, variants: Iterable[BuildVariant], reference: str, policies: Iterable[MatrixPolicy] = ()) -> None:
        try:
            captured = tuple(variants)
        except TypeError:
            raise ValueError("matrix-invalid-variant: variants must be iterable") from None
        if any(not isinstance(variant, BuildVariant) for variant in captured):
            raise ValueError("matrix-invalid-variant: variants must contain BuildVariant records")
        names = tuple(variant.name for variant in captured)
        if len(set(names)) != len(names):
            raise ValueError("matrix-invalid-name: variant names must be unique")
        if not isinstance(reference, str) or reference not in names:
            raise ValueError("matrix-reference-missing: reference must name a declared variant")
        try:
            rules = tuple(policies)
        except TypeError:
            raise ValueError("matrix-policy-error: policies must be iterable") from None
        if any(not _synchronous(policy) for policy in rules):
            raise ValueError("matrix-policy-error: matrix policies must be synchronous callbacks")
        object.__setattr__(self, "variants", captured)
        object.__setattr__(self, "reference", reference)
        object.__setattr__(self, "policies", rules)

    def check(self) -> MatrixReport:
        used: list[ContainerBuilder | ScopeBuilder] = []
        variants: list[VariantReport] = []
        manifests: dict[str, str] = {}
        sources: dict[tuple[str, str], str] = {}
        sarif: list[str] = []
        for variant in self.variants:
            result, document, locations, manifest = _build_variant(variant, used)
            variants.append(result)
            sarif.append(document)
            sources.update({(variant.name, path): value for path, value in locations.items()})
            if manifest is not None:
                manifests[variant.name] = manifest
        reference = next(variant for variant in variants if variant.name == self.reference)
        if reference.is_valid:
            baseline = GraphManifest.from_json(manifests[self.reference])
            variants = [
                replace(
                    variant,
                    difference=replace(
                        GraphManifest.from_json(manifests[variant.name]),
                        _entrypoint_paths={},
                        _reachable_root_paths=frozenset(),
                    ).diff(baseline),
                )
                if variant.is_valid
                else variant
                for variant in variants
            ]
        records = tuple(variants)
        context = MatrixContext(self.reference, records, MappingProxyType(manifests))
        issues = list(_require_valid(context))
        if not reference.is_valid:
            issues.append(
                _issue(
                    "matrix-reference-invalid",
                    "Reference is invalid; cross-variant comparisons are unavailable.",
                    variant=self.reference,
                )
            )
        for policy in self.policies:
            if policy is _require_valid:
                continue
            # Every callback gets its own detached dictionaries. Mutating a
            # retrieved snapshot cannot alter other policies or the final report.
            policy_context = replace(context, variants=deepcopy(records))
            issues.extend(_policy_issues(policy, policy_context))
        return MatrixReport(records, tuple(issues), self.reference, tuple(sarif), MappingProxyType(sources))
