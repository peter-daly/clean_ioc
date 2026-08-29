"""Command-line access to Clean IoC's compiled graph toolchain."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any, Sequence

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
    report = _filtered_report(scope.build_report, set(args.ignore))
    _write(report.to_json() if args.format == "json" else report.to_text(), None)
    if not report.is_valid or (args.strict and report.warnings):
        return 1
    return 0


def _graph(args: argparse.Namespace) -> int:
    graph = _load_scope(args.target).graph
    if args.format == "json":
        value = graph.manifest(all_roots=args.all).to_json()
    elif args.format == "mermaid":
        value = graph.to_mermaid(all_roots=args.all)
    else:
        value = graph.to_text(all_roots=args.all)
    _write(value, args.output)
    return 0


def _diff(args: argparse.Namespace) -> int:
    current = _load_scope(args.target).graph.manifest(all_roots=args.all)
    baseline = GraphManifest.from_json(Path(args.baseline).read_text(encoding="utf-8"))
    difference = current.diff(baseline)
    _write(difference.to_json() if args.format == "json" else difference.to_text(), None)
    return 0 if difference.is_empty else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clean-ioc", description="Inspect compiled Clean IoC component plans")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="Build a target and report compiler findings")
    check.add_argument("target", help="module:object composition target")
    check.add_argument("--format", choices=("text", "json"), default="text")
    check.add_argument("--strict", action="store_true", help="Fail when unsuppressed warnings remain")
    check.add_argument("--ignore", action="append", default=[], metavar="CODE", help="Ignore a warning code")
    check.set_defaults(handler=_check)

    graph = commands.add_parser("graph", help="Render or snapshot a compiled graph")
    graph.add_argument("target", help="module:object composition target")
    graph.add_argument("--format", choices=("text", "mermaid", "json"), default="text")
    graph.add_argument("--all", action="store_true", help="Include every compiled root")
    graph.add_argument("-o", "--output", help="Write output to a file instead of stdout")
    graph.set_defaults(handler=_graph)

    difference = commands.add_parser("diff", help="Compare a compiled graph with a JSON manifest")
    difference.add_argument("target", help="module:object composition target")
    difference.add_argument("baseline", help="baseline graph manifest")
    difference.add_argument("--format", choices=("text", "json"), default="text")
    difference.add_argument("--all", action="store_true", help="Compare every compiled root")
    difference.set_defaults(handler=_diff)
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
