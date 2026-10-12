"""Task23 functional/ownership gate; no performance measurements."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
prior = json.loads((OUT.parent / '22' / 'verification.json').read_text())
pytest = prior[0]['command'][1:]
pytest[2:2] = [
    'tests/test_execution_features.py',
    'tests/test_resolution_profiler.py',
    *['tests/test_warmup_plans.py::' + name for name in (
        'test_named_default_filters_and_fallback_are_frozen',
        'test_whole_plan_preflight_async_dependency_and_cleanup',
        'test_base_exception_stops_later_targets',
        'test_cancellation_stops_later_targets_and_retry_uses_same_owner',
        'test_concurrent_warmup_and_ordinary_resolution_share_singleton',
        'test_unknown_and_closed_runtime_reject_before_activation',
        'test_closed_pattern_explicit_demand_and_fallback',
        'test_decorators_preconfiguration_and_promoted_resource_cleanup',
        'test_shared_failing_dependency_is_retried_for_later_target',
        'test_profiler_observes_existing_request_activation_cache_and_cleanup_identities',
        'test_async_concurrent_runs_and_resolves_initialize_once',
        'test_nominal_newtype_and_union_closed_keys',
        'test_template_decorated_closed_generic_demand_is_frozen',
    )],
]
files = ['clean_ioc/container.py', 'clean_ioc/instrumentation.py', 'clean_ioc/warmup.py', 'clean_ioc/__init__.py',
         'tests/test_execution_features.py', 'tests/test_resolution_profiler.py', 'tests/test_execution_plan.py',
         'tests/test_execution_evidence_capture.py', 'tests/test_analysis_pipeline.py', 'tests/test_build_matrix.py',
         'tests/test_factory_return_types.py', 'tests/test_policies.py', 'tests/test_resource_ownership.py']
checks = [
    ('pytest', [sys.executable, *pytest]),
    ('ruff', [str(ROOT / '.venv/bin/ruff'), 'check', *files]),
    ('format', [str(ROOT / '.venv/bin/ruff'), 'format', '--check', *files]),
    ('ty', [str(ROOT / '.venv/bin/ty'), 'check', *files[:4], '--output-format', 'concise']),
]
results = []
for name, command in checks:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (OUT / f'{name}-final.log').write_text(result.stdout + result.stderr)
    results.append({'check': name, 'command': command, 'exit_code': result.returncode})
    print(name, result.returncode, (result.stdout + result.stderr).splitlines()[-1:])
(OUT / 'verification.json').write_text(json.dumps(results, indent=2) + '\n')
raise SystemExit(any(result['exit_code'] for result in results))
