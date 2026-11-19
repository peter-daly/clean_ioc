from pathlib import Path
import hashlib,json,shutil,subprocess,sys,platform
ROOT=Path.cwd(); OUT=ROOT/'.work/graph-memory-optimization/evidence/20'; PRIVATE=Path('/Users/peter.daly/.codex/task-baselines/clean-ioc-task20-20261010-v2')
shutil.copytree(PRIVATE/'current-source',PRIVATE/'task10-11-source',symlinks=True,dirs_exist_ok=True)
for src in (ROOT/'.work/graph-memory-optimization/evidence/18/sources/before').rglob('*.txt'):
    dst=PRIVATE/'task10-11-source'/src.relative_to(ROOT/'.work/graph-memory-optimization/evidence/18/sources/before').with_suffix('')
    shutil.copy2(src,dst)
subprocess.run(['cp','-cR',str(ROOT/'.venv'),str(PRIVATE/'library-env')],check=True)
checks={}
for label,p,expected in [('current',PRIVATE/'current-source/clean_ioc/container.py','1a60386b392058ac47143b3acf4fc82b1034b95f360854dae2e98ff6cde42223'),('task10-11',PRIVATE/'task10-11-source/clean_ioc/container.py','4a6c447812f7b313b96d2ce3bf09aab54207f24d88764b830a4c24010be5b683'),('consumer-original',PRIVATE/'consumer-original/cop-env/lib/python3.14/site-packages/clean_ioc/container.py','6253f5e38bd8819099db53514ede0d3c0efc4f451b3ea33f05c6e4a9932e4253')]:
    sha=hashlib.sha256(p.read_bytes()).hexdigest(); assert sha==expected,(label,sha)
    checks[label]={'path':str(p),'sha256':sha}
manifest={str(p.relative_to(PRIVATE)):hashlib.sha256(p.read_bytes()).hexdigest() for name in ['current-source','task10-11-source','consumer-evidence'] for p in (PRIVATE/name).rglob('*') if p.is_file()}
(OUT/'preserved-source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(OUT/'baseline-preservation.json').write_text(json.dumps({'root':str(PRIVATE),'checks':checks,'python':sys.version,'platform':platform.platform(),'revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'method':'Full source copies; complete consumer roots and environments cloned with cp -cR; task10/11 reconstructed using accepted task18 captured overlays on unchanged supporting sources. Private settings remain outside repository.'},indent=2)+'\n')
(OUT/'initial-status.txt').write_bytes(subprocess.check_output(['git','status','--short']))
(OUT/'initial-dirty.patch').write_bytes(subprocess.check_output(['git','diff','--binary']))
print(json.dumps(checks,indent=2))
