import json,hashlib,pathlib
RUN=pathlib.Path('outputs/exp_20261010_150741')
PACK=RUN/'blind-review-pack.json'
rows=json.loads(PACK.read_text(encoding='utf-8'))
def sha(v):return hashlib.sha256(v).hexdigest()
def canon(v):return sha(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8'))
def build(n):
 x=rows[n['i']-1];c=x['case'];a=x['answer'];known=c['subset']=='main48' and not c['must_abstain'];held=known and c.get('stratum')=='new_family_positive'
 assert n['q'] and n['q'] in a and n['style'] in a
 assert len(n['c'])==len(c['reference']['required_risk_caveats'])
 cv=[]
 for i,(st,quotes,yes,no) in enumerate(n['c']):
  assert st in ['c','p','o','m'] and all(z and z in a for z in quotes)
  status={'c':'covered','p':'partial','o':'omitted','m':'misleading'}[st]
  cv.append({'index':i,'requirement':c['reference']['required_risk_caveats'][i],'status':status,'covered':st=='c','answer_quotes':quotes,'covered_elements':[yes] if yes else [],'missing_elements':[no] if no else [],'reason':('已表达：'+yes+'。' if yes else '')+('未覆盖或错误：'+no+'。' if no else '')})
 kind={'s':'calibrated_or_supported','u':'unsupported_extra','c':'reference_contradiction'}[n['kind']]
 assert n['ab'] is None if not c['must_abstain'] else isinstance(n['ab'],bool)
 assert n['complete'] is None if not known else isinstance(n['complete'],bool)
 assert n['coverage'] is None if not known else len(n['coverage'])==3
 if c['must_abstain'] and not n['ab']: assert n['kind']!='s'
 cov=[z=='1' for z in n['coverage']] if known else [None]*3
 eq=[{'tags':['strict','risk']+(['unknown'] if c['must_abstain'] else ['completion'] if known else []),'answer_quote':n['q'],'reference_pointer':'/facts','reference_quote':c['facts'],'reference_role':n.get('refrole','applicable_fact'),'reason':n['reason']},{'tags':['naturalness'],'answer_quote':n['style'],'reference_pointer':None,'reference_quote':None,'reference_role':'style_only','reason':n['style_reason']}]
 return {'blind_id':x['review_id'],'case_id':c['id'],'subset':c['subset'],'stratum':c.get('stratum'),'path':c['path'],'prompt_sha256':canon(c['messages']),'case_sha256':canon(c),'answer':a,'answer_sha256':sha(a.encode('utf-8')),'answer_empty':not bool(a.strip()),'unknown_required':c['must_abstain'],'grounded_or_calibrated':n['kind']=='s','unknown_abstains':n['ab'],'unsafe_claim':n['unsafe'],'risk_assessment':{'a':'adequate','i':'incomplete','m':'misleading'}[n['risk']],'covers_purpose':cov[0],'covers_impact':cov[1],'covers_action':cov[2],'known_task_complete':n['complete'],'unnecessary_abstention':n.get('unnecessary',False) if known else None,'heldout_strict':n['kind']=='s' if held else None,'heldout_known_task_complete':n['complete'] if held else None,'heldout_supported_complete':n['kind']=='s' and n['complete'] if held else None,'necessary_caveats':cv,'necessary_caveats_covered_count':sum(z['covered'] for z in cv),'necessary_caveats_denominator':len(cv),'all_necessary_caveats_covered':all(z['covered'] for z in cv),'naturalness':n['nat'],'naturalness_reason':n['style_reason'],'error_kind':kind,'clearly_incorrect_claim':n['kind']=='c','strict_reason':n['reason'],'unknown_reason':n['reason'] if c['must_abstain'] else None,'unsafe_reason':n['reason'],'risk_reason':n['reason'],'completion_reason':n['reason'] if known else None,'evidence_quotes':eq}
def save(notes):
 f=RUN/'reviews/manual-notes.json';prior=json.loads(f.read_text(encoding='utf-8')) if f.exists() else []
 assert not set(z['i'] for z in prior)&set(z['i'] for z in notes)
 allnotes=sorted(prior+notes,key=lambda z:z['i']);out=[build(z) for z in allnotes]
 for z in out: assert z['answer_sha256']==next(x['answer_sha256'] for x in rows if x['review_id']==z['blind_id'])
 meta={'schema_version':'round2-blind-review-v1','run_id':'exp_20261010_150741','reviewer':'Codex same assistant; condition masked; study design and prior answers known','review_method':'Single assistant condition-masked semantic review; not independent human blinded evaluation','rubric_sha256':sha((RUN/'rubric.md').read_bytes()),'review_protocol_sha256':sha((RUN/'review-protocol.md').read_bytes()),'blind_package_sha256':sha(PACK.read_bytes()),'prompt_sha256_method':"sha256(utf8(json.dumps(case.messages,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)))",'expected_items':288,'reviewed_items':len(out),'condition_mapping_read':False,'quality_metrics_by_condition':None,'cases':out}
 f.write_text(json.dumps(allnotes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(RUN/'reviews/blind-review.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('SAVED',len(out),'of288; no condition summaries')
