"""Publish a frozen research snapshot with guarded GitHub tree/commit/ref operations."""
import argparse,hashlib,json,subprocess
from pathlib import Path
import requests
RUN=Path(__file__).resolve().parent
PUB=RUN/'publication'
PREFIX='lora-training/experiments/2026-10-10-round2/'
parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['prereg','final'],required=True);args=parser.parse_args()
phase=args.phase
baseline=json.loads((PUB/'baseline.json').read_text())
assert baseline['repository']=='szaaaaaa/C_manager' and baseline['branch']=='main'
expected=baseline['expected_parent']
if phase=='final':
    previous=json.loads((PUB/'publication-prereg.json').read_text());assert previous['status']=='published_verified'
    expected=previous['commit_sha']
    assert json.loads((RUN/'final-verify.json').read_text())['status']=='passed'
assert json.loads((RUN/'freeze.json').read_text())['status']=='approved'
entries=[];inventory=[]
for path in sorted(RUN.rglob('*')):
    if not path.is_file(): continue
    rel=path.relative_to(RUN)
    if any(part in {'publication','__pycache__','adapter','checkpoints'} for part in rel.parts): continue
    if path.suffix.lower() not in {'.md','.json','.jsonl','.py','.ps1','.txt','.log','.csv'}: continue
    if phase=='prereg' and path.name in {'progress.md','prepare_blind_review.py'}: continue
    assert path.stat().st_size<2*1024*1024,'Oversized archive file: '+str(rel)
    raw=path.read_bytes(); content=raw.decode('utf-8')
    remote=PREFIX+rel.as_posix();assert '..' not in Path(remote).parts
    entries.append({'path':remote,'mode':'100644','type':'blob','content':content})
    inventory.append({'path':remote,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
if phase=='final':
    for remote,local in [('README.md','README.md'),('lora-training/README.md','training-README.md')]:
        path=PUB/local;assert path.is_file()
        raw=path.read_bytes();entries.append({'path':remote,'mode':'100644','type':'blob','content':raw.decode('utf-8')})
        inventory.append({'path':remote,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
assert len({e['path'] for e in entries})==len(entries) and len(entries)>=30
assert all(e['path'] in {'README.md','lora-training/README.md'} or e['path'].startswith(PREFIX) for e in entries)
payload={'expected_parent':expected,'phase':phase,'files':len(entries),'entries':entries}
encoded=json.dumps(payload,ensure_ascii=False).encode('utf-8');assert len(encoded)<25*1024*1024
(PUB/f'inventory-{phase}.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(PUB/f'payload-{phase}.json').write_bytes(encoded)
audit={'phase':phase,'status':'preparing','expected_parent':expected,'files':len(entries),'payload_bytes':len(encoded)}
audit_path=PUB/f'publication-{phase}.json';assert not audit_path.exists(),'Do not replay a publication with an unknown outcome'
def save(): audit_path.write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
token=subprocess.check_output(['gh','auth','token'],text=True).strip()
s=requests.Session();s.headers.update({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
def request(method,path,body=None):
    r=s.request(method,'https://api.github.com/repos/szaaaaaa/C_manager'+path,json=body,timeout=(10,45));r.raise_for_status();return r.json()
try:
    head=request('GET','/git/ref/heads/main')['object']['sha'];assert head==expected,'Remote changed; reconcile before publication'
    parent=request('GET','/git/commits/'+head)
    tree=request('POST','/git/trees',{'base_tree':parent['tree']['sha'],'tree':entries})
    audit.update(status='tree_created',tree_sha=tree['sha']);save()
    title='research: freeze round 2 expression and abstention controls' if phase=='prereg' else 'research: publish round 2 controlled LoRA results and correct readmes'
    commit=request('POST','/git/commits',{'message':title,'tree':tree['sha'],'parents':[head]})
    audit.update(status='commit_created',commit_sha=commit['sha']);save()
    assert request('GET','/git/ref/heads/main')['object']['sha']==head,'Concurrent update detected'
    request('PATCH','/git/refs/heads/main',{'sha':commit['sha'],'force':False})
    observed=request('GET','/git/ref/heads/main')['object']['sha'];assert observed==commit['sha']
    nodes=request('GET','/git/trees/'+tree['sha']+'?recursive=1');assert not nodes.get('truncated')
    remote={node['path']:node['sha'] for node in nodes['tree'] if node['type']=='blob'}
    for entry in entries:
        raw=entry['content'].encode('utf-8');want=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        assert remote.get(entry['path'])==want,entry['path']
    audit.update(status='published_verified',observed_head=observed,verified_remote_blobs=len(entries),url='https://github.com/szaaaaaa/C_manager/commit/'+observed);save()
    print(json.dumps(audit),flush=True)
except Exception as error:
    audit.update(status='error_or_unknown',error_type=type(error).__name__);save();print(json.dumps(audit),flush=True);raise
