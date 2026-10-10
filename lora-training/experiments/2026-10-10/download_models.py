"""Bounded, resumable public downloads; each checkpoint must match its Hub SHA256."""
import argparse,concurrent.futures,hashlib,json,re,threading,time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[2];RUN=Path(__file__).resolve().parent
MODELS=[
 {'id':'qwen35-4b-q4km','repo':'unsloth/Qwen3.5-4B-GGUF','revision':'e87f176479d0855a907a41277aca2f8ee7a09523','file':'Qwen3.5-4B-Q4_K_M.gguf','bytes':2740937888,'sha256':'00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4'},
 {'id':'qwen35-9b-q4km','repo':'unsloth/Qwen3.5-9B-GGUF','revision':'3885219b6810b007914f3a7950a8d1b469d598a5','file':'Qwen3.5-9B-Q4_K_M.gguf','bytes':5680522464,'sha256':'03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8'},
 {'id':'gemma4-e4b-qatq4','repo':'google/gemma-4-E4B-it-qat-q4_0-gguf','revision':'4b4a2c1d584be7264f87aac328a1bc739ce81b6c','file':'gemma-4-E4B_q4_0-it.gguf','bytes':5154941280,'sha256':'676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee'},
]
CHUNK=32*1024*1024

def sha256(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()

def download(record):
 record=record.copy();start=time.monotonic();deadline=start+record.get('deadline_seconds',1800)
 dest=ROOT/'models'/record.get('directory',record['id']);assert dest.resolve().is_relative_to((ROOT/'models').resolve());dest.mkdir(parents=True,exist_ok=True)
 target=dest/record['file'];chunks=dest/'.chunks';chunks=chunks/record['file'] if record.get('format')=='safetensors' else chunks;chunks.mkdir(parents=True,exist_ok=True)
 try:
  if not (target.exists() and target.stat().st_size==record['bytes'] and sha256(target)==record['sha256']):
   url=f"https://huggingface.co/{record['repo']}/resolve/{record['revision']}/{record['file']}"
   def get_chunk(index):
    first=index*CHUNK;last=min(first+CHUNK,record['bytes'])-1;length=last-first+1
    part=chunks/f'{index:04d}.part'
    if part.exists() and part.stat().st_size==length:return length
    for attempt in range(3):
     if time.monotonic()>deadline:raise TimeoutError('download deadline exceeded')
     try:
      with requests.get(url,headers={'Range':f'bytes={first}-{last}'},stream=True,timeout=(10,20)) as response:
       assert response.status_code==206,f'HTTP {response.status_code}'
       assert response.headers.get('Content-Range')==f"bytes {first}-{last}/{record['bytes']}",'wrong content range'
       with part.open('wb') as f:
        for block in response.iter_content(1024*1024):
         if time.monotonic()>deadline:raise TimeoutError('download deadline exceeded')
         f.write(block)
       assert part.stat().st_size==length,'incomplete chunk'
      return length
     except Exception as exc:
      if attempt==2:raise RuntimeError(f'chunk {index} failed: {type(exc).__name__}') from None
      time.sleep(attempt+1)
   count=(record['bytes']+CHUNK-1)//CHUNK;complete=0
   with concurrent.futures.ThreadPoolExecutor(max_workers=record.get('workers',8)) as pool:
    for n,future in enumerate(concurrent.futures.as_completed([pool.submit(get_chunk,i) for i in range(count)]),1):
     complete+=future.result()
     if n%8==0 or n==count:print(json.dumps({'id':record['id'],'verified_range_bytes':complete,'total_bytes':record['bytes'],'seconds':round(time.monotonic()-start,1)}),flush=True)
   temp=target.with_suffix(target.suffix+'.assembling')
   with temp.open('wb') as output:
    for i in range(count):
     with (chunks/f'{i:04d}.part').open('rb') as part:
      for block in iter(lambda:part.read(8*1024*1024),b''):output.write(block)
   assert temp.stat().st_size==record['bytes'],'wrong checkpoint size'
   assert sha256(temp)==record['sha256'],'checkpoint SHA256 mismatch'
   if record.get('format','gguf')=='gguf':
    with temp.open('rb') as f:assert f.read(4)==b'GGUF','wrong GGUF magic'
   temp.replace(target)
  record.update(status='downloaded',path=str(target),download_seconds=time.monotonic()-start)
 except Exception as exc:
  record.update(status='error',error_type=type(exc).__name__,error=str(exc).split('https://')[0],download_seconds=time.monotonic()-start)
 print(json.dumps(record,ensure_ascii=False),flush=True);return record

if __name__=='__main__':
 assert ROOT.drive.lower()=='d:' and len({m['id'] for m in MODELS})==3
 assert all(re.fullmatch('[a-f0-9]{64}',m['sha256']) for m in MODELS)
 parser=argparse.ArgumentParser();parser.add_argument('--models',nargs='+',choices=[m['id'] for m in MODELS]);args=parser.parse_args()
 selected=[m for m in MODELS if not args.models or m['id'] in args.models]
 manifest=RUN/'models.json';old=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else []
 result={m['id']:m for m in old};current=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=len(selected)) as pool:
  for future in concurrent.futures.as_completed([pool.submit(download,m) for m in selected]):
   record=future.result();current.append(record);result[record['id']]=record
   temporary=manifest.with_suffix('.tmp');temporary.write_text(json.dumps(list(result.values()),ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temporary.replace(manifest)
 raise SystemExit(0 if all(r['status']=='downloaded' for r in current) else 1)
