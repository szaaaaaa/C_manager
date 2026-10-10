"""Frozen-input utilities for this NF4 study; no live retrieval or project-relative imports."""
import hashlib
import json
from pathlib import Path
import sys
RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[1]
sys.path.insert(0, str(RUN / 'helpers'))
import checks


def write_json(path, value):
    path = Path(path).resolve()
    assert path.is_relative_to(RUN.resolve())
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_inputs(config):
    for record in config['inputs'].values():
        path = Path(record['path']).resolve()
        assert path.is_relative_to(ROOT.resolve()) and sha256(path) == record['sha256'], path


def load_inputs(config):
    verify_inputs(config)
    record = config['inputs']['eval_cases']
    cases = json.loads(Path(record['path']).read_text(encoding='utf-8'))
    assert len(cases) == record['records'] and len({case['id'] for case in cases}) == len(cases)
    for case in cases:
        assert case['instruction'].strip() and case['input'].strip()
        assert case['path'] in case['input'] and isinstance(case['facts'], str)
        assert not case['facts'] or case['facts'] in case['input'], case['id']
    counts = {subset:sum(case['subset'] == subset for case in cases) for subset in {case['subset'] for case in cases}}
    assert counts == record['subsets'], counts
    return cases, None, None, checks


def messages_for(case, *unused):
    expected = [{'role':'system', 'content':case['instruction']}, {'role':'user', 'content':case['input']}]
    assert case['messages'] == expected, 'Frozen messages differ from explicit instruction/input'
    return case['messages']


def cue_check(case, answer):
    if 'required' in case and 'forbidden' in case:
        return {'cue_checked':True, **checks.check_response(case, answer)}
    return {'cue_checked':False, 'cue_pass':None, 'missing_cues':[], 'forbidden_phrases':[]}
