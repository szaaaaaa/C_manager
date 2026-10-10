"""Independent CPU verification of frozen inputs and actual NF4 study artifacts."""
import hashlib,json,math,statistics
from pathlib import Path
RUN=Path(__file__).resolve().parent
FIELDS=['dtype','shape','raw_sha256','float32_value_sha256','quant_state_sha256','device','requires_grad']
def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
freeze=read(RUN/'freeze.json');assert freeze['status']=='approved'
for name,row in freeze['files'].items(): assert sha(RUN/name)==row['sha256'],name
for row in freeze['data_files'].values(): assert sha(Path(row['path']))==row['sha256']
checks={'status':'passed','frozen_protocol_files':len(freeze['files']),'training':{},'evaluation':{},'limits':'Arithmetic, bytes, parameter and quant-state checks do not verify semantic truth, all hidden runtime buffers, physical file contents or deletion safety.'}
for n in range(1,4):
    name=f'exp_{n:03d}';directory=RUN/'experiments'/name;r=read(directory/'result.json');m=r['metrics']
    assert r['status']=='success' and r['exit_code']==0 and r['actual_steps']==40
    assert m['finite_loss_and_gradients'] and m['changed_base_parameter_count']==0 and m['changed_lora_parameter_count']==64
    grads=m['gradient_observations'];assert len(grads)==40
    assert all(math.isfinite(g['post_clip_grad_norm']) and g['post_clip_grad_norm']>0 for g in grads)
    before=read(directory/'base_after_step0_before_training.json');after=read(directory/'base_after_training_before_final_eval.json')
    assert before.keys()==after.keys() and len(before)==723
    assert sum(v['quant_state_sha256'] is not None for v in before.values())==346
    assert all(before[k][f]==after[k][f] for k in before for f in FIELDS)
    assert all(not p['requires_grad'] and p['device'].startswith('cuda') for p in after.values())
    manifest=read(directory/'adapter-manifest.json');assert manifest['selected_checkpoint_step'] in {20,40}
    selected=Path(manifest['selected_checkpoint'])
    for row in manifest['files']:
        file=directory/'adapter'/row['file'];assert file.stat().st_size==row['bytes'] and sha(file)==row['sha256']==sha(selected/row['file'])
    assert manifest['selection_basis'].startswith('Only shared validation NLL')
    checks['training'][name]={'steps':40,'frozen_base_parameters':723,'frozen_quant_states':346,'changed_lora_tensors':64,'selected_step':manifest['selected_checkpoint_step'],'selected_nll':manifest['selected_checkpoint_validation_nll'],'elapsed_seconds':r['elapsed_seconds']}
training_bases=[read(RUN/'experiments'/f'exp_{n:03d}'/'base_after_step0_before_training.json') for n in range(1,4)]
assert all(state.keys()==training_bases[0].keys() and all(state[k][f]==training_bases[0][k][f] for k in state for f in FIELDS) for state in training_bases)
checks['matched_training_base']={'conditions':3,'parameters':723,'quant_states':346,'fields':FIELDS,'lora_initial_hashes_persisted':False}
cases=read(RUN/'data/eval_cases.json');assert len(cases)==72
configs=[];messages=[];runtime=[];records_by_run={}
for n in range(4,8):
    name=f'exp_{n:03d}';directory=RUN/'experiments'/name;r=read(directory/'result.json');m=r['metrics'];config=read(directory/'executed_config.json')
    rows=[json.loads(line) for line in (directory/'records.jsonl').read_text(encoding='utf-8').splitlines()]
    assert r['status']=='success' and r['exit_code']==0 and rows==r['records'] and len(rows)==72
    assert [row['id'] for row in rows]==[case['id'] for case in cases]
    for case,row in zip(cases,rows):
        assert row['path']==case['path'] and row['answer'] and row['raw_output'].endswith('<|im_end|>')
        assert not row['thinking_leak'] and not row['truncated'] and row['input_tokens']+256<=2048
        assert row['messages']==[{'role':'system','content':case['instruction']},{'role':'user','content':case['input']}]
        assert row['cue_checked']==(case['subset']=='historical24')
        if not row['cue_checked']: assert row['cue_pass'] is None
    assert m['completed_cases']==72 and all(m[f]==0 for f in ['empty_answer_count','thinking_leak_count','truncated_answer_count'])
    assert statistics.median(row['seconds'] for row in rows)==m['latency_median_seconds']
    assert config['generation']=={'do_sample':False,'max_new_tokens':256,'enable_thinking':False,'seed':42}
    assert sha(directory/'executed_training.py')==config['executed_runner_sha256']==sha(RUN/'training.py')
    configs.append(config);messages.append([row['messages'] for row in rows]);runtime.append(read(directory/'base_runtime_after_warmup.json'));records_by_run[name]=rows
    checks['evaluation'][name]={'cases':72,'subsets':m['subset_metrics'],'median_seconds':m['latency_median_seconds'],'elapsed_seconds':r['elapsed_seconds']}
assert all(m==messages[0] for m in messages)
assert all(c['inputs']==configs[0]['inputs'] and c['engine']==configs[0]['engine'] and c['generation']==configs[0]['generation'] for c in configs)
assert len(runtime[0])==723 and sum(v['quant_state_sha256'] is not None for v in runtime[0].values())==346
assert all(state.keys()==runtime[0].keys() and all(state[k][f]==runtime[0][k][f] for k in state for f in FIELDS) for state in runtime)
old=[json.loads(line) for line in (RUN.parent/'exp_20261010_111944/experiments/exp_015/records.jsonl').read_text(encoding='utf-8').splitlines()]
assert [r['messages'] for r in old]==messages[0][:24]
checks['historical_repeat_exact_answers']=sum(a['answer']==b['answer'] for a,b in zip(old,records_by_run['exp_004'][:24]))
checks['matched_evaluation_base']={'parameters':723,'quant_states':346,'same_input_messages':72,'same_fields':FIELDS}
(RUN/'ml-verify.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps(checks,ensure_ascii=False))

