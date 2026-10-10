import base64, hashlib, json, subprocess
from pathlib import Path
import requests
RUN=Path(__file__).resolve().parent
assert RUN==Path('D:/small-model-experiments/outputs/exp_20261010_150741')
PUB=RUN/'publication'; PUB.mkdir(exist_ok=True)
token=subprocess.check_output(['gh','auth','token'],text=True).strip()
s=requests.Session();s.headers.update({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
def get(path):
    r=s.get('https://api.github.com/repos/szaaaaaa/C_manager'+path,timeout=(10,30));r.raise_for_status();return r.json()
head=get('/git/ref/heads/main')['object']['sha']
meta={'repository':'szaaaaaa/C_manager','branch':'main','expected_parent':head,'files':[]}
for remote,local in [('README.md','README-before.md'),('lora-training/README.md','training-README-before.md')]:
    obj=get('/contents/'+remote+'?ref='+head)
    assert obj['encoding']=='base64' and obj['type']=='file'
    data=base64.b64decode(obj['content']); assert len(data)<300000
    path=PUB/local; assert not path.exists(), 'Read-only remote snapshot already exists'
    path.write_bytes(data)
    meta['files'].append({'remote':remote,'local':local,'blob_sha':obj['sha'],'sha256':hashlib.sha256(data).hexdigest()})
(PUB/'baseline.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'head':head,'readme_files':len(meta['files'])}))
