"""CPU-only artifact verification after all seven terminal runs; no scoring/tuning."""
from pathlib import Path
import json, hashlib, math, statistics
RUN = Path(__file__).resolve().parent
FIELDS = ['dtype','shape','raw_sha256','float32_value_sha256','quant_state_sha256']
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()
def same_base(a,b):
    assert set(a) == set(b)
    assert all(not p['requires_grad'] for p in a.values())
    assert all(not p['requires_grad'] for p in b.values())
    return {field:[name for name in a if a[name][field] != b[name][field]] for field in FIELDS}
freeze = read(RUN/'freeze.json'); freeze_sha = sha(RUN/'freeze.json')
assert freeze['status'] == 'approved'
assert freeze_sha == '67929c63b5cc884e4a466d5e58bfe18bc6ce1344ea3b58f8f107a5588a23d872'
for name, meta in freeze['files'].items():
    p = RUN/name
    assert p.stat().st_size == meta['bytes'] and sha(p) == meta['sha256'], name
for name, meta in freeze['data_files'].items():
    p = Path(meta['path'])
    assert p.stat().st_size == meta['bytes'] and sha(p) == meta['sha256'], name
cases = read(RUN/'data/eval_cases.json')
assert len(cases) == 72 and len({c['id'] for c in cases}) == 72
reference = read(RUN/'experiments/exp_004/base_runtime_after_warmup.json')
training_reference = read(RUN/'experiments/exp_001/base_after_step0_before_training.json')
out = {'run_id':RUN.name,'status':'passed','freeze_sha256':freeze_sha,'frozen_files_unchanged':True,'experiments':{},'semantic_review':'Not performed by this execution verification. Primary48 requires the frozen blinded review protocol.','lora_initial_hashes_saved':False}
for number in range(1,8):
    exp = f'exp_{number:03d}'; directory = RUN/'experiments'/exp
    result = read(directory/'result.json'); config = read(directory/'config.json'); executed = read(directory/'executed_config.json'); native = read(directory/'native-session.json')
    assert result['status'] == 'success' and result['exit_code'] == 0
    assert native['experiment_actual_exit_code'] == native['observer_actual_exit_code'] == 0
    assert config['data_freeze_approved'] and config['freeze_sha256'] == freeze_sha
    assert result['elapsed_seconds'] < config['deadline_seconds'] == 1740
    assert result['eos_configuration']['actual_eos_token_id'] == 248046
    assert executed['model']['downloaded_files_manifest_sha256'] == sha(RUN/'training-files.json')
    metrics = result['metrics']; assert metrics['out_of_memory'] is False
    assert metrics['actual_nf4_double_quant_bf16_linear_modules'] == 346
    record = {'status':result['status'],'actual_exit':native['experiment_actual_exit_code'],'session':native['experiment_session_id'],'observer_session':native['observer_session_id'],'observer_exit':native['observer_actual_exit_code'],'elapsed_seconds':result['elapsed_seconds'],'device_total_sparse_peak_mib':native['device_total_sparse_peak_mib'],'loading_peak_allocated_gpu_mib':metrics['loading_peak_allocated_gpu_mib'],'loading_peak_reserved_gpu_mib':metrics['loading_peak_reserved_gpu_mib'],'observed_environment_warnings':result['observed_environment_warnings']}
    if number <= 3:
        assert result['actual_steps'] == metrics['completed_optimizer_steps'] == 40
        assert metrics['finite_loss_and_gradients'] and metrics['prompt_mask_valid']
        assert metrics['train_records'] == 160 and metrics['validation_records'] == 32
        assert metrics['maximum_tokenized_length'] <= 768
        assert len(metrics['gradient_observations']) == 40
        assert all(math.isfinite(g['post_clip_grad_norm']) and g['post_clip_grad_norm'] > 0 for g in metrics['gradient_observations'])
        before = read(directory/'base_after_step0_before_training.json'); after = read(directory/'base_after_training_before_final_eval.json')
        differences = same_base(before,after); cross = same_base(training_reference,before)
        assert len(before) == metrics['base_parameter_hashes_checked'] == 723 and not any(differences.values()) and not any(cross.values())
        assert metrics['changed_base_parameter_count'] == 0 and metrics['changed_lora_parameter_count'] == 64
        losses = {row['step']:row['eval_loss'] for row in result['training_logs'] if 'eval_loss' in row}
        assert set(losses) == {0,20,40} and all(math.isfinite(v) for v in losses.values())
        manifest = read(directory/'adapter-manifest.json')
        selected = manifest['selected_checkpoint_step']; assert selected in (20,40)
        assert losses[selected] == min(losses[20],losses[40]) == manifest['selected_checkpoint_validation_nll']
        for file in manifest['files']:
            p = directory/'adapter'/file['file']; selected_p = Path(manifest['selected_checkpoint'])/file['file']
            assert p.stat().st_size == file['bytes'] and sha(p) == file['sha256'] == sha(selected_p)
        assert manifest['adapter_storage_dtypes'] == ['BF16']
        record.update(steps=40,base_parameter_count=723,changed_base=0,changed_lora=64,cross_arm_base_mismatch_count=sum(len(v) for v in cross.values()),validation_nll_by_step=losses,selected_checkpoint_step=selected,training_peak_allocated_gpu_mib=metrics['training_peak_allocated_gpu_mib'],training_peak_reserved_gpu_mib=metrics['training_peak_reserved_gpu_mib'],adapter_manifest_sha256=sha(directory/'adapter-manifest.json'))
    else:
        runtime = read(directory/'base_runtime_after_warmup.json'); differences = same_base(reference,runtime)
        assert len(runtime) == 723 and not any(differences.values())
        if number != 4:
            comparison = read(directory/'runtime_base_comparison.json')
            assert comparison['status'] == 'passed' and not any(comparison['mismatches'].values())
        rows = [json.loads(line) for line in (directory/'records.jsonl').read_text(encoding='utf-8').splitlines()]
        assert rows == result['records'] and len(rows) == metrics['completed_cases'] == 72
        assert [row['id'] for row in rows] == [case['id'] for case in cases]
        assert [row['messages'] for row in rows] == [case['messages'] for case in cases]
        assert all(row['answer'].strip() and not row['thinking_leak'] and not row['truncated'] for row in rows)
        assert all(row['raw_output'].endswith('<|im_end|>') for row in rows)
        assert all(0 < row['output_tokens'] <= 256 and row['input_tokens'] + 256 <= 2048 for row in rows)
        assert all(not any(marker in row['raw_output'].lower() for marker in ['<think>','</think>','<|thought|>','<|thinking|>']) for row in rows)
        primary = [row for row in rows if row['subset'] == 'main48']; diagnostic = [row for row in rows if row['subset'] == 'historical24']
        assert len(primary) == 48 and len(diagnostic) == 24
        assert all(row['cue_checked'] is False and row['cue_pass'] is None for row in primary)
        assert all(row['cue_checked'] is True for row in diagnostic)
        assert metrics['empty_answer_count'] == metrics['thinking_leak_count'] == metrics['truncated_answer_count'] == 0
        assert result['adapter_runtime_dtypes'] == ['torch.float32']
        record.update(completed_cases=72,primary48_cases=48,historical24_cases=24,historical_cue_pass=sum(row['cue_pass'] is True for row in diagnostic),latency_median_seconds=statistics.median(row['seconds'] for row in rows),base_runtime_mismatch_count=sum(len(v) for v in differences.values()),base_parameters=723,empty=0,thinking_leak=0,truncated=0,eos_ended=72,post_load_peak_allocated_gpu_mib=metrics['post_load_peak_allocated_gpu_mib'],post_load_peak_reserved_gpu_mib=metrics['post_load_peak_reserved_gpu_mib'])
    out['experiments'][exp] = record
assert not (RUN/'inference.gpu.lock').exists()
out['gpu_lock_released'] = True
out['evaluation_total_records'] = 288
out['total_reported_elapsed_seconds'] = sum(v['elapsed_seconds'] for v in out['experiments'].values())
out['scope_limits'] = ['single seed; synthetic local data','shared validation, not all-family holdout','no independent across-arm LoRA initial hashes','no isolated cold-compiler timer','serial GPU but uncontrolled residual CPU/disk load','nvidia-smi samples are sparse device totals','no GGUF conversion, merge/export or product GUI deployment']
(RUN/'run-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':out['status'],'experiments':len(out['experiments']),'evaluation_total_records':out['evaluation_total_records'],'elapsed_sum':out['total_reported_elapsed_seconds'],'frozen_files_unchanged':True},ensure_ascii=False))
