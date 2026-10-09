"""Reuse execution-focused regression tests with reduced metadata on both builders.

Run serially outside memory measurements:
python -m benchmarks.graph_resolution_only_checks
"""

import ast
import inspect
import textwrap

import pytest

from clean_ioc import ContainerBuilder, ScopeBuilder

FILES = (
    "tests/test_managed_providers.py",
    "tests/test_typed_providers.py",
    "tests/test_provider_maps.py",
    "tests/test_per_call_scopes.py",
    "tests/test_per_call_scope_acceptance.py",
    "tests/test_type_alias_lookup_paths.py",
)


class ExecutionOnly:
    def pytest_collection_modifyitems(self, config, items):
        selected, inspection = [], []
        for item in items:
            source = ast.parse(textwrap.dedent(inspect.getsource(item.obj)))
            if any(
                isinstance(node, ast.Attribute) and node.attr in ("graph", "validation_report")
                for node in ast.walk(source)
            ):
                inspection.append(item)
            else:
                selected.append(item)
        items[:] = selected
        config.hook.pytest_deselected(items=inspection)


def main():
    originals = [(builder, builder.build) for builder in (ContainerBuilder, ScopeBuilder)]

    def reduced_build(original):
        def invoke(self, **options):
            options["explain_metadata"] = False
            return original(self, **options)

        return invoke

    try:
        for builder, original in originals:
            setattr(builder, "build", reduced_build(original))
        return pytest.main(["-q", *FILES], plugins=[ExecutionOnly()])
    finally:
        for builder, original in originals:
            setattr(builder, "build", original)


if __name__ == "__main__":
    raise SystemExit(main())
