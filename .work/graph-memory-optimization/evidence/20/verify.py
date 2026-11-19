"""Task20 correctness/quality checks. No performance measurement."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
SOURCES = [
    'clean_ioc/container.py', 'clean_ioc/components.py', 'clean_ioc/policies.py',
    'clean_ioc/tooling.py', 'clean_ioc/__init__.py', 'clean_ioc/matrix.py', 'clean_ioc/cli.py',
]
TEST_FILES = [
    'tests/test_analysis_pipeline.py', 'tests/test_build_matrix.py',
    'tests/test_factory_return_types.py', 'tests/test_policies.py',
]
RUNTIME = [
    'tests/test_per_call_scopes.py::test_deferred_activation_and_all_keywords_forward_unchanged',
    'tests/test_per_call_scopes.py::test_literal_self_keyword_is_forwarded_to_kwargs_contract',
    'tests/test_per_call_scopes.py::test_activation_and_method_failures_finalize_invocation_scope',
    'tests/test_per_call_scopes.py::test_unknown_factory_stream_result_is_rejected_before_scope_closes',
    'tests/test_per_call_scopes.py::test_unknown_factory_awaitable_result_is_rejected_before_scope_closes',
    'tests/test_resource_ownership.py::test_scoped_component_owns_transient_cleanup_at_scope_boundary',
    'tests/test_resource_ownership.py::test_runtime_contexts_remain_valid_for_short_lived_components',
    'tests/test_resource_ownership.py::test_cleanup_attempts_every_finalizer_and_aggregates_in_finalization_order',
    'tests/test_resource_ownership.py::test_one_cleanup_failure_is_reraised_unchanged',
    'tests/test_resource_ownership.py::test_closed_scope_rejects_runtime_operations_and_saved_resolution_context',
    'tests/test_resource_ownership.py::test_parent_close_does_not_close_an_independent_child_scope',
    'tests/test_resource_ownership.py::test_concurrent_singleton_activation_registers_one_promoted_finalizer',
]
COMMANDS = {
    'pytest': [sys.executable, '-m', 'pytest', *TEST_FILES, *RUNTIME, '-q', '--tb=short'],
    'ruff': [str(ROOT / '.venv/bin/ruff'), 'check', *SOURCES, *TEST_FILES],
    'format': [str(ROOT / '.venv/bin/ruff'), 'format', '--check', *SOURCES, *TEST_FILES],
    'ty': [str(ROOT / '.venv/bin/ty'), 'check', *SOURCES, '--output-format', 'concise'],
}
if __name__ == '__main__':
    results = []
    for name, command in COMMANDS.items():
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        (EVIDENCE / f'{name}-final.log').write_text(result.stdout + result.stderr)
        results.append({'check': name, 'command': command, 'exit_code': result.returncode})
        print(name, result.returncode, flush=True)
    (EVIDENCE / 'verification.json').write_text(json.dumps(results, indent=2) + '\n')
    assert all(result['exit_code'] == 0 for result in results), results
