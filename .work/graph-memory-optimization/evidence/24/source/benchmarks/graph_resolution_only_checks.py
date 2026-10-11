"""Run execution-focused regression tests against the public build() API.

Run serially outside memory measurements:
python -m benchmarks.graph_resolution_only_checks
"""

import ast
import inspect
import textwrap

import pytest

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
            if any(isinstance(node, ast.Attribute) and node.attr in ("graph", "analyse") for node in ast.walk(source)):
                inspection.append(item)
            else:
                selected.append(item)
        items[:] = selected
        config.hook.pytest_deselected(items=inspection)


def main():
    return pytest.main(["-q", *FILES], plugins=[ExecutionOnly()])


if __name__ == "__main__":
    raise SystemExit(main())
