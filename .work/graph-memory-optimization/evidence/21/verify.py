"""Task21 focused correctness/quality reproduction; no performance measurements."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
prior = json.loads((OUT.parent / '20' / 'verification.json').read_text())
pytest = prior[0]['command'][1:]
pytest[2:2] = [
    'tests/test_execution_plan.py',
    'tests/test_intermediate_occurrence_lifetimes.py::test_discarded_opaque_finalizer_observes_completed_freeze_and_tag_normalization',
    'tests/test_intermediate_occurrence_lifetimes.py::test_retained_opaque_facts_survive_freeze_then_detached_snapshot_owns_them',
]
files = ['clean_ioc/container.py', 'tests/test_execution_plan.py', 'tests/test_analysis_pipeline.py',
         'tests/test_factory_return_types.py', 'tests/test_policies.py', 'tests/test_build_matrix.py']
checks = [
    ('pytest', [sys.executable, *pytest]),
    ('ruff', [str(ROOT / '.venv/bin/ruff'), 'check', *files]),
    ('format', [str(ROOT / '.venv/bin/ruff'), 'format', '--check', *files]),
    ('ty', [str(ROOT / '.venv/bin/ty'), 'check', 'clean_ioc/container.py', '--output-format', 'concise']),
]
results=[]
for name, command in checks:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (OUT / f'{name}-final.log').write_text(result.stdout + result.stderr)
    results.append({'check':name, 'command':command, 'exit_code':result.returncode})
    print(name, result.returncode, (result.stdout + result.stderr).splitlines()[-1:])
(OUT / 'verification.json').write_text(json.dumps(results, indent=2)+'\n')
raise SystemExit(any(result['exit_code'] for result in results))
