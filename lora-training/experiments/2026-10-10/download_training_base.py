"""Fetch two pinned training shards to D; reuse the verified public range downloader."""
import concurrent.futures,json
from pathlib import Path
from download_models import download
RUN=Path(__file__).resolve().parent
records=[
 {'id':'qwen35-4b-training-shard1','directory':'qwen35-4b-training','format':'safetensors','repo':'unsloth/Qwen3.5-4B','revision':'3764fa359b9082ea5a1e4a5e3ac3aaf6e9671636','file':'model.safetensors-00001-of-00002.safetensors','bytes':5329398688,'sha256':'26a93f066e1916adb13453dae5a0c707c0fbc71299ed98779571a907b8e74c61','workers':16,'deadline_seconds':3600},
 {'id':'qwen35-4b-training-shard2','directory':'qwen35-4b-training','format':'safetensors','repo':'unsloth/Qwen3.5-4B','revision':'3764fa359b9082ea5a1e4a5e3ac3aaf6e9671636','file':'model.safetensors-00002-of-00002.safetensors','bytes':3990429408,'sha256':'cb544bd9bfae93dc59b0f22b292f5933573854a7f9b97835c67060d7d910e188','workers':16,'deadline_seconds':3600}
]
assert len({r['file'] for r in records})==2 and all(r['format']=='safetensors' for r in records)
manifest=RUN/'training-files.json';data=json.loads(manifest.read_text(encoding='utf-8'));files={r['file']:r for r in data['files']};current=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 for future in concurrent.futures.as_completed([pool.submit(download,r) for r in records]):
  record=future.result();current.append(record);files[record['file']]=record;data['files']=list(files.values())
  temporary=manifest.with_suffix('.tmp');temporary.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8');temporary.replace(manifest)
raise SystemExit(0 if all(r['status']=='downloaded' for r in current) else 1)
