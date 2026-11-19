"""Fresh serial native prerequisite samples; never sync environments or edit old evidence."""
from pathlib import Path
import json,os,subprocess,sys,hashlib
OUT=Path(__file__).resolve().parent
P=Path(json.loads((OUT/'baseline-preservation.json').read_text())['root'])
PROBE=P/'consumer-evidence/native_probe.py'
rows=[]
for trace in (False,True):
    for sample in range(3):
        policies=['baseline-full','run','analysis']
        if sample%2: policies.reverse()
        for app in ('api','worker'):
            for policy in policies:
                source=P/('consumer-original' if policy=='baseline-full' else 'consumer-current')
                clean=source/'cop-env/lib/python3.14/site-packages' if policy=='baseline-full' else P/'current-source'
                env=dict(os.environ,PYTHONPATH=os.pathsep.join(map(str,[clean,source/'cop-source',source/'bark-source'])),PYTHONHASHSEED='0')
                label=f'{app}-{policy}-{sample}-'+('trace' if trace else 'normal')
                args=[str(source/'cop-env/bin/python'),str(PROBE),app,policy]+(['--trace'] if trace else [])
                r=subprocess.run(args,env=env,cwd=source/'cop-source',text=True,capture_output=True)
                # Full stderr may contain private configuration. Preserve outside the repository.
                raw=P/'prerequisite-samples'; raw.mkdir(exist_ok=True)
                (raw/(label+'.stdout')).write_text(r.stdout); (raw/(label+'.stderr')).write_text(r.stderr)
                if r.returncode: raise RuntimeError(f'{label} failed; see private saved stderr')
                row=json.loads(r.stdout.splitlines()[-1]); rows.append(dict(label=label,**row))
                (OUT/'native-baseline-samples.json').write_text(json.dumps(rows,indent=2)+'\n')
                print(label,row['clean_container_sha256'],row['selected_registrations'],flush=True)
for label,source in [('current',P/'current-source'),('task10-11',P/'task10-11-source')]:
    code='import clean_ioc,hashlib,inspect,json; from clean_ioc import ContainerBuilder; b=ContainerBuilder(); b.register(int,instance=7); c=b.build(); assert c.resolve(int)==7; print(json.dumps({"import":clean_ioc.__file__,"sha256":hashlib.sha256(open(inspect.getfile(ContainerBuilder),"rb").read()).hexdigest()}))'
    r=subprocess.run([str(P/'library-env/bin/python'),'-c',code],env=dict(os.environ,PYTHONPATH=str(source)),cwd='/tmp',capture_output=True,text=True,check=True)
    (OUT/(label+'-reproduction.json')).write_text(r.stdout)
print('Baseline reproducibility verified',flush=True)
