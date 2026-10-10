"""Root preflight checks and a timestamped, immutable input/protocol freeze."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
RUN=Path(__file__).resolve().parent
ROOT=RUN.parents[1]
def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
manifest=read(RUN/'data/manifest.json')
assert manifest['dataset_counts']=={'train_A':160,'train_B':160,'train_C':160,'validation':32,'evaluation':72,'primary':48,'historical':24,'primary_abstention':20,'historical_abstention':7}
for name,row in manifest['files'].items():
    path=Path(row['path']).resolve();assert path==RUN/'data'/name
    assert path.is_relative_to(RUN/'data') and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],name
for path,expected in manifest['source_sha256'].items(): assert sha(Path(path))==expected,path
trains=[[json.loads(line) for line in (RUN/'data'/f'train_{a}.jsonl').read_text(encoding='utf-8').splitlines()] for a in 'ABC']
for a,b,c in zip(*trains):
    assert (a['instruction'],a['input'])==(b['instruction'],b['input'])
    if b['polarity']=='positive': assert b==c
    else: assert b['output']==c['output'] and b['evidence']=='ordinary_unknown' and c['evidence']!='ordinary_unknown'
check=read(RUN/'training_self_check.json');assert check['status']=='passed' and check['all_evaluation_inputs_equal'] and check['same_A_B_inputs']
assert all(r['train_records']==160 and r['validation_records']==32 and r['maximum_tokenized_length']<768 and r['prompt_padding_mask_valid'] and r['overlong_rejected'] for r in check['arms'])
audit=read(RUN/'data-audit.json');assert audit['status']=='passed',audit['status']
for name,row in audit['files'].items(): assert sha(RUN/'data'/name)==row['sha256'],name
protocols=[RUN/'plan.md',RUN/'rubric.md',RUN/'review-protocol.md',RUN/'sources.json',RUN/'data/manifest.json',RUN/'training_self_check.json',RUN/'diagnostic_self_check.json',RUN/'data-audit.json',RUN/'preflight-review.md']
protocols += [RUN/'experiments'/f'exp_{n:03d}'/'spec.md' for n in range(1,8)]
for n in range(1,8):
    directory=RUN/'experiments'/f'exp_{n:03d}'
    assert not (directory/'result.json').exists(),'No model execution before protocol freeze'
    cfg=read(directory/'config.json')
    assert cfg['seed']==42 and cfg['deadline_seconds']==1740 and not cfg['data_freeze_approved']
    assert cfg['data_manifest_sha256']==sha(RUN/'data/manifest.json')
    for row in cfg['inputs'].values(): assert sha(Path(row['path']))==row['sha256']
    if n<=3: assert cfg['training']['max_steps']==40 and cfg['training']['lora_r']==8 and cfg['training']['learning_rate']==5e-5
freeze={'status':'approved','run_id':RUN.name,'project_id':'46bb9df518194783a69ee24582b3b7c6','frozen_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'preflight':'Root file/hash/config/control checks and independent CPU data audit passed before GPU execution.','files':{str(path.relative_to(RUN)).replace('\\','/'):{'bytes':path.stat().st_size,'sha256':sha(path)} for path in protocols},'data_files':manifest['files'],'approved_gpu_runs':[f'exp_{n:03d}' for n in range(1,8)],'conditions':'Refresh config from these fixed inputs; only then set data_freeze_approved true. Preserve data, protocol and terminal results. No test checkpoint selection.'}
path=RUN/'freeze.json';assert not path.exists(),'Refusing to replace protocol freeze'
path.write_text(json.dumps(freeze,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'status':'approved','files':len(protocols),'time':freeze['frozen_at'],'sha256':sha(path)}))
