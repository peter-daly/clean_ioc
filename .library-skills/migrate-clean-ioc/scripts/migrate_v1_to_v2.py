#!/usr/bin/env python3
"""Preview or apply conservative Clean IoC 1 to 2 source migrations."""

from __future__ import annotations

import argparse
import ast
import difflib
import os
import sys
import tempfile
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

LIFESPANS = {
    "transient": "transient",
    "once_per_graph": "per_resolution",
    "scoped": "scoped",
    "singleton": "singleton",
}
COMPOSITION_METHODS = {"register", "register_decorator", "pre_configure", "apply_bundle"}
CONFIG_METHODS = {"register", "register_decorator", "pre_configure"}
LEGACY_METHODS = {
    "register_generic_subclasses",
    "register_generic_decorator",
    "expect_to_be_scoped",
    "patch_registration",
    "resolve_dependency_graph",
    "resolve_from_registration_id",
    "force_run_pre_configuration",
    "call_async",
    "call",
}
LEGACY_KEYWORDS = {
    "dependency_config",
    "registration_filter",
    "decorator_node_filter",
    "parent_node_filter",
    "scoped_teardown",
    "list_modifier",
}
SKIP_DIRS = {".git", ".venv", ".tox", "__pycache__", "build", "dist", "site"}


@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    replacement: str


@dataclass(frozen=True)
class Finding:
    line: int
    message: str


class Source:
    def __init__(self, value: str):
        self.value = value
        self.lines = value.splitlines(keepends=True)
        self.starts = [0]
        for line in self.lines:
            self.starts.append(self.starts[-1] + len(line))
        self.newline = "\r\n" if "\r\n" in value else "\n"

    def position(self, line: int, byte_column: int) -> int:
        # AST columns count UTF-8 bytes; Python string slices count code points.
        prefix = self.lines[line - 1].encode("utf-8")[:byte_column].decode("utf-8")
        return self.starts[line - 1] + len(prefix)

    def span(self, node: ast.expr | ast.stmt) -> tuple[int, int]:
        if node.end_lineno is None or node.end_col_offset is None:
            raise ValueError("AST node has no end position")
        return self.position(node.lineno, node.col_offset), self.position(node.end_lineno, node.end_col_offset)


def _name_used(node: ast.AST, identifier: str) -> bool:
    return any(isinstance(child, ast.Name) and child.id == identifier for child in ast.walk(node))


def _method_call(statement: ast.stmt, receiver: str, methods: set[str]) -> ast.Call | None:
    value = statement.value if isinstance(statement, (ast.Expr, ast.Assign, ast.AnnAssign)) else None
    if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Attribute):
        return None
    if not isinstance(value.func.value, ast.Name) or value.func.value.id != receiver:
        return None
    return value if value.func.attr in methods else None


def _resolve_statement(statement: ast.stmt, receiver: str) -> bool:
    if isinstance(statement, ast.Return):
        value = statement.value
        if isinstance(value, ast.Call):
            return _method_call(ast.Expr(value=value), receiver, {"resolve", "resolve_async"}) is not None
        return False
    return _method_call(statement, receiver, {"resolve", "resolve_async"}) is not None


def _straight_line_builds(tree: ast.Module, source: Source, constructor_names: set[str]) -> tuple[list[Edit], set[int]]:
    edits: list[Edit] = []
    converted_calls: set[int] = set()
    for owner in ast.walk(tree):
        if not isinstance(owner, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = owner.body
        for index, statement in enumerate(body):
            if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
                continue
            target, constructor = statement.targets[0], statement.value
            if not isinstance(target, ast.Name) or not isinstance(constructor, ast.Call):
                continue
            if not isinstance(constructor.func, ast.Name) or constructor.func.id not in constructor_names:
                continue
            if constructor.args or constructor.keywords:
                continue
            receiver = target.id
            next_index = index + 1
            while next_index < len(body):
                call = _method_call(body[next_index], receiver, COMPOSITION_METHODS)
                if call is None:
                    break
                if any(_name_used(arg, receiver) for arg in (*call.args, *(kw.value for kw in call.keywords))):
                    break
                next_index += 1
            if next_index == index + 1 or next_index >= len(body):
                continue
            if not _resolve_statement(body[next_index], receiver):
                continue
            # Never move a build ahead of a later mutation or rebind.
            if any(
                any(
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == receiver
                    and n.func.attr in COMPOSITION_METHODS | LEGACY_METHODS
                    for n in ast.walk(later)
                )
                or any(
                    isinstance(n, ast.Name) and n.id == receiver and isinstance(n.ctx, ast.Store)
                    for n in ast.walk(later)
                )
                for later in body[next_index + 1 :]
            ):
                continue
            indentation = source.lines[body[next_index].lineno - 1][
                : len(source.lines[body[next_index].lineno - 1])
                - len(source.lines[body[next_index].lineno - 1].lstrip(" \t"))
            ]
            start, end = source.span(constructor.func)
            edits.append(Edit(start, end, "ContainerBuilder"))
            insert = source.starts[body[next_index].lineno - 1]
            edits.append(Edit(insert, insert, f"{indentation}{receiver} = {receiver}.build(){source.newline}"))
            converted_calls.add(id(constructor))
    return edits, converted_calls


def transform(value: str) -> tuple[str, list[Finding]]:
    source = Source(value)
    tree = ast.parse(value)
    edits: list[Edit] = []
    findings: list[Finding] = []
    constructor_names: set[str] = set()
    builder_names: set[str] = set()
    lifespan_names: set[str] = set()
    builder_imported = False
    import_anchor: ast.ImportFrom | None = None

    for statement in tree.body:
        if not isinstance(statement, ast.ImportFrom) or statement.module not in {"clean_ioc", "clean_ioc.core"}:
            continue
        for alias in statement.names:
            if alias.name == "Container":
                constructor_names.add(alias.asname or alias.name)
                if statement.module == "clean_ioc" and import_anchor is None:
                    import_anchor = statement
            if alias.name == "Lifespan":
                lifespan_names.add(alias.asname or alias.name)
            if alias.name == "ContainerBuilder":
                builder_imported = builder_imported or (alias.asname or alias.name) == "ContainerBuilder"
                builder_names.add(alias.asname or alias.name)

    if import_anchor is not None:
        # A local binding with the same name makes the constructor's identity ambiguous.
        for identifier in tuple(constructor_names):
            if any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name == identifier
                or isinstance(node, ast.Name)
                and node.id == identifier
                and isinstance(node.ctx, ast.Store)
                or isinstance(node, ast.arg)
                and node.arg == identifier
                or isinstance(node, ast.ImportFrom)
                and node.module not in {"clean_ioc", "clean_ioc.core"}
                and any((alias.asname or alias.name) == identifier for alias in node.names)
                for node in ast.walk(tree)
            ):
                constructor_names.remove(identifier)
        if not builder_imported and any(
            isinstance(node, ast.Name) and node.id == "ContainerBuilder" and isinstance(node.ctx, ast.Store)
            for node in ast.walk(tree)
        ):
            constructor_names.clear()
        builds, converted = _straight_line_builds(tree, source, constructor_names)
        edits.extend(builds)
        if builds and not builder_imported:
            if import_anchor.end_lineno is None:
                raise ValueError("import has no end position")
            insert = source.starts[import_anchor.end_lineno]
            prefix = "" if source.lines[import_anchor.end_lineno - 1].endswith("\n") else source.newline
            edits.append(Edit(insert, insert, f"{prefix}from clean_ioc import ContainerBuilder{source.newline}"))
    else:
        converted = set()

    if any(
        isinstance(node, ast.Name)
        and node.id in lifespan_names
        and isinstance(node.ctx, ast.Store)
        or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name in lifespan_names
        or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(arg.arg in lifespan_names for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs))
        for node in ast.walk(tree)
    ):
        lifespan_names.clear()
    if any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and (
            any(alias.name == "Lifespan" or alias.asname in lifespan_names for alias in node.names)
            if isinstance(node, ast.Import)
            else node.module not in {"clean_ioc", "clean_ioc.core"}
            and any(alias.name == "Lifespan" or alias.asname in lifespan_names for alias in node.names)
        )
        for node in ast.walk(tree)
    ):
        lifespan_names.clear()

    receivers = {
        node.targets[0].id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id in constructor_names | builder_names
        and sum(
            isinstance(binding, ast.Name) and binding.id == node.targets[0].id and isinstance(binding.ctx, ast.Store)
            for binding in ast.walk(tree)
        )
        == 1
    }
    converted_lifespans: set[int] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in constructor_names and id(node) not in converted:
                findings.append(Finding(node.lineno, "Container() needs a manually placed build boundary"))
            if isinstance(node.func, ast.Name) and node.func.id == "DependencySettings":
                findings.append(Finding(node.lineno, "rewrite DependencySettings as V2 argument policies"))
            if isinstance(node.func, ast.Attribute) and node.func.attr in LEGACY_METHODS:
                findings.append(Finding(node.lineno, f"review removed V1 method {node.func.attr}()"))
            method = node.func.attr if isinstance(node.func, ast.Attribute) else None
            receiver_known = (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in receivers
            )
            for keyword in node.keywords:
                if keyword.arg == "lifespan" and receiver_known and method in COMPOSITION_METHODS:
                    member = keyword.value
                    if (
                        isinstance(member, ast.Attribute)
                        and isinstance(member.value, ast.Name)
                        and member.value.id in lifespan_names
                        and member.attr in LIFESPANS
                    ):
                        start, end = source.span(member)
                        edits.append(Edit(start, end, repr(LIFESPANS[member.attr])))
                        converted_lifespans.add(id(member))
                if keyword.arg == "dependency_config" and receiver_known and method in CONFIG_METHODS:
                    plain = isinstance(keyword.value, ast.Dict) and all(
                        isinstance(key, ast.Constant) and isinstance(key.value, str) and isinstance(item, ast.Constant)
                        for key, item in zip(keyword.value.keys, keyword.value.values, strict=True)
                    )
                    if plain:
                        start = source.position(keyword.lineno, keyword.col_offset)
                        edits.append(Edit(start, start + len("dependency_config"), "arguments"))
                        continue
                if keyword.arg in LEGACY_KEYWORDS:
                    findings.append(Finding(keyword.lineno, f"review V1 keyword {keyword.arg}="))
        elif isinstance(node, ast.Attribute) and node.attr in LIFESPANS:
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in lifespan_names
                and id(node) not in converted_lifespans
            ):
                findings.append(
                    Finding(node.lineno, "review V1 Lifespan member outside a supported lifespan= argument")
                )
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if any(
                name.startswith(
                    ("clean_ioc.registration_filters", "clean_ioc.node_filters", "clean_ioc.list_reduction_filters")
                )
                for name in modules
            ):
                findings.append(Finding(node.lineno, "rewrite legacy filters against clean_ioc.component_filters"))

    edits.sort(key=lambda edit: (edit.start, edit.end))
    if any(left.end > right.start for left, right in pairwise(edits)):
        raise ValueError("overlapping codemod edits")
    result = value
    for edit in reversed(edits):
        result = result[: edit.start] + edit.replacement + result[edit.end :]
    ast.parse(result)
    return result, sorted(set(findings), key=lambda finding: (finding.line, finding.message))


def python_files(paths: list[Path]):
    seen: set[Path] = set()
    for path in paths:
        if path.is_file():
            candidates = [path] if path.suffix == ".py" else []
        elif path.is_dir():
            candidates = []
            for root, dirs, names in os.walk(path):
                dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
                candidates.extend(Path(root) / name for name in sorted(names) if name.endswith(".py"))
        else:
            raise FileNotFoundError(path)
        for candidate in candidates:
            real = candidate.resolve()
            if real not in seen:
                seen.add(real)
                yield candidate


def write_atomic(path: Path, value: str) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(value.encode("utf-8"))
            os.chmod(temporary, path.stat().st_mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Python files or directories to inspect")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="apply proposed edits")
    mode.add_argument("--check", action="store_true", help="fail when edits or manual findings remain")
    args = parser.parse_args(argv)
    changed = False
    needs_review = False
    try:
        files = list(python_files(args.paths))
    except FileNotFoundError as error:
        parser.error(f"path not found: {error}")
    for path in files:
        try:
            original = path.read_bytes().decode("utf-8")
            updated, findings = transform(original)
        except (UnicodeError, SyntaxError, ValueError) as error:
            print(f"{path}: skipped: {error}", file=sys.stderr)
            needs_review = True
            continue
        if original != updated:
            changed = True
            if args.write:
                write_atomic(path, updated)
                print(f"updated {path}")
            else:
                sys.stdout.writelines(
                    difflib.unified_diff(
                        original.splitlines(keepends=True),
                        updated.splitlines(keepends=True),
                        fromfile=str(path),
                        tofile=str(path),
                    )
                )
        for finding in findings:
            print(f"{path}:{finding.line}: {finding.message}", file=sys.stderr)
            needs_review = True
    if args.check and (changed or needs_review):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
