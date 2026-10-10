"""Independently validate the new paired raw outputs and review arithmetic on CPU."""
import hashlib,json,math,statistics
from pathlib import Path
ROOT=Path.cwd(); RUN=ROOT/'outputs/exp_20261010_111944'
def read(path): return json.loads(path.read_text(encoding='utf-8'))
cases=read(ROOT/'inputs/eval_cases.json'); ids=[case['id'] for case in cases]
unknown={case['id'] for case in cases if case['knowledge'] is None or case.get('missing_evidence')}
assert len(ids)==len(set(ids))==24 and len(unknown)==7
paired=[];verified={}
for n in (14,15):
    eid=f'exp_{n:03d}'; d=RUN/'experiments'/eid
    result=read(d/'result.json'); records=[json.loads(line) for line in (d/'records.jsonl').read_text(encoding='utf-8').splitlines()]
    review=read(RUN/'reviews'/f'{eid}.json'); reviewed=review['cases']; metrics=review['metrics']
    assert result['status']=='success' and result['exit_code']==0 and result['records']==records
    assert [r['id'] for r in records]==ids and [r['id'] for r in reviewed]==ids
    assert result['eos_configuration']['actual_eos_token_id']==248046
    for case,row,judgment in zip(cases,records,reviewed):
        answer=row['answer']; expected_missing=[g for g in case['required'] if not any(w in answer for w in g)]
        expected_forbidden=[w for w in case['forbidden'] if w in answer]
        assert row['missing_cues']==expected_missing and row['forbidden_phrases']==expected_forbidden
        assert row['cue_pass']==(bool(answer.strip()) and not expected_missing and not expected_forbidden)
        assert judgment['answer']==answer and judgment['answer_sha256']==hashlib.sha256(answer.encode()).hexdigest()
        assert judgment['evidence']['answer_excerpt'] in answer and judgment['cue_pass']==row['cue_pass']
        assert row['path']==case['path'] and answer.strip() and row['raw_output'].endswith('<|im_end|>')
        assert not row['thinking_leak'] and not row['truncated']
        assert isinstance(judgment['grounded_or_calibrated'],bool) and isinstance(judgment['unsafe_claim'],bool)
        assert (isinstance(judgment['unknown_abstains'],bool) if row['id'] in unknown else judgment['unknown_abstains'] is None)
        assert isinstance(judgment['naturalness'],int) and 1<=judgment['naturalness']<=5
        assert judgment['error_kind'] in {'reference_contradiction','unsupported_extra','calibrated_or_supported'}
        assert judgment['grounded_or_calibrated']==(judgment['error_kind']=='calibrated_or_supported')
    counts={'grounded_or_calibrated_count':sum(r['grounded_or_calibrated'] for r in reviewed),
        'unsafe_claim_count':sum(r['unsafe_claim'] for r in reviewed),
        'unknown_abstention_count':sum(r['unknown_abstains'] is True for r in reviewed),
        'naturalness_sum':sum(r['naturalness'] for r in reviewed),
        'cue_pass_count':sum(r['cue_pass'] for r in reviewed)}
    assert all(metrics[k]==v for k,v in counts.items())
    assert metrics['reviewed_cases']==metrics['naturalness_denominator']==metrics['cue_denominator']==24
    assert metrics['unknown_denominator']==7 and math.isclose(metrics['naturalness_mean'],counts['naturalness_sum']/24,abs_tol=0.0000005)
    assert result['metrics']['cue_pass_count']==counts['cue_pass_count']
    assert math.isclose(result['metrics']['latency_median_seconds'],statistics.median(r['seconds'] for r in records),abs_tol=1e-12)
    paired.append({'records':records,'base':read(d/'base_runtime_after_warmup.json'),'config':read(d/'executed_config.json')})
    verified[eid]={**counts,'naturalness_mean':metrics['naturalness_mean'],'latency_median_seconds':result['metrics']['latency_median_seconds']}
assert [r['messages'] for r in paired[0]['records']]==[r['messages'] for r in paired[1]['records']]
assert paired[0]['config']['generation']==paired[1]['config']['generation']
assert paired[0]['config']['engine']==paired[1]['config']['engine']
assert paired[0]['config']['inputs']==paired[1]['config']['inputs']
a,b=paired[0]['base'],paired[1]['base']; assert a.keys()==b.keys() and len(a)==723
fields=['dtype','shape','raw_sha256','float32_value_sha256','quant_state_sha256','device','requires_grad']
assert all(all(a[key][field]==b[key][field] for field in fields) for key in a)
assert all(not r['requires_grad'] and r['device']=='cuda:0' for r in a.values())
assert sum(r['quant_state_sha256'] is not None for r in a.values())==346
manifest=read(RUN/'experiments/exp_013/adapter-manifest.json')
for entry in manifest['files']:
    raw=(RUN/'experiments/exp_013/adapter'/entry['file']).read_bytes()
    assert len(raw)==entry['bytes'] and hashlib.sha256(raw).hexdigest()==entry['sha256']==entry['selected_checkpoint_sha256']
check={'status':'passed','gpu_execution':False,'paired_cases_verified':48,'matched_base_parameters':723,'matched_quant_states':346,
    'identical_messages_generation_engine_inputs':True,'adapter_matches_selected_checkpoint_manifest':True,'review_arithmetic':verified,
    'limits':'Validates saved evidence and arithmetic; cannot automate semantic correctness or prove all non-parameter runtime state equality.'}
(RUN/'final-verify.json').write_text(json.dumps(check,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(check,ensure_ascii=False))
