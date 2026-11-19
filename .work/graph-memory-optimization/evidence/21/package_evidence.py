"""Freeze task-relative source and reconstruct it without changing historical evidence."""
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
BEFORE = json.loads((OUT / 'before-source.json').read_text())
CHANGED = [*BEFORE, 'tests/test_execution_plan.py']

def digest(content):
    return hashlib.sha256(content).hexdigest()

patch = []
records = []
for name in CHANGED:
    before = (OUT / 'before' / name).read_bytes() if name in BEFORE else b''
    if name in BEFORE:
        assert digest(before) == BEFORE[name]
    after = (ROOT / name).read_bytes()
    snapshot = OUT / 'after' / (name + '.txt')
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(after)
    records.append({'path': name, 'before_sha256': None if name not in BEFORE else digest(before),
                    'after_sha256': digest(after), 'snapshot': str(snapshot.relative_to(ROOT))})
    patch.extend(difflib.unified_diff(before.decode().splitlines(keepends=True), after.decode().splitlines(keepends=True),
        fromfile='a/'+name if name in BEFORE else '/dev/null', tofile='b/'+name))
patch_path = OUT / 'task21.patch'
patch_path.write_text(''.join(patch))
supporting = {str(path.relative_to(ROOT)): digest(path.read_bytes())
              for path in sorted((ROOT / 'clean_ioc').rglob('*.py'))}
manifest = {'base_compiler_sha256': BEFORE['clean_ioc/container.py'], 'changed':records,
            'supporting_package_sha256':supporting, 'patch_sha256':digest(patch_path.read_bytes()),
            'python':sys.version, 'platform':platform.platform(), 'performance_measurements':False}
(OUT / 'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
names = {'_ExecutionPlan','_PlanSet','_project_execution_plan','_finalize_execution','_prepare_compilation',
         '_compile_execution','_compile_with_report','_compile_warmup_plans','_observe_execution_bridge',
         'AnalysisResult','compile_execution','_compile_execution_roots','_release_declarations',
         '_build_execution','_build_plan','_from_blueprint'}
tree = ast.parse((ROOT / 'clean_ioc/container.py').read_text())
(OUT / 'source-symbols.json').write_text(json.dumps({node.name: node.lineno for node in ast.walk(tree)
    if isinstance(node,(ast.ClassDef,ast.FunctionDef)) and node.name in names},indent=2)+'\n')

reconstruction = Path(tempfile.mkdtemp(prefix='clean-ioc-task21-reproduced-')).resolve()
old = BASE / 'task20-reproduced-source'
for directory in ('clean_ioc','tests'):
    shutil.copytree(old/directory, reconstruction/directory, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copy2(old/'pyproject.toml', reconstruction/'pyproject.toml')
for name, sha in BEFORE.items():
    assert digest((reconstruction/name).read_bytes()) == sha, name
applied = subprocess.run(['patch','-p1','-i',str(patch_path)],cwd=reconstruction,capture_output=True,text=True)
(OUT/'patch-reproduction.log').write_text(applied.stdout+applied.stderr)
assert applied.returncode == 0
for name in CHANGED:
    assert (reconstruction/name).read_bytes() == (ROOT/name).read_bytes(), name
command = json.loads((OUT/'verification.json').read_text())[0]['command']
command[0] = str(BASE/'library-env/bin/python')
environment = dict(os.environ, PYTHONPATH=str(reconstruction))
identity = subprocess.run([command[0],'-c','import clean_ioc.container as c; print(c.__file__)'],
                         cwd=reconstruction,env=environment,capture_output=True,text=True,check=True)
assert identity.stdout.strip() == str(reconstruction/'clean_ioc/container.py')
result = subprocess.run(command,cwd=reconstruction,env=environment,capture_output=True,text=True)
(OUT/'reproduced-pytest.log').write_text(result.stdout+result.stderr)
(OUT/'reproduction.json').write_text(json.dumps({'cwd':str(reconstruction),'command':command,
    'PYTHONPATH':str(reconstruction),'import':identity.stdout.strip(),'byte_verified':CHANGED,
    'exit_code':result.returncode,'patch_sha256':digest(patch_path.read_bytes())},indent=2)+'\n')
print(result.stdout.splitlines()[-1:])
raise SystemExit(result.returncode)
