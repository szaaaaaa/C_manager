"""Device-total telemetry only; this observer never starts a model GPU workload."""
import json
from pathlib import Path
import subprocess
import sys
import time
run = Path(__file__).resolve().parent
experiment = sys.argv[1]
assert experiment in {'exp_012', 'exp_013', 'exp_014', 'exp_015'}
directory = run / 'experiments' / experiment
assert directory.resolve().is_relative_to(run.resolve())
config = json.loads((directory / 'config.json').read_text(encoding='utf-8'))
started = time.monotonic()
while time.monotonic() - started < config['deadline_seconds']:
    try:
        result = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        result = None
    if result and result['status'] != 'running':
        break
    measured = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,utilization.gpu', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=10)
    if measured.returncode == 0:
        used, utilization = [float(part.strip()) for part in measured.stdout.strip().split(',')]
        assert used >= 0 and 0 <= utilization <= 100
        record = {'unix_seconds': time.time(), 'memory_total_used_mib': used, 'utilization_gpu_percent': utilization,
            'actual_steps_last_saved': result['actual_steps'] if result else None,
            'scope': 'Sparse device-total nvidia-smi samples; not per-process allocation or exact CUDA phase peaks'}
        with (directory / 'gpu_samples.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record) + '\n')
    time.sleep(5)
print('Device telemetry observer finished.')
