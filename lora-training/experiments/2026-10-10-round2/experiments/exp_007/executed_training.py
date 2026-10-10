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
import shutil
import statistics
import sys
import threading
import time
import traceback

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[1]
sys.path.insert(0, str(RUN))
from inference import load_inputs, messages_for, sha256, write_json, verify_inputs, cue_check


def has_thinking_leak(raw_output):
    return any(marker in raw_output.lower() for marker in (
        '<think>', '</think>', '<|channel>thought', '<|channel|>thought', '[think]', '[/think]'))


def thinking_self_check():
    assert not has_thinking_leak('这是缓存，确认后可以清理。<|im_end|>')
    assert not has_thinking_leak('The word thought alone is ordinary prose.')
    for raw in ['<think>隐藏推理</think>答案', '</think>答案', '<|channel>thought分析',
                '<|channel|>thought分析', '[THINK]分析[/THINK]']:
        assert has_thinking_leak(raw), raw
    write_json(RUN / 'training_thinking_self_check.json', {
        'status': 'passed', 'cpu_only': True, 'gpu_execution': False,
        'negative_cases': 2, 'positive_cases': 5,
        'raw_decode_skip_special_tokens': False, 'leak_blocks_success': True})
    print('CPU thinking-leak self-check passed: raw special tokens retained; leaks block success.', flush=True)


def load_samples(record):
    samples = [json.loads(line) for line in Path(record['path']).read_text(encoding='utf-8').splitlines() if line.strip()]
    assert len(samples) == record['records'] and len({sample['id'] for sample in samples}) == len(samples)
    for sample in samples:
        assert all(isinstance(sample[key], str) and sample[key].strip() for key in ['instruction','input','output'])
        assert '{verdict}' not in sample['instruction']
    return samples


def samples_and_split(config):
    verify_inputs(config)
    import formatting
    formatting.MAX_SEQ_LENGTH = config['training']['max_seq_length']
    train = load_samples(config['inputs']['training'])
    validation = load_samples(config['inputs']['validation'])
    assert not ({sample['id'] for sample in train} & {sample['id'] for sample in validation}), 'Train/validation IDs overlap'
    assert not ({sample['path'].lower().replace('/', '\\') for sample in train}
        & {sample['path'].lower().replace('/', '\\') for sample in validation}), 'Train/validation paths overlap'
    return train + validation, train, validation, formatting


def tokenized_samples(config, tokenizer):
    samples, train, validation, formatting = samples_and_split(config)
    formatted = formatting.format_for_chat(samples, tokenizer)
    assert len(formatted) == len(samples)
    for raw, row in zip(samples, formatted):
        prompt = tokenizer.apply_chat_template([
            {'role':'system','content':raw['instruction']}, {'role':'user','content':raw['input']}],
            tokenize=False, add_generation_prompt=True, enable_thinking=False)
        boundary = len(tokenizer.encode(prompt, add_special_tokens=False))
        assert row['labels'][:boundary] == [-100] * boundary
        assert row['labels'][boundary:] == row['input_ids'][boundary:] and boundary < len(row['labels'])
        assert len(row['input_ids']) <= config['training']['max_seq_length']
    return formatted[:len(train)], formatted[len(train):], max(len(row['input_ids']) for row in formatted)


def self_check(model_path):
    thinking_self_check()
    from transformers import AutoTokenizer, DataCollatorForSeq2Seq
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    collator = DataCollatorForSeq2Seq(tokenizer, label_pad_token_id=-100, return_tensors='pt')
    results = []
    configs = []
    for experiment in ['exp_001','exp_002','exp_003']:
        config = json.loads((RUN / 'experiments' / experiment / 'config.json').read_text(encoding='utf-8'))
        train, validation, longest = tokenized_samples(config, tokenizer)
        probe = [min(train, key=lambda row:len(row['input_ids'])), max(train, key=lambda row:len(row['input_ids']))]
        batch = collator(probe)
        assert bool((batch['labels'][batch['attention_mask'] == 0] == -100).all())
        for index,row in enumerate(probe):
            assert batch['labels'][index][batch['attention_mask'][index].bool()].tolist() == row['labels']
        samples, raw_train, raw_validation, formatting = samples_and_split(config)
        overlong = {**raw_train[0], 'output':'不确定用途。' * config['training']['max_seq_length']}
        try:
            formatting.format_for_chat([overlong], tokenizer)
        except ValueError as error:
            assert 'exceeds MAX_SEQ_LENGTH' in str(error)
        else:
            raise AssertionError('Overlong answers were silently truncated/accepted')
        results.append({'experiment':experiment,'train_records':len(train),'validation_records':len(validation),
            'maximum_tokenized_length':longest,'prompt_padding_mask_valid':True,'overlong_rejected':True})
        configs.append(config)
    assert len({config['inputs']['validation']['sha256'] for config in configs}) == 1
    train_a, train_b = load_samples(configs[0]['inputs']['training']), load_samples(configs[1]['inputs']['training'])
    assert [(row['instruction'],row['input']) for row in train_a] == [(row['instruction'],row['input']) for row in train_b], 'A/B inputs differ'
    cases, _, _, _ = load_inputs(configs[0])
    for experiment in ['exp_004','exp_005','exp_006','exp_007']:
        config = json.loads((RUN / 'experiments' / experiment / 'config.json').read_text(encoding='utf-8'))
        observed, _, _, _ = load_inputs(config)
        assert [messages_for(case) for case in observed] == [messages_for(case) for case in cases]
    write_json(RUN / 'training_self_check.json', {'status':'passed','gpu_execution':False,'arms':results,
        'shared_validation_hash':configs[0]['inputs']['validation']['sha256'],
        'same_A_B_inputs':True,'all_evaluation_inputs_equal':True,'eval_cases':len(cases),
        'eval_subsets':configs[0]['inputs']['eval_cases']['subsets'], 'eos_configuration':eos_check(tokenizer)})
    print('CPU frozen data/split/masking/overlong-rejection/evaluation-input/EOS self-check passed.', flush=True)


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


def tensor_hash(tensor, torch, float32=False):
    digest = hashlib.sha256()
    flat = tensor.detach().reshape(-1)
    for offset in range(0, flat.numel(), 1024 * 1024):
        block = flat[offset:offset + 1024 * 1024].contiguous().cpu()
        if float32:
            block = block.float()
        digest.update(block.view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def normalized_base_name(name):
    if name.startswith('base_model.model.'):
        name = name[len('base_model.model.'):]
    return name.replace('.base_layer.', '.')


def parameter_state(model, torch, names=None, normalize=False):
    state = {}
    for name, parameter in model.named_parameters():
        if 'lora_' in name or (names is not None and name not in names):
            continue
        key = normalized_base_name(name) if normalize else name
        assert key not in state, 'Base parameter name normalization is not one-to-one: ' + key
        quant = getattr(parameter, 'quant_state', None)
        quant_digest = hashlib.sha256()
        if quant is not None:
            for quant_key, value in sorted(quant.as_dict(packed=True).items()):
                quant_digest.update(quant_key.encode())
                if isinstance(value, torch.Tensor):
                    quant_digest.update(str((str(value.dtype), tuple(value.shape))).encode())
                    quant_digest.update(tensor_hash(value, torch).encode())
                else:
                    quant_digest.update(repr(value).encode())
        state[key] = {'source_name': name, 'dtype': str(parameter.dtype), 'shape': list(parameter.shape),
            'requires_grad': bool(parameter.requires_grad), 'device': str(parameter.device),
            'raw_sha256': tensor_hash(parameter, torch),
            'float32_value_sha256': tensor_hash(parameter, torch, float32=True) if parameter.is_floating_point() else None,
            'quant_state_sha256': quant_digest.hexdigest() if quant is not None else None}
    if names is not None:
        assert set(names) == set(state), 'Frozen base parameter names changed'
    return state


def state_changes(before, after):
    assert before.keys() == after.keys(), 'Frozen base parameter name set changed'
    changes = []
    for name in before:
        old, new = before[name], after[name]
        if any(old[key] != new[key] for key in ['dtype', 'shape', 'raw_sha256', 'quant_state_sha256']):
            same_values = old['shape'] == new['shape'] and old['quant_state_sha256'] == new['quant_state_sha256'] and (
                old['float32_value_sha256'] == new['float32_value_sha256']
                if old['float32_value_sha256'] is not None else old['raw_sha256'] == new['raw_sha256'])
            changes.append({'name': name, 'before_dtype': old['dtype'], 'after_dtype': new['dtype'],
                'before_shape': old['shape'], 'after_shape': new['shape'],
                'float32_values_equal': same_values, 'before_raw_sha256': old['raw_sha256'],
                'after_raw_sha256': new['raw_sha256']})
    return changes


def eos_check(tokenizer):
    messages = [{'role': 'user', 'content': '请只回复准备好了'}, {'role': 'assistant', 'content': '准备好了'}]
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False, enable_thinking=False)
    assert tokenizer.eos_token and tokenizer.eos_token_id is not None
    assert rendered.rstrip().endswith(tokenizer.eos_token), 'Template does not end assistant turn with tokenizer EOS'
    assert tokenizer.encode(rendered.rstrip(), add_special_tokens=False)[-1] == tokenizer.eos_token_id
    return {'tokenizer_eos_token': tokenizer.eos_token, 'actual_eos_token_id': tokenizer.eos_token_id}


def diagnostic_self_check(model_path):
    import torch
    from transformers import AutoTokenizer
    class Probe:
        def __init__(self, parameter, name='model.norm.weight'):
            self.parameter, self.name = parameter, name
        def named_parameters(self):
            return [(self.name, self.parameter)]
    initial = torch.nn.Parameter(torch.tensor([0.5, 1.0], dtype=torch.bfloat16), requires_grad=False)
    converted = torch.nn.Parameter(initial.detach().float(), requires_grad=False)
    one, two = parameter_state(Probe(initial), torch), parameter_state(Probe(converted), torch)
    changes = state_changes(one, two)
    assert len(changes) == 1 and changes[0]['float32_values_equal']
    converted.data[0] += 0.25
    assert not state_changes(one, parameter_state(Probe(converted), torch))[0]['float32_values_equal']
    names = ['model.layer.weight', 'base_model.model.model.layer.base_layer.weight']
    assert normalized_base_name(names[0]) == normalized_base_name(names[1])
    class Collision:
        def named_parameters(self):
            return [(name, initial) for name in names]
    try:
        parameter_state(Collision(), torch, normalize=True)
    except AssertionError:
        pass
    else:
        raise AssertionError('Normalization collision was not rejected')
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True)
    config = json.loads((model_path / 'config.json').read_text(encoding='utf-8'))
    eos = eos_check(tokenizer)
    write_json(RUN / 'diagnostic_self_check.json', {'status': 'passed', 'gpu_execution': False,
        'dtype_only_and_real_change_distinguished': True, 'normalization_collision_rejected': True,
        'original_text_config_eos_token_id': config['text_config']['eos_token_id'], **eos})
    print('CPU diagnostic self-check passed: dtype-only vs numeric changes, unique names, template EOS.', flush=True)


def run_training(config, directory, model, tokenizer, torch, FastLanguageModel, report, save):
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer
    from transformers import DataCollatorForSeq2Seq, TrainerCallback
    settings = config['training']
    setup_started = time.perf_counter()
    model = FastLanguageModel.get_peft_model(model, r=8, lora_alpha=8, lora_dropout=0,
        target_modules=settings['target_modules'], bias='none', random_state=42,
        use_gradient_checkpointing='unsloth')
    train_rows, validation_rows, longest = tokenized_samples(config, tokenizer)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    trainable = {name: parameter for name, parameter in model.named_parameters() if parameter.requires_grad}
    assert trainable and all('lora_' in name for name in trainable)
    frozen_names = {name for name, parameter in model.named_parameters() if 'lora_' not in name}
    stages = {}
    def capture(stage):
        capturing = time.perf_counter()
        observed = parameter_state(model, torch, frozen_names)
        assert all(not value['requires_grad'] for value in observed.values()), 'Frozen base became trainable'
        stages[stage] = observed
        report.setdefault('base_state_capture_seconds', {})[stage] = time.perf_counter() - capturing
        write_json(directory / ('base_' + stage + '.json'), observed)
        write_json(directory / 'base_stage_changes.json', {key: state_changes(stages['before_trainer'], value)
            for key, value in stages.items() if key != 'before_trainer'})
        return observed
    capture('before_trainer')
    before_lora = None
    before_base = None
    gradients = []
    report['metrics']['gradient_observations'] = gradients
    report['training_setup_seconds'] = time.perf_counter() - setup_started
    report['metrics'].update({'maximum_tokenized_length': longest, 'prompt_mask_valid': True,
        'trainable_parameters': sum(parameter.numel() for parameter in trainable.values()),
        'train_records': len(train_rows), 'validation_records': len(validation_rows),
        'validation_groups': sorted({row['group'] for row in load_samples(config['inputs']['validation'])})})
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
        def on_train_begin(self, args, state, control, **kwargs):
            self.first_step_started = time.perf_counter()
        def on_step_end(self, args, state, control, **kwargs):
            if state.global_step == 1:
                report['first_optimizer_step_seconds_including_any_cold_compile'] = time.perf_counter() - self.first_step_started
                save()
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

    formal = settings['max_steps'] == 40
    trainer = SFTTrainer(model=model, processing_class=tokenizer,
        data_collator=CheckMask(tokenizer=tokenizer, label_pad_token_id=-100),
        train_dataset=Dataset.from_list(train_rows), eval_dataset=Dataset.from_list(validation_rows),
        callbacks=[RecordTraining()], args=SFTConfig(
            output_dir=str(directory / 'checkpoints'), max_steps=settings['max_steps'],
            num_train_epochs=1, per_device_train_batch_size=1, per_device_eval_batch_size=1,
            gradient_accumulation_steps=4, learning_rate=5e-5, warmup_steps=settings['warmup_steps'],
            logging_steps=1, bf16=True, fp16=False, max_length=768, packing=False,
            dataset_kwargs={'skip_prepare_dataset': True}, dataset_num_proc=1,
            eval_strategy='steps' if formal else 'no', eval_steps=settings['eval_steps'],
            save_strategy='steps' if formal else 'no', save_steps=settings['save_steps'], save_total_limit=2,
            load_best_model_at_end=formal, metric_for_best_model='eval_loss', greater_is_better=False,
            optim='adamw_8bit', lr_scheduler_type='cosine', seed=42, report_to='none',
            max_grad_norm=1.0, dataloader_num_workers=0, dataloader_pin_memory=False,
            gradient_checkpointing=True))
    assert all(id(parameter) in {id(value) for value in trainable.values()}
        for group in trainer.create_optimizer().param_groups for parameter in group['params'])
    capture('after_trainer')
    first_forward = time.perf_counter()
    baseline_eval = trainer.evaluate()
    report['first_heldout_evaluation_seconds_including_any_cold_compile'] = time.perf_counter() - first_forward
    report['metrics']['heldout_eval_loss_step0'] = baseline_eval['eval_loss']
    assert math.isfinite(baseline_eval['eval_loss'])
    FastLanguageModel.for_training(model)
    before_base = capture('after_step0_before_training')
    trainable = {name: parameter for name, parameter in model.named_parameters() if parameter.requires_grad}
    assert trainable and all('lora_' in name for name in trainable)
    assert all(id(parameter) in {id(value) for value in trainable.values()}
        for group in trainer.optimizer.param_groups for parameter in group['params'])
    before_lora = {name: parameter.detach().cpu().clone() for name, parameter in trainable.items()}
    report['base_freeze_baseline_stage'] = 'after_step0_before_training'
    report['metrics']['preparation_changed_base_parameter_count'] = len(state_changes(stages['before_trainer'], before_base))
    save()
    report['metrics']['setup_and_step0_peak_allocated_gpu_mib'] = torch.cuda.max_memory_allocated() / 1024 ** 2
    torch.cuda.reset_peak_memory_stats()
    stats = trainer.train()
    report['metrics']['training_peak_allocated_gpu_mib'] = torch.cuda.max_memory_allocated() / 1024 ** 2
    report['metrics']['training_peak_reserved_gpu_mib'] = torch.cuda.max_memory_reserved() / 1024 ** 2
    after_base = capture('after_training_before_final_eval')
    validation = trainer.evaluate()
    assert stats.global_step == settings['max_steps'] and len(gradients) == settings['max_steps']
    assert math.isfinite(stats.training_loss) and math.isfinite(validation['eval_loss'])
    changes = state_changes(before_base, after_base)
    changed_base = len(changes)
    changed_lora = sum(not torch.equal(before_lora[name], parameter.detach().cpu()) for name, parameter in trainable.items())
    report['metrics'].update({'changed_base_parameter_count': changed_base, 'changed_lora_parameter_count': changed_lora,
        'changed_base_parameter_names': [change['name'] for change in changes], 'training_base_changes': changes})
    save()
    assert changed_base == 0, f'Frozen base changed during training: {changes}'
    assert changed_lora > 0, 'No LoRA parameters changed during training'
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
    import struct
    adapter_path = directory / 'adapter'
    selected = Path(trainer.state.best_model_checkpoint)
    manifest_files = []
    for filename in ['adapter_model.safetensors','adapter_config.json']:
        path = adapter_path / filename
        digest = sha256(path)
        assert digest == sha256(selected / filename), 'Final adapter differs from selected checkpoint'
        manifest_files.append({'file':filename,'bytes':path.stat().st_size,'sha256':digest})
    with (adapter_path / 'adapter_model.safetensors').open('rb') as stream:
        header_length = struct.unpack('<Q', stream.read(8))[0]
        assert header_length < 1024 * 1024
        header = json.loads(stream.read(header_length))
    write_json(directory / 'adapter-manifest.json', {'files':manifest_files,
        'selected_checkpoint':str(selected),'selected_checkpoint_step':int(selected.name.split('-')[-1]),
        'selected_checkpoint_validation_nll':trainer.state.best_metric,
        'adapter_storage_dtypes':sorted({value['dtype'] for name,value in header.items() if name != '__metadata__'}),
        'selection_basis':'Only shared validation NLL; evaluation cases never used for selection',
        'base_revision':config['model']['revision']})
    report['adapter_path'] = str(directory / 'adapter')
    report['status'] = 'success'


def run_evaluation(config, directory, model, tokenizer, torch, FastLanguageModel, report, save):
    cases, knowledge, grounding, evaluator = load_inputs(config)
    if config['adapter_enabled']:
        from peft import PeftModel
        manifest = json.loads(Path(config['adapter_manifest']).read_text(encoding='utf-8'))
        for record in manifest['files']:
            path = Path(config['adapter_source']) / record['file']
            assert path.stat().st_size == record['bytes'] and sha256(path) == record['sha256']
        report['adapter_manifest_sha256'] = sha256(Path(config['adapter_manifest']))
        model = PeftModel.from_pretrained(model, config['adapter_source'], local_files_only=True, is_trainable=False)
    FastLanguageModel.for_inference(model)
    model.requires_grad_(False)
    model.eval()
    warmup_start = time.perf_counter()
    warmup = tokenizer.apply_chat_template([{'role': 'user', 'content': '请只回复准备好了'}],
        tokenize=True, add_generation_prompt=True, enable_thinking=False,
        return_dict=True, return_tensors='pt').to('cuda:0')
    with torch.inference_mode():
        model.generate(**warmup, max_new_tokens=16, do_sample=False, use_cache=True, eos_token_id=tokenizer.eos_token_id)
    torch.cuda.synchronize()
    report['warmup_seconds'] = time.perf_counter() - warmup_start
    runtime_state = parameter_state(model, torch, normalize=True)
    assert all(not value['requires_grad'] for value in runtime_state.values())
    write_json(directory / 'base_runtime_after_warmup.json', runtime_state)
    reference_path = Path(config['runtime_base_reference'])
    if reference_path.resolve() != (directory / 'base_runtime_after_warmup.json').resolve():
        reference = json.loads(reference_path.read_text(encoding='utf-8'))
        assert reference.keys() == runtime_state.keys(), 'Runtime base parameter names differ from reference'
        fields = ['dtype','shape','raw_sha256','float32_value_sha256','quant_state_sha256']
        mismatches = {field:[name for name in reference if reference[name][field] != runtime_state[name][field]] for field in fields}
        write_json(directory / 'runtime_base_comparison.json', {'reference':str(reference_path),
            'base_parameters':len(reference),'mismatches':mismatches,'status':'passed' if not any(mismatches.values()) else 'failed'})
        assert not any(mismatches.values()), 'Runtime base differs from pair-group reference'
    report['adapter_runtime_dtypes'] = sorted({str(parameter.dtype) for name, parameter in model.named_parameters() if 'lora_' in name})
    save()
    for case in cases:
        messages = messages_for(case, 'rag', knowledge, grounding)
        start = time.perf_counter()
        inputs = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
            enable_thinking=False, return_dict=True, return_tensors='pt').to('cuda:0')
        assert inputs.input_ids.shape[1] + 256 <= 2048, 'Context overflow; no truncation permitted'
        torch.cuda.synchronize()
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=256, do_sample=False, use_cache=True, eos_token_id=tokenizer.eos_token_id)
        torch.cuda.synchronize()
        seconds = time.perf_counter() - start
        output = generated[0][inputs.input_ids.shape[1]:]
        raw_output = tokenizer.decode(output, skip_special_tokens=False)
        thinking_leak = has_thinking_leak(raw_output)
        answer = tokenizer.decode(output, skip_special_tokens=True).strip()
        eos = model.generation_config.eos_token_id
        eos_ids = set(eos if isinstance(eos, list) else [eos])
        record = {'id': case['id'], 'path': case['path'], 'subset':case['subset'],
            'case_metadata':{key:value for key,value in case.items() if key not in ['instruction','input']},
            'messages': messages, 'answer': answer,
            'raw_output': raw_output, 'thinking_leak': thinking_leak,
            'seconds': seconds, 'input_tokens': inputs.input_ids.shape[1], 'output_tokens': len(output),
            'truncated': len(output) >= 256 and int(output[-1]) not in eos_ids,
            **cue_check(case, answer)}
        report['records'].append(record)
        with (directory / 'records.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        report['metrics'].update({'completed_cases': len(report['records']),
            'cue_pass_count': sum(row['cue_pass'] is True for row in report['records']),
            'empty_answer_count': sum(not row['answer'] for row in report['records']),
            'thinking_leak_count': sum(row['thinking_leak'] for row in report['records']),
            'truncated_answer_count': sum(row['truncated'] for row in report['records']),
            'latency_median_seconds': statistics.median(row['seconds'] for row in report['records'])})
        report['metrics']['cue_checked_cases'] = sum(row['cue_checked'] for row in report['records'])
        report['metrics']['subset_metrics'] = {subset:{
            'completed_cases':sum(row['subset'] == subset for row in report['records']),
            'cue_checked_cases':sum(row['subset'] == subset and row['cue_checked'] for row in report['records']),
            'cue_pass_count':sum(row['subset'] == subset and row['cue_pass'] is True for row in report['records'])}
            for subset in config['inputs']['eval_cases']['subsets']}
        print(json.dumps(record, ensure_ascii=False), flush=True)
        save()
        if thinking_leak:
            raise RuntimeError('Unexpected thinking marker in raw generated tokens despite thinking disabled')
    assert report['metrics']['thinking_leak_count'] == 0
    report['status'] = 'success'


def run(experiment, model_path):
    assert experiment in {'exp_001','exp_002','exp_003','exp_004','exp_005','exp_006','exp_007'}
    directory = (RUN / 'experiments' / experiment).resolve()
    assert directory.is_relative_to(RUN.resolve())
    assert not (directory / 'result.json').exists(), 'Refusing to overwrite an executed experiment'
    config = copy.deepcopy(json.loads((directory / 'config.json').read_text(encoding='utf-8')))
    assert config['data_freeze_approved'], 'Root data/config freeze approval is required before GPU execution'
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
            assert dependency in {'exp_001','exp_002','exp_003','exp_004'}
            prior = json.loads((RUN / 'experiments' / dependency / 'result.json').read_text(encoding='utf-8'))
            assert prior['status'] == 'success', 'Dependency failed/incomplete: ' + dependency
        verify_inputs(config)
        verify_model(config, model_path)
        config['executed_runner_sha256'] = sha256(Path(__file__))
        shutil.copy2(Path(__file__), directory / 'executed_training.py')
        write_json(directory / 'executed_config.json', config)
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['UNSLOTH_DISABLE_STATISTICS'] = '1'
        cache_paths = [Path(os.environ[key]) for key in ['CUDA_CACHE_PATH', 'TORCHINDUCTOR_CACHE_DIR', 'TRITON_CACHE_DIR', 'UNSLOTH_COMPILE_LOCATION']]
        assert all(path.resolve().is_relative_to(ROOT.resolve()) for path in cache_paths)
        report['compile_cache_files_before'] = {str(path): len(list(path.rglob('*'))) for path in cache_paths}
        report['timing_scope'] = 'Import/first forward/first optimizer timings include possible cold compilation; no isolated compiler timer. Serial GPU; residual CPU/disk background load is not controlled.'
        importing = time.perf_counter()
        from unsloth import FastLanguageModel
        report['unsloth_import_seconds_including_patch_compile'] = time.perf_counter() - importing
        import torch
        from transformers import BitsAndBytesConfig
        assert torch.cuda.is_available() and torch.cuda.is_bf16_supported()
        torch.manual_seed(42)
        torch.cuda.reset_peak_memory_stats()
        report['versions'] = {name: importlib.metadata.version(name) for name in ['torch', 'unsloth', 'trl', 'transformers', 'peft', 'bitsandbytes']}
        report['gpu'] = torch.cuda.get_device_name(0)
        loading = time.perf_counter()
        model, processor = FastLanguageModel.from_pretrained(model_name=str(model_path),
            max_seq_length=768 if experiment in {'exp_001','exp_002','exp_003'} else 2048,
            dtype=torch.bfloat16, load_in_4bit=True, load_in_16bit=False, full_finetuning=False,
            quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16),
            device_map={'': 0}, local_files_only=True, use_exact_model_name=True,
            revision=config['model']['revision'], trust_remote_code=False)
        tokenizer = getattr(processor, 'tokenizer', processor)
        report['eos_configuration'] = {'original_generation_eos_token_id': model.generation_config.eos_token_id,
            'original_text_config_eos_token_id': getattr(getattr(model.config, 'text_config', model.config), 'eos_token_id', None),
            **eos_check(tokenizer)}
        model.generation_config.eos_token_id = tokenizer.eos_token_id
        model.config.eos_token_id = tokenizer.eos_token_id
        if hasattr(model.config, 'text_config'):
            model.config.text_config.eos_token_id = tokenizer.eos_token_id
        model.generation_config.pad_token_id = tokenizer.pad_token_id or tokenizer.eos_token_id
        report['model_load_seconds'] = time.perf_counter() - loading
        report['metrics'].update({'loading_peak_allocated_gpu_mib': torch.cuda.max_memory_allocated() / 1024 ** 2,
            'loading_peak_reserved_gpu_mib': torch.cuda.max_memory_reserved() / 1024 ** 2,
            'loaded_allocated_gpu_mib': torch.cuda.memory_allocated() / 1024 ** 2,
            'loaded_reserved_gpu_mib': torch.cuda.memory_reserved() / 1024 ** 2})
        torch.cuda.reset_peak_memory_stats()
        assert all(parameter.device.type == 'cuda' for parameter in model.parameters()), 'CPU offload is outside this experiment'
        from bitsandbytes.nn import Linear4bit
        quantized = [module for module in model.modules() if isinstance(module, Linear4bit)]
        assert quantized, 'No actual bitsandbytes Linear4bit modules loaded'
        assert all(module.weight.quant_state is not None and module.weight.quant_state.quant_type == 'nf4'
            and module.weight.quant_state.state2 is not None and module.compute_dtype == torch.bfloat16
            for module in quantized), 'Actual module is not NF4 double quant + bf16 compute'
        report['metrics']['actual_nf4_double_quant_bf16_linear_modules'] = len(quantized)
        save()
        if experiment in {'exp_001','exp_002','exp_003'}:
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
            report['metrics']['post_load_peak_allocated_gpu_mib'] = torch.cuda.max_memory_allocated() / 1024 ** 2
            report['metrics']['peak_allocated_gpu_mib'] = max(report['metrics'].get('loading_peak_allocated_gpu_mib', 0),
                report['metrics'].get('setup_and_step0_peak_allocated_gpu_mib', 0), torch.cuda.max_memory_allocated() / 1024 ** 2)
            report['metrics']['post_load_peak_reserved_gpu_mib'] = torch.cuda.max_memory_reserved() / 1024 ** 2
            report['metrics']['peak_reserved_gpu_mib'] = max(report['metrics'].get('loading_peak_reserved_gpu_mib', 0), torch.cuda.max_memory_reserved() / 1024 ** 2)
        log_path = directory / 'run.log'
        if log_path.exists():
            log_text = log_path.read_text(encoding='utf-8', errors='replace')
            report['observed_environment_warnings'] = [warning for warning in [
                'does not accept `num_items_in_batch`',
                'The fast path is not available',
                'Flash Attention 2 installation seems to be broken'] if warning in log_text]
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
    parser.add_argument('--self-check-thinking', action='store_true')
    parser.add_argument('--self-check-diagnostic', action='store_true')
    parser.add_argument('--experiment', choices=['exp_001','exp_002','exp_003','exp_004','exp_005','exp_006','exp_007'])
    parser.add_argument('--model-path', type=Path, default=ROOT / 'models/qwen35-4b-training')
    args = parser.parse_args()
    assert ROOT.resolve().drive.lower() == 'd:' and Path.cwd().resolve() == ROOT.resolve()
    if args.self_check_diagnostic:
        diagnostic_self_check(args.model_path.resolve())
    elif args.self_check_thinking:
        thinking_self_check()
    elif args.self_check:
        self_check(args.model_path.resolve())
    else:
        assert args.experiment, '--experiment is required for GPU execution'
        sys.exit(run(args.experiment, args.model_path.resolve()))
