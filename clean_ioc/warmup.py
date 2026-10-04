"""Declared startup intent and detached observations of explicit initialization."""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .components import ComponentFilter, default_component_filter
from .tooling import BuildIssue, BuildReport, FailureEvidence, IssueSeverity, SourceLocation

__all__ = [
    "WarmupTarget",
    "WarmupPlan",
    "WarmupTargetInfo",
    "WarmupPlanInfo",
    "WarmupResult",
    "WarmupReport",
    "WarmupError",
]


@dataclass(frozen=True, slots=True)
class WarmupTarget:
    service_type: Any
    filter: ComponentFilter = default_component_filter


@dataclass(frozen=True, slots=True, init=False)
class WarmupPlan:
    name: str
    targets: tuple[WarmupTarget, ...]

    def __init__(self, name: str, targets: Iterable[WarmupTarget]):
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "targets", tuple(targets))


@dataclass(frozen=True, slots=True)
class WarmupTargetInfo:
    service: str
    implementation: str
    path: str
    requires_async: bool
    source_location: SourceLocation | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "implementation": self.implementation,
            "path": self.path,
            "requires_async": self.requires_async,
            "source_location": None if self.source_location is None else self.source_location.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class WarmupPlanInfo:
    name: str
    targets: tuple[WarmupTargetInfo, ...]

    @property
    def requires_async(self) -> bool:
        return any(target.requires_async for target in self.targets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "requires_async": self.requires_async,
            "targets": [t.to_dict() for t in self.targets],
        }


@dataclass(frozen=True, slots=True)
class WarmupResult:
    target: WarmupTargetInfo
    status: str
    exception_type: str | None = None
    code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.target.to_dict(),
            "status": self.status,
            "exception_type": self.exception_type,
            "code": self.code,
        }


@dataclass(frozen=True, slots=True)
class WarmupReport:
    name: str
    graph_fingerprint: str
    results: tuple[WarmupResult, ...]

    @property
    def is_valid(self) -> bool:
        return all(result.status == "succeeded" for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "graph_fingerprint": self.graph_fingerprint,
            "valid": self.is_valid,
            "targets": [result.to_dict() for result in self.results],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        return "\n".join(
            [
                f"Warm-up {self.name}: {'valid' if self.is_valid else 'invalid'}",
                *(
                    f"  {r.target.path}: {r.status}" + (f" [{r.exception_type}]" if r.exception_type else "")
                    for r in self.results
                ),
            ]
        )

    def to_sarif(self, *, indent: int | None = 2) -> str:
        failures = tuple(result for result in self.results if result.code is not None)
        report = BuildReport(
            tuple(
                BuildIssue(
                    result.code or "warmup-activation-failed",
                    IssueSeverity.error,
                    "Warm-up requires asynchronous activation or cleanup."
                    if result.code == "warmup-requires-async"
                    else "Warm-up target initialization failed.",
                    root=self.name,
                    path=(result.target.path,),
                )
                for result in failures
            ),
            checked_roots=len(self.results),
        )
        evidence = tuple(
            FailureEvidence(
                "warmup", result.target.service, "Warm-up observation.", source_location=result.target.source_location
            )
            for result in failures
        )
        document = json.loads(report.to_sarif(evidence=evidence))
        document["runs"][0]["properties"]["graphFingerprint"] = self.graph_fingerprint
        document["runs"][0]["properties"]["warmupPlan"] = self.name
        for finding, result in zip(document["runs"][0]["results"], failures, strict=True):
            finding["properties"]["exceptionType"] = result.exception_type
        return json.dumps(document, indent=indent, sort_keys=True)

    def assert_valid(self) -> None:
        if not self.is_valid:
            raise AssertionError(self.to_sarif())

    def raise_for_errors(self) -> None:
        if not self.is_valid:
            raise WarmupError(self)


class WarmupError(RuntimeError):
    def __init__(self, report: WarmupReport):
        self.report = report
        super().__init__("Warm-up initialization did not complete successfully.")
