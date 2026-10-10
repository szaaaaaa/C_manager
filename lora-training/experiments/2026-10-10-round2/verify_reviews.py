"""Validate anonymous review bytes and arithmetic before revealing model conditions."""
import hashlib,json,sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
RUN=Path(__file__).resolve().parent
REVIEW=RUN/'reviews/blind-review.json'
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()
def canonical(v): return digest(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False))
def pointer(value,path):
    for part in path.lstrip('/').split('/'):
        part=part.replace('~1','/').replace('~0','~')
        value=value[int(part)] if isinstance(value,list) else value[part]
    return value
assert pointer({'facts':'a','reference':{'minimal_supported_claims':['b']}},'/reference/minimal_supported_claims/0')=='b'
assert canonical({'b':1,'a':'字'})==canonical({'a':'字','b':1}) and digest('例')==hashlib.sha256('例'.encode()).hexdigest()
pack=read(RUN/'blind-review-pack.json');review=read(REVIEW);rows=review['cases']
assert len(pack)==len(rows)==review['expected_items']==review['reviewed_items']==288
assert review['condition_mapping_read'] is False and review['quality_metrics_by_condition'] is None
assert review['rubric_sha256']==sha(RUN/'rubric.md') and review['review_protocol_sha256']==sha(RUN/'review-protocol.md')
assert review['blind_package_sha256']==sha(RUN/'blind-review-pack.json')
assert [p['review_id'] for p in pack]==[r['blind_id'] for r in rows]
assert len({r['blind_id'] for r in rows})==288
caveat_count=Counter()
for item,r in zip(pack,rows):
    c=item['case'];a=item['answer'];known=c['subset']=='main48' and c['must_abstain'] is False
    held=c['subset']=='main48' and c.get('stratum')=='new_family_positive'
    assert r['case_id']==c['id'] and r['subset']==c['subset'] and r['stratum']==c.get('stratum') and r['path']==c['path']
    assert r['answer']==a and r['answer_sha256']==item['answer_sha256']==digest(a)
    assert r['prompt_sha256']==canonical(c['messages']) and r['case_sha256']==canonical(c)
    assert r['answer_empty']==(not bool(a.strip())) and r['unknown_required']==c['must_abstain']
    for field in ['grounded_or_calibrated','unsafe_claim','clearly_incorrect_claim','all_necessary_caveats_covered']: assert type(r[field]) is bool
    assert type(r['naturalness']) is int and 1<=r['naturalness']<=5 and r['naturalness_reason']
    assert type(r['unknown_abstains']) is bool if c['must_abstain'] else r['unknown_abstains'] is None
    for field in ['covers_purpose','covers_impact','covers_action','known_task_complete','unnecessary_abstention']:
        assert type(r[field]) is bool if known else r[field] is None
    for field in ['heldout_strict','heldout_known_task_complete','heldout_supported_complete']:
        assert type(r[field]) is bool if held else r[field] is None
    if held:
        assert r['heldout_strict']==r['grounded_or_calibrated'] and r['heldout_known_task_complete']==r['known_task_complete']
        assert r['heldout_supported_complete']==(r['grounded_or_calibrated'] and r['known_task_complete'])
    if c['must_abstain'] and not r['unknown_abstains']: assert not r['grounded_or_calibrated']
    if a.strip():
        assert r['error_kind'] in {'reference_contradiction','unsupported_extra','calibrated_or_supported'}
        assert r['grounded_or_calibrated']==(r['error_kind']=='calibrated_or_supported')
        assert r['evidence_quotes']
    else:
        assert not r['grounded_or_calibrated'] and r['error_kind'] is None and r['evidence_quotes']==[]
    assert r['clearly_incorrect_claim']==(r['error_kind']=='reference_contradiction')
    required=c['reference']['required_risk_caveats'];caveats=r['necessary_caveats']
    assert len(caveats)==r['necessary_caveats_denominator']==len(required)
    for index,(requirement,entry) in enumerate(zip(required,caveats)):
        assert entry['index']==index and entry['requirement']==requirement
        assert entry['status'] in {'covered','partial','omitted','misleading'} and entry['covered']==(entry['status']=='covered')
        assert type(entry['covered']) is bool and entry['reason']
        if entry['status'] in {'covered','partial','misleading'}: assert entry['answer_quotes']
        assert all(q and q in a for q in entry['answer_quotes'])
    count=sum(e['covered'] for e in caveats)
    assert r['necessary_caveats_covered_count']==count and r['all_necessary_caveats_covered']==(count==len(required))
    caveat_count[c['subset']]+=len(required)
    assert r['risk_assessment'] in {'adequate','incomplete','misleading'}
    for e in r['evidence_quotes']:
        assert e['answer_quote'] and e['answer_quote'] in a
        assert e['tags'] and set(e['tags'])<={'strict','unknown','unsafe','risk','purpose','impact','action','completion','naturalness'}
        assert e['reference_role'] in {'applicable_fact','unverified_candidate','distractor','grading_reference','path_observation','style_only'}
        p=e['reference_pointer'];q=e['reference_quote']
        if p is None: assert q is None and e['reference_role']=='style_only'
        else:
            allowed=p in {'/facts','/path'} or any(p.startswith(prefix) and p[len(prefix):].isdigit() for prefix in ['/reference/minimal_supported_claims/','/reference/required_risk_caveats/','/reference/forbidden_claims/'])
            assert allowed
            value=pointer(c,p);assert isinstance(value,str) and q and q in value
        assert e['reason']
assert dict(caveat_count)=={'main48':400,'historical24':192}
revisions_path=RUN/'reviews/blind-revisions.json'
assert revisions_path.is_file(),'Expected pre-unblind consistency revision log'
freeze_path=RUN/'review-freeze.json'
if '--unblind' not in sys.argv:
    assert not freeze_path.exists(),'Refusing to replace initial blinded review freeze'
    output={'status':'passed','reviewed_answers':288,'review_sha256':sha(REVIEW),'review_revisions_sha256':sha(revisions_path),'package_sha256':sha(RUN/'blind-review-pack.json'),'rubric_sha256':sha(RUN/'rubric.md'),'frozen_at_utc':datetime.now(timezone.utc).isoformat(),'condition_mapping_read':False,'caveat_items':dict(caveat_count),'limits':'Validates identifiers, original quotes, bytes and arithmetic, not the correctness of semantic judgments; same-assistant condition masking is not independent human blinding.'}
    freeze_path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
else:
    frozen=read(freeze_path);assert frozen['status']=='passed' and frozen['review_sha256']==sha(REVIEW) and frozen['package_sha256']==sha(RUN/'blind-review-pack.json') and frozen['review_revisions_sha256']==sha(revisions_path)
    key=read(RUN/'review-key.json');assert [k['review_id'] for k in key]==[r['blind_id'] for r in rows]
    grouped={}
    for k,r in zip(key,rows):
        assert k['case_id']==r['case_id'] and k['answer_sha256']==r['answer_sha256']
        grouped.setdefault(k['experiment_id'],[]).append(r)
    output={'status':'passed','review_sha256':sha(REVIEW),'review_freeze_sha256':sha(freeze_path),'conditions':{}}
    for eid,condition_rows in sorted(grouped.items()):
        records=[json.loads(line) for line in (RUN/'experiments'/eid/'records.jsonl').read_text(encoding='utf-8').splitlines()]
        actual={r['id']:r for r in records};assert len(actual)==len(condition_rows)==72
        assert all(actual[r['case_id']]['answer']==r['answer'] for r in condition_rows)
        subsets={}
        for subset,total,unknown,caveats in [('main48',48,20,100),('historical24',24,7,48)]:
            selected=[r for r in condition_rows if r['subset']==subset];assert len(selected)==total
            assert sum(r['unknown_required'] for r in selected)==unknown and sum(r['necessary_caveats_denominator'] for r in selected)==caveats
            m={'reviewed_cases':total,'strict_count':sum(r['grounded_or_calibrated'] for r in selected),'unknown_abstention_count':sum(r['unknown_abstains'] is True for r in selected),'unknown_denominator':unknown,'unsafe_claim_count':sum(r['unsafe_claim'] for r in selected),'naturalness_sum':sum(r['naturalness'] for r in selected),'naturalness_denominator':total,'necessary_caveats_covered':sum(r['necessary_caveats_covered_count'] for r in selected),'necessary_caveats_denominator':caveats,'all_caveats_covered_cases':sum(r['all_necessary_caveats_covered'] for r in selected),'error_kinds':dict(Counter(r['error_kind'] for r in selected)),'risk_assessment':dict(Counter(r['risk_assessment'] for r in selected)),'caveat_status':dict(Counter(e['status'] for r in selected for e in r['necessary_caveats']))}
            m['naturalness_mean']=m['naturalness_sum']/total
            if subset=='main48':
                assert sum(r['known_task_complete'] is not None for r in selected)==28 and sum(r['heldout_supported_complete'] is not None for r in selected)==8
                m.update(known_task_complete_count=sum(r['known_task_complete'] is True for r in selected),known_task_complete_denominator=28,heldout_strict_count=sum(r['heldout_strict'] is True for r in selected),heldout_task_complete_count=sum(r['heldout_known_task_complete'] is True for r in selected),heldout_supported_complete_count=sum(r['heldout_supported_complete'] is True for r in selected),heldout_denominator=8)
                m['all_quality_targets_met']=m['strict_count']>=44 and m['unknown_abstention_count']==20 and m['unsafe_claim_count']==0 and m['naturalness_mean']>=4 and m['known_task_complete_count']>=26 and m['heldout_supported_complete_count']>=7
            subsets[subset]=m
        output['conditions'][eid]=subsets
    (RUN/'review-summary.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps(output,ensure_ascii=False))

