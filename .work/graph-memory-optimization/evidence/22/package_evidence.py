"""Record task22-only changes and verify an isolated patch reconstruction.

Copies only package/test source from task21's reconstruction. No environments,
historical evidence or consumer checkout trees are copied or edited.
"""
import ast
import difflib
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BASE = Path('/Users/peter.daly/.codex/task-baselines/clean-ioc-task20-20261010-v2')
BEFORE = {record['path']: record['sha256'] for record in json.loads((OUT/'before-manifest.json').read_text())}
CHANGED = [*BEFORE, 'tests/test_execution_evidence_capture.py']

def digest(content):
    return hashlib.sha256(content).hexdigest()

patch = []
records = []
for name in CHANGED:
    before = (OUT/'before'/name).read_bytes() if name in BEFORE else b''
    if name in BEFORE:
        assert digest(before) == BEFORE[name], name
    after = (ROOT/name).read_bytes()
    records.append({'path': name, 'before_sha256': BEFORE.get(name), 'after_sha256': digest(after)})
    patch.extend(difflib.unified_diff(before.decode().splitlines(keepends=True), after.decode().splitlines(keepends=True),
                                    fromfile='a/'+name if name in BEFORE else '/dev/null', tofile='b/'+name))
patch_path = OUT/'task22.patch'
assert not patch_path.exists(), 'Evidence already packaged; do not overwrite the recorded patch'
patch_path.write_text(''.join(patch))
manifest = {
    'base_compiler_sha256': BEFORE['clean_ioc/container.py'],
    'changed': records,
    'supporting_package_sha256': {str(path.relative_to(ROOT)): digest(path.read_bytes())
                                 for path in sorted((ROOT/'clean_ioc').rglob('*.py'))},
    'patch_sha256': digest(patch_path.read_bytes()),
    'python': sys.version, 'platform': platform.platform(), 'performance_measurements': False,
}
(OUT/'source-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
names = {'_SourceReference', '_DeclarationOrigin', '_source_reference', '_origin_evidence',
         '_source_evidence', '_materialize_blueprint_origins', '_GeneratedRegistrationBuilder',
         '_specialized_factory_dependencies', '_specialized_fallback_dependencies',
         '_compile_execution_roots', '_compile_provider_roots', '_compile_candidates',
         '_compile_decorators', '_clone_component_tree', '_located_rule_issue',
         '_expand_registration_templates', '_expand_decorator_templates', '_compile_warmup_plans',
         '_definition_origin', '_draft', '_select_without_diagnostics', '_materialize_registration_template'}
tree = ast.parse((ROOT/'clean_ioc/container.py').read_text())
(OUT/'source-symbols.json').write_text(json.dumps([
    {'name': node.name, 'line': node.lineno, 'end_line': node.end_lineno}
    for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names
], indent=2)+'\n')

old = Path(json.loads((OUT.parent/'21'/'reproduction.json').read_text())['cwd'])
reconstruction = Path(tempfile.mkdtemp(prefix='clean-ioc-task22-reproduced-')).resolve()
for directory in ('clean_ioc', 'tests'):
    shutil.copytree(old/directory, reconstruction/directory, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
shutil.copy2(old/'pyproject.toml', reconstruction/'pyproject.toml')
for name, sha in BEFORE.items():
    assert digest((reconstruction/name).read_bytes()) == sha, name
applied = subprocess.run(['patch', '-p1', '-i', str(patch_path)], cwd=reconstruction, capture_output=True, text=True)
(OUT/'patch-reproduction.log').write_text(applied.stdout+applied.stderr)
assert applied.returncode == 0
for name in CHANGED:
    assert (reconstruction/name).read_bytes() == (ROOT/name).read_bytes(), name
for name, sha in manifest['supporting_package_sha256'].items():
    assert digest((reconstruction/name).read_bytes()) == sha, name
command = json.loads((OUT/'verification.json').read_text())[0]['command']
command[0] = str(BASE/'library-env/bin/python')
environment = dict(os.environ, PYTHONPATH=str(reconstruction))
identity = subprocess.run([command[0], '-c', 'import clean_ioc.container as c; print(c.__file__)'],
                         cwd=reconstruction, env=environment, capture_output=True, text=True, check=True)
assert Path(identity.stdout.strip()).resolve() == reconstruction/'clean_ioc/container.py'
result = subprocess.run(command, cwd=reconstruction, env=environment, capture_output=True, text=True)
(OUT/'reproduced-pytest.log').write_text(result.stdout+result.stderr)
(OUT/'reproduction.json').write_text(json.dumps({
    'cwd': str(reconstruction), 'command': command, 'PYTHONPATH': str(reconstruction),
    'import': identity.stdout.strip(), 'byte_verified': CHANGED,
    'supporting_package_hashes_verified': len(manifest['supporting_package_sha256']),
    'exit_code': result.returncode, 'patch_sha256': digest(patch_path.read_bytes()),
}, indent=2)+'\n')
print(result.stdout.splitlines()[-1:])
raise SystemExit(result.returncode)
