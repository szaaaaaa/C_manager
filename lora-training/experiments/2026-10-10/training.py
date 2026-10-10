"""Bounded NF4 LoRA experiments; CPU self-check first, GPU runs one experiment per process."""
import argparse
import copy
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import threading
import time
import traceback

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[1]
sys.path.insert(0, str(RUN))
from inference import load_inputs, messages_for, sha256, write_json


def samples_and_split(config):
    load_inputs(config)
    finetune = importlib.import_module('finetune')
    finetune.TRAINING_DATA = Path(config['inputs']['training']['path'])
    finetune.MAX_SEQ_LENGTH = 768
    samples = finetune.load_training_data()
    groups = sorted({sample['group'] for sample in samples})
    random.Random(42).shuffle(groups)
    held = set(groups[:max(1, len(groups) // 10)])
    train = [sample for sample in samples if sample['group'] not in held]
    validation = [sample for sample in samples if sample['group'] in held]
    assert len(samples) == 168 and len(train) == 150 and len(validation) == 18
    assert held == {'pip-cache'}
    return samples, train, validation, finetune


def tokenized_samples(config, tokenizer):
    samples, train, validation, finetune = samples_and_split(config)
    formatted = finetune.format_for_chat(samples, tokenizer)
    assert len(formatted) == 168
    for raw, row in zip(samples, formatted):
        prompt = tokenizer.apply_chat_template([
            {'role': 'system', 'content': raw['instruction']},
            {'role': 'user', 'content': raw['input']}], tokenize=False,
            add_generation_prompt=True, enable_thinking=False)
        boundary = len(tokenizer.encode(prompt, add_special_tokens=False))
        assert row['labels'][:boundary] == [-100] * boundary
        assert row['labels'][boundary:] == row['input_ids'][boundary:] and boundary < len(row['labels'])
        assert len(row['input_ids']) <= 768
    train_rows = [row for raw, row in zip(samples, formatted) if raw['group'] != 'pip-cache']
    validation_rows = [row for raw, row in zip(samples, formatted) if raw['group'] == 'pip-cache']
    return train_rows, validation_rows, max(len(row['input_ids']) for row in formatted)


def self_check(model_path):
    from transformers import AutoTokenizer, DataCollatorForSeq2Seq
    config = json.loads((RUN / 'experiments/exp_007/config.json').read_text(encoding='utf-8'))
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True)
    train, validation, longest = tokenized_samples(config, tokenizer)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    collator = DataCollatorForSeq2Seq(tokenizer, label_pad_token_id=-100, return_tensors='pt')
    probe = [min(train, key=lambda row: len(row['input_ids'])), max(train, key=lambda row: len(row['input_ids']))]
    batch = collator(probe)
    assert bool((batch['labels'][batch['attention_mask'] == 0] == -100).all())
    for index, row in enumerate(probe):
        active = batch['attention_mask'][index].bool()
        assert batch['labels'][index][active].tolist() == row['labels']
    write_json(RUN / 'training_self_check.json', {
        'status': 'passed', 'cpu_only': True, 'gpu_execution': False, 'train_records': len(train),
        'validation_records': len(validation), 'held_out_groups': ['pip-cache'],
        'maximum_tokenized_length': longest, 'prompt_and_padding_mask_valid': True,
        'source_helpers': ['finetune.load_training_data', 'finetune.format_for_chat',
                           'grounding.build_sample', 'evaluate.check_response']})
    print('CPU self-check passed: 150/18 family split; all 168 complete samples fit; prompt/padding masking verified.', flush=True)


def verify_model(config, model_path):
    assert model_path.is_relative_to((ROOT / 'models').resolve()) and model_path.is_dir()
    manifest = json.loads((RUN / 'training-files.json').read_text(encoding='utf-8'))
    assert manifest['repo'] == config['model']['repo'] and manifest['revision'] == config['model']['revision']
    files = {record['file']: record for record in manifest['files']}
    index = json.loads((model_path / 'model.safetensors.index.json').read_text(encoding='utf-8'))
    shards = sorted(set(index['weight_map'].values()))
    assert len(shards) == 2
    for name in shards + ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'chat_template.jinja']:
        record = files[name]
        path = (model_path / name).resolve()
        assert path.is_relative_to(model_path) and record['status'] == 'downloaded'
        assert path.stat().st_size == record['bytes'] and sha256(path) == record['sha256'], name
    assert sorted(files[name]['bytes'] for name in shards) == sorted(config['model']['expected_safetensors_bytes'])
    config['model']['downloaded_files_manifest'] = str(RUN / 'training-files.json')
    config['model']['downloaded_files_manifest_sha256'] = sha256(RUN / 'training-files.json')


def parameter_hashes(model, torch):
    hashes = {}
    for name, parameter in model.named_parameters():
        if parameter.requires_grad:
            continue
        digest = hashlib.sha256()
        flat = parameter.detach().reshape(-1)
        digest.update(str((str(parameter.dtype), tuple(parameter.shape))).encode())
        for offset in range(0, flat.numel(), 1024 * 1024):
            block = flat[offset:offset + 1024 * 1024].contiguous().cpu().view(torch.uint8)
            digest.update(block.numpy().tobytes())
        hashes[name] = digest.hexdigest()
    return hashes


def run_training(config, directory, model, tokenizer, torch, FastLanguageModel, report, save):
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer
    from transformers import DataCollatorForSeq2Seq, TrainerCallback
    settings = config['training']
    model = FastLanguageModel.get_peft_model(model, r=8, lora_alpha=8, lora_dropout=0,
        target_modules=settings['target_modules'], bias='none', random_state=42,
        use_gradient_checkpointing='unsloth')
    train_rows, validation_rows, longest = tokenized_samples(config, tokenizer)
    if config['experiment_id'] == 'exp_007':
        train_rows = train_rows[:8]
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    trainable = {name: parameter for name, parameter in model.named_parameters() if parameter.requires_grad}
    assert trainable and all('lora_' in name for name in trainable)
    before_lora = {name: parameter.detach().cpu().clone() for name, parameter in trainable.items()}
    before_base = parameter_hashes(model, torch)
    gradients = []
    report['metrics']['gradient_observations'] = gradients
    report['metrics'].update({'maximum_tokenized_length': longest, 'prompt_mask_valid': True,
        'trainable_parameters': sum(parameter.numel() for parameter in trainable.values()),
        'train_records': len(train_rows), 'validation_records': len(validation_rows),
        'held_out_groups': ['pip-cache']})
    save()

    class CheckMask(DataCollatorForSeq2Seq):
        def __call__(self, features, return_tensors=None):
            batch = super().__call__(features, return_tensors)
            assert bool((batch['labels'][batch['attention_mask'] == 0] == -100).all())
            for index, feature in enumerate(features):
                active = batch['attention_mask'][index].bool()
                assert batch['labels'][index][active].tolist() == feature['labels']
            return batch

    class RecordTraining(TrainerCallback):
        def on_pre_optimizer_step(self, args, state, control, **kwargs):
            observed = [parameter.grad.detach() for parameter in trainable.values() if parameter.grad is not None]
            assert observed and all(bool(torch.isfinite(value).all()) for value in observed), 'Missing/nonfinite adapter gradients'
            norm = math.sqrt(sum(float(value.float().square().sum().item()) for value in observed))
            assert math.isfinite(norm) and norm > 0, 'Zero/nonfinite adapter gradient norm'
            gradients.append({'step': state.global_step + 1, 'post_clip_grad_norm': norm})
        def on_log(self, args, state, control, logs=None, **kwargs):
            record = {'step': state.global_step, **(logs or {})}
            if 'loss' in record:
                assert math.isfinite(record['loss']), 'Nonfinite training loss'
            report['training_logs'].append(record)
            report['actual_steps'] = state.global_step
            with (directory / 'records.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            save()

    formal = config['experiment_id'] == 'exp_008'
    trainer = SFTTrainer(model=model, processing_class=tokenizer,
        data_collator=CheckMask(tokenizer=tokenizer, label_pad_token_id=-100),
        train_dataset=Dataset.from_list(train_rows), eval_dataset=Dataset.from_list(validation_rows),
        callbacks=[RecordTraining()], args=SFTConfig(
            output_dir=str(directory / 'checkpoints'), max_steps=settings['max_steps'],
            num_train_epochs=1, per_device_train_batch_size=1, per_device_eval_batch_size=1,
            gradient_accumulation_steps=4, learning_rate=5e-5, warmup_steps=settings['warmup_steps'],
            logging_steps=1, bf16=True, fp16=False, max_length=768, packing=False,
            dataset_kwargs={'skip_prepare_dataset': True}, dataset_num_proc=1,
            eval_strategy='steps' if formal else 'no', eval_steps=19,
            save_strategy='steps' if formal else 'no', save_steps=19, save_total_limit=2,
            load_best_model_at_end=formal, metric_for_best_model='eval_loss', greater_is_better=False,
            optim='adamw_8bit', lr_scheduler_type='cosine', seed=42, report_to='none',
            max_grad_norm=1.0, dataloader_num_workers=0, dataloader_pin_memory=False,
            gradient_checkpointing=True, save_safetensors=True))
    assert all(id(parameter) in {id(value) for value in trainable.values()}
        for group in trainer.create_optimizer().param_groups for parameter in group['params'])
    baseline_eval = trainer.evaluate()
    report['metrics']['heldout_eval_loss_step0'] = baseline_eval['eval_loss']
    assert math.isfinite(baseline_eval['eval_loss'])
    stats = trainer.train()
    validation = trainer.evaluate()
    assert stats.global_step == settings['max_steps'] and len(gradients) == settings['max_steps']
    assert math.isfinite(stats.training_loss) and math.isfinite(validation['eval_loss'])
    after_base = parameter_hashes(model, torch)
    changed_base = sum(before_base[name] != after_base[name] for name in before_base)
    changed_lora = sum(not torch.equal(before_lora[name], parameter.detach().cpu()) for name, parameter in trainable.items())
    assert changed_base == 0 and changed_lora > 0
    report['actual_steps'] = stats.global_step
    report['metrics'].update({'optimizer_steps': stats.global_step, 'completed_optimizer_steps': stats.global_step,
        'finite_loss_and_gradients': True, 'gradient_observations': gradients,
        'changed_lora_parameter_count': changed_lora, 'changed_base_parameter_count': changed_base,
        'base_parameter_hashes_checked': len(before_base), 'train_loss': stats.training_loss,
        'heldout_eval_loss': validation['eval_loss'],
        'heldout_eval_loss_delta_vs_step0': validation['eval_loss'] - baseline_eval['eval_loss'],
        'best_eval_loss': trainer.state.best_metric, 'best_checkpoint': trainer.state.best_model_checkpoint})
    model.save_pretrained(str(directory / 'adapter'), safe_serialization=True)
    tokenizer.save_pretrained(str(directory / 'adapter'))
    report['adapter_path'] = str(directory / 'adapter')
    report['status'] = 'success'


def run_evaluation(config, directory, model, tokenizer, torch, FastLanguageModel, report, save):
    cases, knowledge, grounding, evaluator = load_inputs(config)
    if config['adapter_enabled']:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, config['adapter_source'], local_files_only=True, is_trainable=False)
    FastLanguageModel.for_inference(model)
    model.eval()
    warmup_start = time.perf_counter()
    warmup = tokenizer.apply_chat_template([{'role': 'user', 'content': '请只回复准备好了'}],
        tokenize=True, add_generation_prompt=True, enable_thinking=False,
        return_dict=True, return_tensors='pt').to('cuda:0')
    with torch.inference_mode():
        model.generate(**warmup, max_new_tokens=16, do_sample=False, use_cache=True)
    torch.cuda.synchronize()
    report['warmup_seconds'] = time.perf_counter() - warmup_start
    save()
    for case in cases:
        messages = messages_for(case, 'rag', knowledge, grounding)
        start = time.perf_counter()
        inputs = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
            enable_thinking=False, return_dict=True, return_tensors='pt').to('cuda:0')
        assert inputs.input_ids.shape[1] + 256 <= 2048, 'Context overflow; no truncation permitted'
        torch.cuda.synchronize()
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=256, do_sample=False, use_cache=True)
        torch.cuda.synchronize()
        seconds = time.perf_counter() - start
        output = generated[0][inputs.input_ids.shape[1]:]
        answer = tokenizer.decode(output, skip_special_tokens=True).strip()
        eos = model.generation_config.eos_token_id
        eos_ids = set(eos if isinstance(eos, list) else [eos])
        record = {'id': case['id'], 'path': case['path'], 'messages': messages, 'answer': answer,
            'seconds': seconds, 'input_tokens': inputs.input_ids.shape[1], 'output_tokens': len(output),
            'truncated': len(output) >= 256 and int(output[-1]) not in eos_ids,
            **evaluator.check_response(case, answer)}
        report['records'].append(record)
        with (directory / 'records.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        report['metrics'].update({'completed_cases': len(report['records']),
            'cue_pass_count': sum(row['cue_pass'] for row in report['records']),
            'empty_answer_count': sum(not row['answer'] for row in report['records']),
            'truncated_answer_count': sum(row['truncated'] for row in report['records']),
            'latency_median_seconds': statistics.median(row['seconds'] for row in report['records'])})
        print(json.dumps(record, ensure_ascii=False), flush=True)
        save()
    report['status'] = 'success'


def run(experiment, model_path):
    assert experiment in {'exp_007', 'exp_008', 'exp_009', 'exp_010'}
    directory = (RUN / 'experiments' / experiment).resolve()
    assert directory.is_relative_to(RUN.resolve())
    assert not (directory / 'result.json').exists(), 'Refusing to overwrite an executed experiment'
    config = copy.deepcopy(json.loads((directory / 'config.json').read_text(encoding='utf-8')))
    config['model']['path'] = str(model_path)
    started = time.perf_counter()
    lock_path = RUN / 'inference.gpu.lock'
    lock_fd = None
    timer = None
    torch = None
    state_lock = threading.RLock()
    report = {'experiment_id': experiment, 'status': 'running', 'exit_code': None, 'actual_steps': 0,
        'elapsed_seconds': 0, 'metrics': {'out_of_memory': False}, 'training_logs': [], 'records': [],
        'review_status': 'pending', 'configuration_path': str(directory / 'executed_config.json')}
    def save():
        with state_lock:
            report['elapsed_seconds'] = time.perf_counter() - started
            write_json(directory / 'result.json', report)
    def timeout():
        with state_lock:
            report.update({'status': 'timed_out', 'exit_code': 124, 'error': 'Hard experiment deadline exceeded'})
            save()
        # shortcut: abrupt timeout leaves a PID lock; verify the PID has exited before removing it.
        os._exit(124)
    exit_code = 1
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_fd, str(os.getpid()).encode())
        timer = threading.Timer(config['deadline_seconds'], timeout)
        timer.daemon = True
        timer.start()
        for dependency in config.get('depends_on', []):
            prior = json.loads((RUN / 'experiments' / dependency / 'result.json').read_text(encoding='utf-8'))
            assert prior['status'] == 'success', 'Dependency failed or incomplete: ' + dependency
        verify_model(config, model_path)
        write_json(directory / 'executed_config.json', config)
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['UNSLOTH_DISABLE_STATISTICS'] = '1'
        from unsloth import FastLanguageModel
        import torch
        from transformers import BitsAndBytesConfig
        assert torch.cuda.is_available() and torch.cuda.is_bf16_supported()
        torch.manual_seed(42)
        torch.cuda.reset_peak_memory_stats()
        report['versions'] = {name: importlib.metadata.version(name) for name in ['torch', 'unsloth', 'trl', 'transformers', 'peft', 'bitsandbytes']}
        report['gpu'] = torch.cuda.get_device_name(0)
        loading = time.perf_counter()
        model, processor = FastLanguageModel.from_pretrained(model_name=str(model_path),
            max_seq_length=768 if experiment in {'exp_007', 'exp_008'} else 2048,
            dtype=torch.bfloat16, load_in_4bit=True, load_in_16bit=False, full_finetuning=False,
            quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16),
            device_map={'': 0}, local_files_only=True, use_exact_model_name=True,
            revision=config['model']['revision'], trust_remote_code=False)
        tokenizer = getattr(processor, 'tokenizer', processor)
        report['model_load_seconds'] = time.perf_counter() - loading
        assert all(parameter.device.type == 'cuda' for parameter in model.parameters()), 'CPU offload is outside this experiment'
        assert model.config.quantization_config['bnb_4bit_quant_type'] == 'nf4'
        if experiment in {'exp_007', 'exp_008'}:
            run_training(config, directory, model, tokenizer, torch, FastLanguageModel, report, save)
        else:
            run_evaluation(config, directory, model, tokenizer, torch, FastLanguageModel, report, save)
        exit_code = 0
    except BaseException as error:
        report.update({'status': 'failed', 'error': str(error), 'traceback': traceback.format_exc()})
        report['metrics']['out_of_memory'] = 'out of memory' in str(error).lower()
        print(report['traceback'], flush=True)
    finally:
        if timer:
            timer.cancel()
        if torch is not None and torch.cuda.is_available():
            report['metrics']['peak_allocated_gpu_mib'] = torch.cuda.max_memory_allocated() / 1024 ** 2
            report['metrics']['peak_reserved_gpu_mib'] = torch.cuda.max_memory_reserved() / 1024 ** 2
        report['exit_code'] = exit_code
        save()
        if lock_fd is not None:
            os.close(lock_fd)
            assert lock_path.resolve().is_relative_to(RUN.resolve())
            lock_path.unlink()
    return exit_code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--experiment', choices=['exp_007', 'exp_008', 'exp_009', 'exp_010'])
    parser.add_argument('--model-path', type=Path, default=ROOT / 'models/qwen35-4b-training')
    args = parser.parse_args()
    assert ROOT.resolve().drive.lower() == 'd:' and Path.cwd().resolve() == ROOT.resolve()
    if args.self_check:
        self_check(args.model_path.resolve())
    else:
        assert args.experiment, '--experiment is required for GPU execution'
        sys.exit(run(args.experiment, args.model_path.resolve()))
