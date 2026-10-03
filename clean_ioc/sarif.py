"""Source-linked SARIF output over captured compiler and validation findings."""

from __future__ import annotations

import json
from collections import defaultdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable
from urllib.parse import quote

from .tooling import BuildIssue, BuildReport, CompilationExplanation, CompiledGraph, FailureEvidence, SourceLocation

_SCHEMA = "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json"


def _physical_location(source: SourceLocation | None) -> dict[str, Any] | None:
    if source is None or not source.path or source.path.startswith("<"):
        return None
    # Source capture normally supplies relative paths. Also handle explicit
    # absolute sources inside the checkout; omit external and foreign paths.
    if PureWindowsPath(source.path).drive and Path(source.path).drive == "":
        return None
    try:
        relative = Path(source.path).resolve().relative_to(Path.cwd().resolve())
    except (OSError, ValueError, RuntimeError):
        return None
    if relative == Path("."):
        return None
    physical: dict[str, Any] = {"artifactLocation": {"uri": quote(relative.as_posix(), safe="/")}}
    if isinstance(source.line, int) and not isinstance(source.line, bool) and source.line > 0:
        physical["region"] = {"startLine": source.line}
    return physical


def _unique_source(sources: Iterable[SourceLocation | None]) -> SourceLocation | None:
    candidates = {(None if source is None else (source.path, source.line)): source for source in sources}
    return next(iter(candidates.values())) if len(candidates) == 1 else None


class _Sources:
    """Index exact visits and captured decisions without re-running selection."""

    def __init__(self, graph: CompiledGraph | None, explanations: Iterable[CompilationExplanation]):
        self.visits: dict[tuple[str, ...], list[tuple[str, tuple[int, ...], tuple[SourceLocation | None, ...]]]] = (
            defaultdict(list)
        )
        self.decisions: dict[tuple[str, ...], list[SourceLocation | None]] = defaultdict(list)
        if graph is not None:
            for visit in graph.walk():
                sources: list[SourceLocation | None] = []
                for component in visit.components:
                    explanation = graph._occurrence_explanations.get(component.occurrence_id)
                    selected = () if explanation is None else explanation.selected
                    sources.append(
                        _unique_source(
                            decision.origin.location for decision in selected if decision.component_id == component.id
                        )
                    )
                self.visits[visit.path].append(
                    (visit.root_name, tuple(component.occurrence_id for component in visit.components), tuple(sources))
                )
        for explanation in explanations:
            self.decisions[explanation.path].extend(decision.origin.location for decision in explanation.selected)

    def path_sources(self, issue: BuildIssue) -> tuple[SourceLocation | None, ...]:
        matches = [
            sources
            for root, occurrences, sources in self.visits.get(issue.path, ())
            if (issue.root is None or root == issue.root)
            and (not issue._occurrence_path or occurrences == issue._occurrence_path)
        ]
        if matches:
            return tuple(_unique_source(sources[index] for sources in matches) for index in range(len(issue.path)))
        return tuple(
            _unique_source(self.decisions.get(issue.path[: index + 1], ())) for index in range(len(issue.path))
        )


def _location(label: str, source: SourceLocation | None) -> dict[str, Any]:
    location: dict[str, Any] = {"logicalLocations": [{"fullyQualifiedName": label, "kind": "type"}]}
    physical = _physical_location(source)
    if physical is not None:
        location["physicalLocation"] = physical
    return location


def report_to_sarif(
    report: BuildReport,
    *,
    graph: CompiledGraph | None = None,
    explanations: Iterable[CompilationExplanation] = (),
    evidence: Iterable[FailureEvidence | None] = (),
    indent: int | None = 2,
) -> str:
    """Serialize findings with best-effort source attribution and no activation."""

    captured = tuple(evidence)
    if len(captured) > len(report.issues):
        raise ValueError("More evidence records than report issues")
    captured += (None,) * (len(report.issues) - len(captured))
    sources = _Sources(graph, explanations)
    codes = tuple(dict.fromkeys(issue.code for issue in report.issues))
    rule_indices = {code: index for index, code in enumerate(codes)}
    results: list[dict[str, Any]] = []
    for issue, fact in zip(report.issues, captured, strict=True):
        path_sources = sources.path_sources(issue)
        result: dict[str, Any] = {
            "ruleId": issue.code,
            "ruleIndex": rule_indices[issue.code],
            "level": issue.severity.value,
            "message": {"text": str(issue)},
            "properties": {"root": issue.root, "componentPath": list(issue.path)},
        }
        primary = fact.source_location if fact is not None else (path_sources[-1] if path_sources else None)
        if issue.path:
            result["locations"] = [_location(issue.path[-1], primary)]
            result["codeFlows"] = [
                {
                    "threadFlows": [
                        {
                            "locations": [
                                {"location": _location(label, source), "nestingLevel": index}
                                for index, (label, source) in enumerate(zip(issue.path, path_sources, strict=True))
                            ]
                        }
                    ]
                }
            ]
        elif (physical := _physical_location(primary)) is not None:
            result["locations"] = [{"physicalLocation": physical}]
        results.append(result)
    driver: dict[str, Any] = {
        "name": "Clean IoC",
        "informationUri": "https://peter-daly.github.io/clean_ioc/",
        "rules": [{"id": code} for code in codes],
    }
    try:
        driver["version"] = version("clean_ioc")
    except PackageNotFoundError:
        pass
    properties: dict[str, Any] = {"checkedRoots": report.checked_roots}
    if graph is not None:
        properties["graphFingerprint"] = graph.manifest(all_roots=True).fingerprint
    run = {
        "tool": {"driver": driver},
        "results": results,
        "invocations": [{"executionSuccessful": True}],
        "properties": properties,
    }
    return json.dumps({"$schema": _SCHEMA, "version": "2.1.0", "runs": [run]}, indent=indent, sort_keys=True)
