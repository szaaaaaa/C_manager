"""Check the final research snapshot against frozen bytes and raw reviewed outputs."""
import hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parent
read=lambda p:json.loads((R/p).read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256((R/p).read_bytes()).hexdigest()
e=read('evidence.json');s=read('review-summary.json');reviews=read('reviews/blind-review.json')['cases'];pack=read('blind-review-pack.json');key=read('review-key.json')
byid={v['blind_id']:v for v in reviews};mapping={v['review_id']:v for v in key}
assert len(reviews)==288 and len(e['case_matrix'])==72 and len(e['examples'])==15
assert e['metrics']==s['conditions']
for p,h in e['input_file_sha256'].items():assert sha(p)==h,p
for p,v in read('freeze.json')['files'].items():assert sha(p)==v['sha256'],p
for m in e['case_matrix']:
 for exp,v in m['conditions'].items():
  a=byid[v['blind_id']];assert a['case_id']==m['case_id'] and mapping[v['blind_id']]['experiment_id']==exp
  for field,value in v.items():assert a[field]==value,(m['case_id'],field)
for x in e['examples']:
 a=byid[x['blind_id']];assert x['answer_quote'] in a['answer'];assert x['answer_sha256']==a['answer_sha256'];assert reviews[int(x['review_pointer'].split('/')[-1])]==a
 p=pack[int(x['reference_pointer'].split('/')[1])];assert p['case']['facts']==x['facts'];assert p['case'].get('source_urls',[])==x['source_urls'];assert p['review_id']==x['blind_id']
 rows=[json.loads(l) for l in (R/x['raw_record_path']).read_text(encoding='utf-8-sig').splitlines() if l];assert rows[x['raw_record_line']-1]['answer']==a['answer']
for pair in e['paired_changes']:
 rows=[m for m in e['case_matrix'] if m['subset']==pair['subset']]
 for field,groups in pair['changes'].items():
  for label,ids in groups.items():
   a,b=[z=='true' for z in label.split('_to_')];got=sorted(m['case_id'] for m in rows if m['conditions'][pair['before']][field] is a and m['conditions'][pair['after']][field] is b);assert got==sorted(ids),(field,label)
for i in range(1,8):
 n=read(f'experiments/exp_{i:03}/native-session.json');assert n['experiment_actual_exit_code']==n['observer_actual_exit_code']==0
for p in ['ml-verify.json','run-verification.json','review-freeze.json','review-summary.json']:assert read(p)['status']=='passed',p
for v in s['conditions'].values():assert v['main48']['all_quality_targets_met'] is False
# These documents were read semantically by root; this check verifies local artifact targets.
docs=['analysis.md','report.md','progress.md','publication/README.md','publication/training-README.md']
links=0
for p in docs:
 text=(R/p).read_text(encoding='utf-8-sig');assert text.strip()
 for target in re.findall(r'\]\(([^)]+)\)',text):
  if '://' in target or target.startswith('#'):continue
  target=target.split('#')[0]
  if p.startswith('publication/'):
   marker='2026-10-10-round2/'
   if marker not in target:continue
   dest=R/target.split(marker,1)[1]
  else:dest=R/target
  # This audit is created only after all checks pass.
  assert dest.is_file() or dest==R/'final-verify.json',(p,target)
  assert not any(x in {'adapter','checkpoints'} for x in dest.relative_to(R).parts),(p,target)
  links+=1
old=(R/'publication/README-remote-current.md').read_text(encoding='utf-8-sig');new=(R/'publication/README.md').read_text(encoding='utf-8-sig')
assert old.split('## 当前功能')[1].split('## 实验和验证')[0]==new.split('## 当前功能')[1].split('## 实验和验证')[0]
assert old.split('## 开发')[1].strip()==new.split('## 开发')[1].strip()
result={'status':'passed','scope':'Artifact consistency and arithmetic, not independent semantic scoring or model quality acceptance','run_id':R.name,'checked_at_utc':datetime.now(timezone.utc).isoformat(),'frozen_inputs_unchanged':True,'matrix_cases':72,'reviewed_answers':288,'verified_examples':15,'paired_comparisons':8,'local_document_links_checked':links,'native_and_observer_exit_codes':[0]*14,'all_quality_targets_met':{k:v['main48']['all_quality_targets_met'] for k,v in s['conditions'].items()},'document_sha256':{p:sha(p) for p in docs},'evidence_sha256':sha('evidence.json'),'review_sha256':sha('reviews/blind-review.json'),'review_revisions_sha256':sha('reviews/blind-revisions.json'),'limitations':['same-assistant semantic ratings, no independent human review','single seed and synthetic test inputs','no GGUF export or application integration','Windows shared GPU memory/paging not measured']}
(R/'final-verify.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
