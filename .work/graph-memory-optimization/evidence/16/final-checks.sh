#!/bin/sh
set -eu
TASK16_HERE=.work/graph-memory-optimization/evidence/16
.venv/bin/pytest -q tests/test_callback_snapshot_sharing.py tests/test_shared_draft_definitions.py tests/test_shared_component_definitions.py tests/test_decorator_template_feasibility.py tests/test_decorator_template_compilation.py tests/test_registration_templates.py tests/test_graph_artifact_experiment.py tests/test_build_modes.py tests/test_validation_evidence_lifetime.py > "$TASK16_HERE/final-focused.txt" 2>&1
make ci > "$TASK16_HERE/make-ci.txt" 2>&1
.venv/bin/mkdocs build --strict > "$TASK16_HERE/docs-strict.txt" 2>&1
for TASK16_VERSION in 3.11 3.12 3.13; do
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --isolated --no-project --python "$TASK16_VERSION" --with 'pytest>=8,<10' --with pytest-asyncio --with funcie --with typetoolbox --with typing_extensions --with assertive python -m pytest -p pytest_asyncio.plugin -q tests/test_callback_snapshot_sharing.py tests/test_shared_draft_definitions.py tests/test_shared_component_definitions.py tests/test_decorator_template_feasibility.py tests/test_decorator_template_compilation.py tests/test_registration_templates.py tests/test_graph_artifact_experiment.py tests/test_build_modes.py tests/test_validation_evidence_lifetime.py > "$TASK16_HERE/python$TASK16_VERSION.txt" 2>&1
done
git diff --check > "$TASK16_HERE/diff-check.txt"
