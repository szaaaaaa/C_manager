"""Bounded GGUF inference on frozen files; run --self-check before model execution."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[1]
SOURCE = Path('D:/C_manager/lora-training/scripts')
ENGINE = ROOT / 'cache/tools/llama-b11539/llama-server.exe'
NVIDIA_DEVICE = 'Vulkan1'


def write_json(path, value):
    path = path.resolve()
    assert path.is_relative_to(RUN.resolve())
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_inputs(config):
    for record in config['inputs'].values():
        path = Path(record['path']).resolve()
        assert path.is_relative_to(ROOT.resolve()) and sha256(path) == record['sha256'], path
    cases = json.loads(Path(config['inputs']['eval_cases']['path']).read_text(encoding='utf-8'))
    knowledge = json.loads(Path(config['inputs']['knowledge']['path']).read_text(encoding='utf-8'))
    assert len(cases) == 24 and len({case['id'] for case in cases}) == 24
    sys.path.insert(0, str(SOURCE))
    grounding = importlib.import_module('grounding')
    evaluator = importlib.import_module('evaluate')
    # Reuse the existing functions while fixing their knowledge input to the frozen D-drive copy.
    grounding.KNOWLEDGE = knowledge
    for case in cases:
        entry = grounding.retrieve(case['path'])
        assert (entry['id'] if entry else None) == case['knowledge'], case['id']
    return cases, knowledge, grounding, evaluator


def messages_for(case, mode, knowledge, grounding):
    entries = {entry['id']: entry for entry in knowledge['entries']}
    facts = None
    if case.get('missing_evidence'):
        facts = knowledge['unknown']
    elif case.get('distractor'):
        facts = entries[case['knowledge']]['facts'] + '\n另一个路径的资料（可能不相关）：\n' + entries[case['distractor']]['facts']
    sample = grounding.build_sample(case['path'], case['is_dir'], use_rag=mode == 'rag', facts=facts)
    return [{'role': 'system', 'content': sample['instruction']}, {'role': 'user', 'content': sample['input']}]


def server_command(config, port):
    engine = config['engine']
    return [str(ENGINE), '--model', config['model']['path'], '--host', '127.0.0.1', '--port', str(port),
            '--device', NVIDIA_DEVICE, '--split-mode', 'none', '--gpu-layers', str(engine['gpu_layers_requested']),
            '--ctx-size', str(engine['context_tokens']), '--batch-size', str(engine['batch_tokens']),
            '--ubatch-size', str(engine['ubatch_tokens']), '--parallel', '1', '--threads', str(engine['threads']),
            '--jinja', '--reasoning', 'off', '--chat-template-kwargs', '{"enable_thinking":false}',
            '--no-cache-prompt', '--fit', 'off', '--offline', '--no-webui', '--no-agent', '--no-mmproj',
            '--timeout', '60', '--seed', str(config['seed']), '--log-colors', 'off', '--log-verbosity', '4']


def json_http(url, body=None, timeout=60):
    payload = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
    request = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def chat_request(messages, tokens):
    return {'messages': messages, 'stream': False, 'temperature': 0, 'seed': 42,
            'max_tokens': tokens, 'cache_prompt': False, 'chat_template_kwargs': {'enable_thinking': False}}


def parse_response(case, response, seconds, messages, evaluator):
    assert response.get('choices'), 'Server returned no choices'
    choice = response['choices'][0]
    message = choice['message']
    answer = message.get('content')
    assert isinstance(answer, str), 'Server returned non-text content'
    usage = response.get('usage', {})
    reasoning = message.get('reasoning_content') or ''
    thinking_leak = bool(reasoning.strip()) or any(tag in answer for tag in ['<think>', '<|channel>thought', '[THINK]'])
    return {'id': case['id'], 'path': case['path'], 'answer': answer.strip(), 'messages': messages,
            'seconds': round(seconds, 4), 'input_tokens': usage.get('prompt_tokens'),
            'output_tokens': usage.get('completion_tokens'), 'finish_reason': choice.get('finish_reason'),
            'truncated': choice.get('finish_reason') == 'length', 'thinking_leak': thinking_leak,
            'raw_response': response, **evaluator.check_response(case, answer.strip())}


def metrics_for(records):
    return {'completed_cases': len(records), 'cue_pass_count': sum(record['cue_pass'] for record in records),
            'cue_pass_denominator': 24, 'empty_answer_count': sum(not record['answer'] for record in records),
            'truncated_answer_count': sum(record['truncated'] for record in records),
            'thinking_leak_count': sum(record['thinking_leak'] for record in records),
            'latency_median_seconds': statistics.median(record['seconds'] for record in records) if records else None,
            'fact_grounded_or_calibrated_count_review': None, 'unsafe_claim_count_review': None,
            'naturalness_mean_review': None, 'unknown_abstention_count_review': None}


def self_check():
    config = json.loads((RUN / 'experiments/exp_002/config.json').read_text(encoding='utf-8'))
    cases, knowledge, grounding, evaluator = load_inputs(config)
    probe = {'required': [['无法', '不确定'], ['备份']], 'forbidden': ['放心删']}
    assert evaluator.check_response(probe, '无法确定用途，先备份。')['cue_pass']
    assert not evaluator.check_response(probe, '无法确定用途，备份后放心删。')['cue_pass']
    for case in cases:
        plain = messages_for(case, 'plain', knowledge, grounding)
        rag = messages_for(case, 'rag', knowledge, grounding)
        assert plain[0] == rag[0]
        assert '用途资料：' not in plain[1]['content'] and '用途资料：' in rag[1]['content']
        assert rag[1]['content'].startswith(plain[1]['content'])
        for entry in knowledge['entries']:
            assert entry['answer'] not in rag[1]['content'], 'Gold answer leaked into input'
        if case.get('missing_evidence') or case['knowledge'] is None:
            assert rag[1]['content'].endswith(knowledge['unknown'])
    command = server_command(config, 18081)
    assert command[command.index('--device') + 1] == 'Vulkan1'
    assert command[command.index('--fit') + 1] == 'off'
    assert command[command.index('--reasoning') + 1] == 'off'
    assert command[command.index('--log-verbosity') + 1] == '4'
    response = {'choices': [{'message': {'content': '无法确定用途，先备份。😀'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 25, 'completion_tokens': 12}}
    record = parse_response({'id': 'probe', 'path': 'D:/test', **probe}, response, 0.5, [], evaluator)
    assert record['cue_pass'] and '😀' in record['answer'] and not record['truncated']
    response['choices'][0]['finish_reason'] = 'length'
    response['choices'][0]['message']['reasoning_content'] = 'reasoning unexpectedly enabled'
    failure = parse_response({'id': 'probe', 'path': 'D:/test', **probe}, response, 0.6, [], evaluator)
    assert failure['thinking_leak'] and failure['truncated']
    summary = metrics_for([record, failure])
    assert summary['completed_cases'] == 2 and summary['truncated_answer_count'] == 1
    assert summary['latency_median_seconds'] == 0.55
    write_json(RUN / 'self_check.json', {'status': 'passed', 'frozen_cases': 24, 'input_answer_leak': False,
               'device': 'Vulkan1', 'thinking_off': True, 'model_or_gpu_execution': False})
    print('Self-check passed: frozen hashes, 24 prompts, no gold-answer leakage, parsing, metrics, explicit Vulkan1.')


def run(experiment):
    directory = (RUN / 'experiments' / experiment).resolve()
    assert directory.is_relative_to((RUN / 'experiments').resolve()) and directory.name == experiment
    assert experiment in {'exp_%03d' % number for number in range(1, 7)}
    assert not (directory / 'result.json').exists(), 'Refusing to overwrite an existing run; use a new experiment ID'
    config = json.loads((directory / 'config.json').read_text(encoding='utf-8'))
    started = time.perf_counter()
    deadline = started + config['deadline_seconds']
    records = []
    process = None
    lock_fd = None
    server_log = None
    timer = None
    stop_samples = threading.Event()
    samples = []
    lock_path = RUN / 'inference.gpu.lock'
    result = {'experiment_id': experiment, 'status': 'running', 'exit_code': None, 'records': records,
              'metrics': metrics_for(records), 'review_status': 'pending', 'terminated_by_driver': False, 'configuration_path': str(directory / 'executed_config.json')}
    write_json(directory / 'result.json', result)
    try:
        cases, knowledge, grounding, evaluator = load_inputs(config)
        manifest = json.loads((RUN / 'models.json').read_text(encoding='utf-8'))
        model = next(record for record in manifest if record['id'] == config['model']['id'])
        assert model['status'] == 'downloaded' and model['revision'] == config['model']['revision']
        model_path = Path(config['model']['path']).resolve()
        assert model_path.is_relative_to((ROOT / 'models').resolve()) and model_path.stat().st_size == config['model']['bytes']
        assert sha256(model_path) == model['sha256'], 'Model SHA256 mismatch'
        assert ENGINE.is_file()
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_fd, str(os.getpid()).encode('ascii'))
        with socket.socket() as bound:
            bound.bind(('127.0.0.1', 0)); port = bound.getsockname()[1]
        command = server_command(config, port)
        executed = {**config, 'actual_command': command, 'actual_device': NVIDIA_DEVICE,
                    'model_sha256': model['sha256'], 'runtime_sha256': sha256(ENGINE), 'source_scripts': str(SOURCE),
                    'adaptations': ['Explicit Vulkan1 selects NVIDIA rather than default Intel Vulkan0',
                                    'fit off prevents implicit context/offload changes', 'reasoning off plus enable_thinking false',
                                    'Model GGUF metadata chat template; no external template override',
                                    'log-verbosity 4 records actual GPU offload layers and buffers'],
                    'runtime_version': subprocess.check_output([str(ENGINE), '--version'], text=True, stderr=subprocess.STDOUT, timeout=10)}
        write_json(directory / 'executed_config.json', executed)
        server_log = (directory / 'server.log').open('w', encoding='utf-8', newline='\n')
        process = subprocess.Popen(command, cwd=ROOT, stdout=server_log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        def hard_stop():
            if process.poll() is None:
                result['terminated_by_driver'] = True
                result['server_termination_reason'] = 'hard wall-clock deadline'
                process.kill()
        timer = threading.Timer(max(0.1, deadline - time.perf_counter()), hard_stop)
        timer.daemon = True; timer.start()
        def sample_gpu():
            while not stop_samples.is_set():
                try:
                    raw = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
                                                  text=True, timeout=3, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    samples.append({'elapsed_seconds': round(time.perf_counter() - started, 3),
                                    'gpu_used_mib': int(raw.splitlines()[0].strip())})
                except Exception:
                    pass
                stop_samples.wait(1)
        monitor = threading.Thread(target=sample_gpu, daemon=True); monitor.start()
        url = 'http://127.0.0.1:%d' % port
        load_started = time.perf_counter()
        while True:
            if process.poll() is not None:
                raise RuntimeError('llama-server exited during model loading: %s' % process.returncode)
            if time.perf_counter() >= min(deadline, load_started + config['timeouts']['load_seconds']):
                raise TimeoutError('Model initialization timed out')
            try:
                health = json_http(url + '/health', timeout=2)
                if health.get('status') == 'ok': break
            except (urllib.error.URLError, TimeoutError):
                pass
            time.sleep(0.5)
        result['model_load_seconds'] = round(time.perf_counter() - load_started, 4)
        executed['server_props'] = json_http(url + '/props', timeout=5)
        write_json(directory / 'executed_config.json', executed)
        warm_start = time.perf_counter()
        result['warmup_response'] = json_http(url + '/v1/chat/completions',
            chat_request([{'role': 'user', 'content': config['warmup']['question']}], config['warmup']['max_new_tokens']), timeout=60)
        result['warmup_seconds'] = round(time.perf_counter() - warm_start, 4)
        with (directory / 'records.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
            for case in cases:
                remaining = deadline - time.perf_counter()
                if remaining <= 0: raise TimeoutError('Experiment wall-clock budget exhausted')
                messages = messages_for(case, config['mode'], knowledge, grounding)
                start = time.perf_counter()
                response = json_http(url + '/v1/chat/completions', chat_request(messages, 256),
                                     timeout=min(config['timeouts']['request_seconds'], remaining))
                record = parse_response(case, response, time.perf_counter() - start, messages, evaluator)
                records.append(record)
                stream.write(json.dumps(record, ensure_ascii=False) + '\n'); stream.flush()
                result['metrics'] = metrics_for(records)
                write_json(directory / 'result.json', result)
                print(json.dumps({key: record[key] for key in ['id', 'answer', 'seconds', 'cue_pass', 'finish_reason']}, ensure_ascii=False), flush=True)
                if record['thinking_leak']: raise RuntimeError('Unexpected reasoning content despite thinking disabled')
        result['status'] = 'success'; result['exit_code'] = 0
    except Exception as exc:
        result['status'] = 'timed_out' if isinstance(exc, TimeoutError) or time.perf_counter() >= deadline else 'failed'
        result['exit_code'] = 1
        result['error_type'] = type(exc).__name__; result['error'] = str(exc)
        (directory / 'error.log').write_text(traceback.format_exc(), encoding='utf-8', newline='\n')
        (directory / 'lessons.md').write_text('# Execution failure\n\nStatus: ' + result['status'] + '\n\n' + str(exc) + '\n\nOriginal spec/config kept unchanged; incomplete results are not successful experiments.\n', encoding='utf-8', newline='\n')
    finally:
        stop_samples.set()
        if timer: timer.cancel()
        if process is not None:
            if process.poll() is None:
                result['terminated_by_driver'] = True
                result['server_termination_reason'] = 'controlled cleanup after ' + result['status']
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            result['server_exit_code'] = process.returncode
        if server_log: server_log.close()
        if lock_fd is not None:
            os.close(lock_fd)
            assert lock_path.resolve().is_relative_to(RUN.resolve()); lock_path.unlink()
        result['metrics'] = metrics_for(records)
        result['metrics']['peak_gpu_used_mib'] = max((sample['gpu_used_mib'] for sample in samples), default=None)
        result['gpu_measurement_note'] = 'nvidia-smi total device usage sampled at 1Hz, includes desktop/background use; not process-only allocation'
        result['gpu_samples'] = samples
        result['elapsed_seconds'] = round(time.perf_counter() - started, 4)
        result['automatic_targets_met'] = (len(records) == 24 and result['metrics']['cue_pass_count'] >= 21
            and result['metrics']['empty_answer_count'] == 0 and result['metrics']['truncated_answer_count'] == 0
            and result['metrics']['thinking_leak_count'] == 0 and result['metrics']['latency_median_seconds'] <= 10)
        write_json(directory / 'result.json', result)
        print(json.dumps({'experiment_id': experiment, 'status': result['status'], 'metrics': result['metrics'], 'elapsed_seconds': result['elapsed_seconds']}, ensure_ascii=False), flush=True)
    return result['exit_code']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--experiment', choices=['exp_%03d' % n for n in range(1, 7)])
    args = parser.parse_args()
    if args.self_check:
        self_check()
    else:
        parser.error('--experiment is required') if not args.experiment else None
        raise SystemExit(run(args.experiment))
