"""Task22 focused correctness and quality checks; no performance measurements."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
prior = json.loads((OUT.parent / '21' / 'verification.json').read_text())
pytest = prior[0]['command'][1:]
pytest[2:2] = [
    'tests/test_execution_evidence_capture.py',
    'tests/test_decorator_template_diagnostics.py::test_source_and_target_decisions_are_frozen_and_do_not_replay_callbacks',
    'tests/test_decorator_template_diagnostics.py::test_generic_source_and_target_projections_remain_separate',
    'tests/test_decorator_template_diagnostics.py::test_independent_overlapping_policies_keep_both_identities',
    'tests/test_decorator_template_diagnostics.py::test_private_boundary_facts_keep_declaration_and_target_context',
    'tests/test_registration_templates.py::test_structural_source_filters_keep_the_complete_undecorated_source_view',
    'tests/test_registration_templates.py::test_saved_metadata_views_cannot_start_compilation_after_source_selection',
    'tests/test_registration_templates.py::test_generated_factory_cleanup_and_scoped_identity',
    'tests/test_registration_templates.py::test_generated_registration_census_records_source_and_template',
    'tests/test_callback_snapshot_sharing.py::test_snapshot_generic_cache_keeps_conditional_identity',
    'tests/test_callback_snapshot_sharing.py::test_draft_snapshot_preserves_every_field_without_second_record',
]
files = ['clean_ioc/container.py', 'clean_ioc/_decorator_templates.py', 'clean_ioc/_registration_templates.py',
         'tests/test_execution_evidence_capture.py', 'tests/test_decorator_template_diagnostics.py',
         'tests/test_registration_templates.py']
checks = [
    ('pytest', [sys.executable, *pytest]),
    ('ruff', [str(ROOT / '.venv/bin/ruff'), 'check', *files]),
    ('format', [str(ROOT / '.venv/bin/ruff'), 'format', '--check', *files]),
    ('ty', [str(ROOT / '.venv/bin/ty'), 'check', *files[:3], '--output-format', 'concise']),
]
results = []
for name, command in checks:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (OUT / f'{name}-final.log').write_text(result.stdout + result.stderr)
    results.append({'check': name, 'command': command, 'exit_code': result.returncode})
    print(name, result.returncode, (result.stdout + result.stderr).splitlines()[-1:])
(OUT / 'verification.json').write_text(json.dumps(results, indent=2) + '\n')
raise SystemExit(any(result['exit_code'] for result in results))
