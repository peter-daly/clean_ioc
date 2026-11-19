"""Capture the task-relative patch and reproduce it without changing the workspace."""
import ast
import difflib
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
BASELINE = Path('/Users/peter.daly/.codex/task-baselines/clean-ioc-task20-20261010-v2')
BEFORE = BASELINE / 'current-source'
AFTER = BASELINE / 'task20-reproduced-source'
spec = importlib.util.spec_from_file_location('task20_verification', EVIDENCE / 'verify.py')
verification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification)
changed = verification.SOURCES + verification.TEST_FILES
patch = []
identities = []
for relative in changed:
    old = BEFORE / relative
    new = ROOT / relative
    patch.extend(difflib.unified_diff(
        old.read_text().splitlines(keepends=True) if old.exists() else [],
        new.read_text().splitlines(keepends=True),
        fromfile=f'a/{relative}' if old.exists() else '/dev/null', tofile=f'b/{relative}',
    ))
    identities.append({'path': relative,
                       'before': hashlib.sha256(old.read_bytes()).hexdigest() if old.exists() else None,
                       'after': hashlib.sha256(new.read_bytes()).hexdigest()})
patch_path = EVIDENCE / 'task20.patch'
patch_path.write_text(''.join(patch))
assert not AFTER.exists(), 'Never overwrite a captured source reconstruction'
shutil.copytree(BEFORE, AFTER, symlinks=True)
result = subprocess.run(['patch', '-p1', '--batch', '--forward', '-i', str(patch_path)], cwd=AFTER, text=True, capture_output=True)
(EVIDENCE / 'patch-reproduction.log').write_text(result.stdout + result.stderr)
assert result.returncode == 0, result.stderr
for relative in changed:
    assert (AFTER / relative).read_bytes() == (ROOT / relative).read_bytes(), relative
manifest = []
for path in sorted((AFTER / 'clean_ioc').rglob('*.py')):
    manifest.append({'path': str(path.relative_to(AFTER)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
for relative in ['pyproject.toml', 'uv.lock', *verification.TEST_FILES]:
    path = AFTER / relative
    if path.exists():
        manifest.append({'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
symbols = []
for relative in verification.SOURCES:
    tree = ast.parse((ROOT / relative).read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append({'file': relative, 'symbol': node.name, 'line': node.lineno})
(EVIDENCE / 'source-symbols.json').write_text(json.dumps(symbols, indent=2) + '\n')
(EVIDENCE / 'final-source-manifest.json').write_text(json.dumps({
    'before_root': str(BEFORE), 'reproduced_root': str(AFTER),
    'patch_sha256': hashlib.sha256(patch_path.read_bytes()).hexdigest(),
    'changed_files': identities, 'supporting_source': manifest,
}, indent=2) + '\n')
env = dict(os.environ, PYTHONPATH=str(AFTER))
python = str(BASELINE / 'library-env/bin/python')
smoke = subprocess.run([python, '-c',
    'import clean_ioc.container as c,hashlib,json; from pathlib import Path; '
    'p=Path(c.__file__); print(json.dumps({"import":str(p),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}))'],
    cwd=AFTER, env=env, text=True, capture_output=True, check=True)
identity = json.loads(smoke.stdout)
assert Path(identity['import']).is_relative_to(AFTER), identity
command = [python, '-m', 'pytest', *verification.TEST_FILES, *verification.RUNTIME, '-q', '--tb=short']
result = subprocess.run(command, cwd=AFTER, env=env, text=True, capture_output=True)
(EVIDENCE / 'reproduced-pytest.log').write_text(result.stdout + result.stderr)
(EVIDENCE / 'reproduction.json').write_text(json.dumps({
    'identity': identity, 'patch_applied': True, 'byte_verified': changed,
    'command': command, 'cwd': str(AFTER), 'exit_code': result.returncode,
}, indent=2) + '\n')
assert result.returncode == 0, result.stdout + result.stderr
print(json.dumps({'compiler': identity, 'reproduced': True}))
