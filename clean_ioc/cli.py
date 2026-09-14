"""Command-line access to Clean IoC's compiled graph toolchain."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import component_filters as cf
from .container import ContainerBuilder, ContainerBuildError, Scope, ScopeBuilder
from .tooling import BuildReport, GraphManifest, IssueSeverity


def _load_object(locator: str) -> Any:
    module_name, separator, attribute_path = locator.partition(":")
    if not separator or not module_name or not attribute_path:
        raise ValueError("Target must use the form module:object")
    value: Any = importlib.import_module(module_name)
    for name in attribute_path.split("."):
        value = getattr(value, name)
    return value


def _load_scope(locator: str) -> Scope:
    value = _load_object(locator)
    if isinstance(value, (ContainerBuilder, ScopeBuilder)):
        value = value.build()
    elif not isinstance(value, Scope) and callable(value):
        value = value()
        if isinstance(value, (ContainerBuilder, ScopeBuilder)):
            value = value.build()
    if not isinstance(value, Scope):
        raise TypeError("Target must be a builder, a built Container/Scope, or a zero-argument factory returning one")
    return value


def _write(value: str, output: str | None) -> None:
    if output is None:
        print(value)
        return
    Path(output).write_text(f"{value.rstrip()}\n", encoding="utf-8")


def _filtered_report(report: BuildReport, ignored: set[str]) -> BuildReport:
    return BuildReport(
        tuple(issue for issue in report.issues if issue.severity is IssueSeverity.error or issue.code not in ignored),
        checked_roots=report.checked_roots,
    )


def _check(args: argparse.Namespace) -> int:
    scope = _load_scope(args.target)
    report = _filtered_report(
        scope.validation_report(),
        set(args.ignore),
    )
    _write(report.to_json() if args.format == "json" else report.to_text(), None)
    if not report.is_valid or (args.strict and report.warnings):
        return 1
    return 0


def _graph(args: argparse.Namespace) -> int:
    try:
        graph = _load_scope(args.target).graph
    except ContainerBuildError as error:
        if args.on_error != "partial" or error.partial_graph is None:
            raise
        if args.format == "json":
            value = error.partial_graph.to_json()
        elif args.format == "mermaid":
            value = error.partial_graph.to_mermaid()
        else:
            value = error.partial_graph.to_text()
        _write(value, args.output)
        return 1
    if args.format == "json":
        value = graph.manifest(all_roots=args.all).to_json()
    elif args.format == "mermaid":
        value = graph.to_mermaid(all_roots=args.all)
    else:
        value = graph.to_text(all_roots=args.all)
    _write(value, args.output)
    return 0


def _ownership(args: argparse.Namespace) -> int:
    report = _load_scope(args.target).graph.ownership_report()
    _write(report.to_json() if args.format == "json" else report.to_text(), args.output)
    return 0 if report.is_valid else 1


def _diff(args: argparse.Namespace) -> int:
    current = _load_scope(args.target).graph.manifest(all_roots=args.all)
    baseline = GraphManifest.from_json(Path(args.baseline).read_text(encoding="utf-8"))
    difference = current.diff(baseline)
    _write(difference.to_json() if args.format == "json" else difference.to_text(), None)
    return 0 if difference.is_empty else 1


def _explain(args: argparse.Namespace) -> int:
    if args.argument is not None and not args.arguments:
        raise ValueError("--argument requires --arguments")
    graph = _load_scope(args.target).graph
    component = None
    if args.path is not None:
        if args.name is not None:
            raise ValueError("--name cannot be combined with --path")
        component = graph.component_at_path(args.path)
        explanation = graph.explain(component)
    else:
        service_type = _load_object(args.service)
        filter = cf.with_name(args.name) if args.name is not None else None
        explanation = graph.explain(service_type) if filter is None else graph.explain(service_type, filter=filter)
        selected = explanation.selected[0] if explanation.selected else None
        component = next(
            (
                visit.component
                for visit in graph.walk()
                if visit.component.id == (selected.component_id if selected else None)
            ),
            None,
        )
    if args.arguments:
        if component is None:
            raise ValueError("explain-arguments-not-recorded: select an exact occurrence with --path")
        records = graph.explain_arguments(component)
        if args.argument is not None:
            records = tuple(record for record in records if record.parameter == args.argument)
            if not records:
                raise ValueError(f"explain-argument-not-found: {args.argument!r}")
        value = (
            json.dumps({"arguments": [record.to_dict() for record in records]}, indent=2, sort_keys=True)
            if args.format == "json"
            else "\n".join(
                f"{record.parameter}: {record.policy_kind} -> {record.result_category} ({record.result_type})"
                for record in records
            )
        )
    elif args.specialization:
        if component is None:
            raise ValueError("explain-specialization-not-recorded: select an exact occurrence with --path")
        record = graph.explain_specialization(component)
        if args.format == "json":
            value = json.dumps(record.to_dict(), indent=2, sort_keys=True)
        else:
            lines = [
                f"Specialization {record.requested_service}",
                f"Template: {record.template_identity}",
                f"Selected tier: {record.selected_tier}",
                "Service bindings:",
            ]
            lines.extend(f"- {name} -> {bound}" for name, bound in record.service_bindings)
            if not record.service_bindings:
                lines.append("- none")
            lines.append("Factory-pattern bindings:")
            lines.extend(f"- {name} -> {bound}" for name, bound in record.factory_pattern_bindings)
            if not record.factory_pattern_bindings:
                lines.append("- none")
            lines.append("Dependency substitutions:")
            lines.extend(f"- {name}: {before} -> {after}" for name, before, after in record.dependency_annotations)
            if not record.dependency_annotations:
                lines.append("- none")
            value = "\n".join(lines)
    else:
        value = explanation.to_json() if args.format == "json" else explanation.to_text()
    _write(value, args.output)
    return 0


def _analysis_subject(graph: Any, service: str | None, path: str | None, *, all_roots: bool = True) -> Any:
    if path is not None and service is not None:
        raise ValueError("--path cannot be combined with a service locator")
    if path is not None:
        return graph.component_at_path(path, all_roots=all_roots)
    if service is None:
        raise ValueError("A service locator or --path is required")
    return _load_object(service)


def _impact(args: argparse.Namespace) -> int:
    graph = _load_scope(args.target).graph
    subject = _analysis_subject(graph, args.service, args.path, all_roots=args.all)
    match = "occurrence" if args.path is not None else args.match
    report = graph.dependents(subject, match=match, name=args.name, include_deferred=args.include_deferred)
    if args.format == "json":
        value = report.to_json()
    elif args.format == "mermaid":
        value = report.to_mermaid()
    else:
        value = report.to_text()
    _write(value, args.output)
    return 0


def _sharing(args: argparse.Namespace) -> int:
    graph = _load_scope(args.target).graph
    subject = None if args.service is None and args.path is None else _analysis_subject(graph, args.service, args.path)
    report = graph.sharing_report(subject)
    if args.format == "json":
        value = report.to_json()
    elif args.format == "mermaid":
        value = report.to_mermaid()
    else:
        value = report.to_text()
    _write(value, args.output)
    return 0


def _activation(args: argparse.Namespace) -> int:
    graph = _load_scope(args.target).graph
    subject = _analysis_subject(graph, args.service, args.path)
    report = graph.activation_report(subject, scenario=args.scenario)
    if args.format == "json":
        value = report.to_json()
    elif args.format == "mermaid":
        value = report.to_mermaid()
    else:
        value = report.to_text()
    _write(value, args.output)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clean-ioc", description="Inspect compiled Clean IoC component plans")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="Build a target and report compiler findings")
    check.add_argument("target", help="module:object composition target")
    check.add_argument("--format", choices=("text", "json"), default="text")
    check.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail when unsuppressed warnings remain; rule selection is unchanged (default: strict)",
    )
    check.add_argument("--ignore", action="append", default=[], metavar="CODE", help="Ignore a warning code")
    check.set_defaults(handler=_check)

    graph = commands.add_parser("graph", help="Render or snapshot a compiled graph")
    graph.add_argument("target", help="module:object composition target")
    graph.add_argument("--format", choices=("text", "mermaid", "json"), default="text")
    graph.add_argument("--all", action="store_true", help="Include every compiled root")
    graph.add_argument(
        "--on-error",
        choices=("raise", "partial"),
        default="raise",
        help="render a non-executable partial diagnostic graph when the build fails",
    )
    graph.add_argument("-o", "--output", help="Write output to a file instead of stdout")
    graph.set_defaults(handler=_graph)

    ownership = commands.add_parser("ownership", help="Show compiled cache and cleanup ownership proofs")
    ownership.add_argument("target", help="module:object composition target")
    ownership.add_argument("--format", choices=("text", "json"), default="text")
    ownership.add_argument("-o", "--output", help="Write output to a file instead of stdout")
    ownership.set_defaults(handler=_ownership)

    difference = commands.add_parser("diff", help="Compare a compiled graph with a JSON manifest")
    difference.add_argument("target", help="module:object composition target")
    difference.add_argument("baseline", help="baseline graph manifest")
    difference.add_argument("--format", choices=("text", "json"), default="text")
    difference.add_argument("--all", action="store_true", help="Compare every compiled root")
    difference.set_defaults(handler=_diff)

    explain = commands.add_parser("explain", help="Explain a frozen compiler selection")
    explain.add_argument("target", help="module:object composition target")
    selection = explain.add_mutually_exclusive_group(required=True)
    selection.add_argument("service", nargs="?", help="module:attribute service type")
    selection.add_argument("--path", help="path from the current graph manifest")
    explain.add_argument("--name", help="select a root with this exact name")
    detail = explain.add_mutually_exclusive_group()
    detail.add_argument("--arguments", action="store_true", help="show recorded parameter outcomes")
    detail.add_argument("--specialization", action="store_true", help="show recorded generic substitutions")
    explain.add_argument("--argument", help="limit --arguments to one parameter")
    explain.add_argument("--format", choices=("text", "json"), default="text")
    explain.add_argument("-o", "--output", help="write output to a file instead of stdout")
    explain.set_defaults(handler=_explain)

    impact = commands.add_parser("impact", help="Show reverse dependencies for a compiled target")
    impact.add_argument("target", help="module:object composition target")
    impact_selection = impact.add_mutually_exclusive_group(required=True)
    impact_selection.add_argument("service", nargs="?", help="module:attribute service type")
    impact_selection.add_argument("--path", help="manifest path for an exact occurrence")
    impact.add_argument("--match", choices=("occurrence", "registration"), default="registration")
    impact.add_argument("--name", help="select a registration with this exact name")
    impact.add_argument("--include-deferred", action="store_true", help="Cross typed-provider deferred targets")
    impact.add_argument("--all", action="store_true", help="Resolve --path against every compiled root")
    impact.add_argument("--format", choices=("text", "mermaid", "json"), default="text")
    impact.add_argument("-o", "--output", help="write output to a file instead of stdout")
    impact.set_defaults(handler=_impact)

    sharing = commands.add_parser("sharing", help="Show static cache-sharing groups")
    sharing.add_argument("target", help="module:object composition target")
    sharing.add_argument("service", nargs="?", help="optional module:attribute service type")
    sharing.add_argument("--path", help="manifest path for an exact occurrence")
    sharing.add_argument("--format", choices=("text", "mermaid", "json"), default="text")
    sharing.add_argument("-o", "--output", help="write output to a file instead of stdout")
    sharing.set_defaults(handler=_sharing)

    activation = commands.add_parser("activation", help="Show static activation obligations for a root")
    activation.add_argument("target", help="module:object composition target")
    activation_selection = activation.add_mutually_exclusive_group(required=True)
    activation_selection.add_argument("service", nargs="?", help="module:attribute service type")
    activation_selection.add_argument("--path", help="manifest path for an exact root occurrence")
    activation.add_argument("--scenario", choices=("cold", "warm_singletons", "warm_scope"), default="cold")
    activation.add_argument("--format", choices=("text", "mermaid", "json"), default="text")
    activation.add_argument("-o", "--output", help="write output to a file instead of stdout")
    activation.set_defaults(handler=_activation)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except ContainerBuildError as error:
        if error.report is not None and getattr(args, "format", "text") == "json":
            print(error.report.to_json())
        else:
            print(str(error), file=sys.stderr)
        return 1
    except Exception as error:
        print(f"clean-ioc: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
