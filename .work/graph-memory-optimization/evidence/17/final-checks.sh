#!/bin/sh
set -eu
TASK17_HERE=.work/graph-memory-optimization/evidence/17
TASK17_TESTS='tests/test_intermediate_occurrence_lifetimes.py tests/test_callback_snapshot_sharing.py tests/test_activation_cache_lifetimes.py tests/test_shared_draft_definitions.py tests/test_shared_component_definitions.py tests/test_decorator_template_feasibility.py tests/test_decorator_template_compilation.py tests/test_registration_templates.py tests/test_graph_artifact_experiment.py tests/test_build_modes.py tests/test_validation_evidence_lifetime.py tests/test_managed_providers.py tests/test_typed_providers.py tests/test_boundaries.py'
.venv/bin/pytest -q $TASK17_TESTS > "$TASK17_HERE/focused.txt" 2>&1
make ci > "$TASK17_HERE/make-ci.txt" 2>&1
.venv/bin/mkdocs build --strict > "$TASK17_HERE/docs-strict.txt" 2>&1
for TASK17_VERSION in 3.11 3.12 3.13; do
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --isolated --no-project --python "$TASK17_VERSION" --with 'pytest>=8,<10' --with pytest-asyncio --with funcie --with typetoolbox --with typing_extensions --with assertive python -m pytest -p pytest_asyncio.plugin -q $TASK17_TESTS > "$TASK17_HERE/python$TASK17_VERSION.txt" 2>&1
done
git diff --check > "$TASK17_HERE/diff-check.txt"
