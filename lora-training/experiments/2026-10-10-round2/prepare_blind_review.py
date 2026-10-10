"""Prepare a condition-hidden review package from terminal, matched inference runs."""
import hashlib,json,random
from pathlib import Path
RUN=Path(__file__).resolve().parent

def digest(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()
def permutation(count):
    result=list(range(count));random.Random(1042).shuffle(result)
    assert sorted(result)==list(range(count))
    return result
assert permutation(9)==permutation(9) and permutation(9)!=list(range(9))
assert digest('例')==hashlib.sha256('例'.encode()).hexdigest()
cases=json.loads((RUN/'data/eval_cases.json').read_text(encoding='utf-8-sig'))
assert len(cases)==72 and len({c['id'] for c in cases})==72
rows=[]; all_messages=[]
for number,arm in [(4,'previous_adapter'),(5,'A'),(6,'B'),(7,'C')]:
    name=f'exp_{number:03d}';directory=RUN/'experiments'/name
    result=json.loads((directory/'result.json').read_text(encoding='utf-8'))
    records=[json.loads(line) for line in (directory/'records.jsonl').read_text(encoding='utf-8').splitlines()]
    assert result['status']=='success' and result['exit_code']==0
    assert result['records']==records and [r['id'] for r in records]==[c['id'] for c in cases]
    messages=[r['messages'] for r in records];all_messages.append(messages)
    for case,record in zip(cases,records):
        assert record['path']==case['path'] and record['answer']
        assert record['raw_output'].endswith('<|im_end|>')
        assert not record['thinking_leak'] and not record['truncated']
        assert record['messages']==[{'role':'system','content':case['instruction']},{'role':'user','content':case['input']}]
        rows.append((name,arm,case,record['answer']))
assert all(m==all_messages[0] for m in all_messages)
pack=[];key=[]
for index,source_index in enumerate(permutation(len(rows)),1):
    name,arm,case,answer=rows[source_index];review_id=f'r{index:04d}'
    pack.append({'review_id':review_id,'case':case,'answer':answer,'answer_sha256':digest(answer)})
    key.append({'review_id':review_id,'experiment_id':name,'arm':arm,'case_id':case['id'],'answer_sha256':digest(answer)})
assert len(pack)==len(key)==288 and len({k['review_id'] for k in key})==288
for filename,content in [('blind-review-pack.json',pack),('review-key.json',key)]:
    path=RUN/filename;assert not path.exists(),'Refusing to replace a frozen review package'
    path.write_text(json.dumps(content,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'status':'passed','answers':len(pack),'matched_cases':72,'shuffle_seed':1042,'pack_sha256':hashlib.sha256((RUN/'blind-review-pack.json').read_bytes()).hexdigest()}))
