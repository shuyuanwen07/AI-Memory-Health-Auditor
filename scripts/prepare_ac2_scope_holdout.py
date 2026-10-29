"""Freeze and prepare source-bound blind review for AC2 scope guard v2.

Run ``freeze`` before ``prepare``. This offline diagnostic reads the ten
previously reserved source-only candidates as-is; no model calls or labels.
The guard's flags and join key are private, outside the reviewer folders.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/proposal-delivery/ac2-scope-v2-independent-review-20261029-v1'
SOURCE = ROOT / 'datasets/assessment-candidates-v1/candidate_test'
GUARD = ROOT / 'output/proposal-delivery/ac2-scope-guard-development-20261029/scope_guard_candidate_v2.py'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def runtime_hashes():
    # Hash the actual local application source, not a mutable version label.
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted((ROOT/'backend/app').rglob('*.py'))}


def write_new(path, data):
    with path.open('x', encoding='utf8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def freeze():
    files = [SOURCE / f'CANDIDATE-{i:02d}.json' for i in range(11, 21)]
    if not all(p.is_file() for p in files):
        raise ValueError('A preregistered source is missing')
    OUT.mkdir(parents=True, exist_ok=False, mode=0o700)
    protocol = {
        'format': 'ac2-scope-v2-prospective-freeze-v1',
        'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
        'selection': 'All ten CANDIDATE-11 through CANDIDATE-20 from the existing source-only candidate_test directory, sorted by ID; no selection by generated question, flag or outcome.',
        'selection_limits': 'Synthetic source candidates, not certified novel or randomly sampled; their README explicitly notes only ten histories and recommends further independent scenarios. They were not among the 30 source histories used in the v2 development evaluation, but prior exposure cannot be ruled out.',
        'source_sha256': {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in files},
        'guard_sha256': digest(GUARD.read_bytes()),
        'runner_sha256': digest(Path(__file__).read_bytes()),
        'application_sha256': runtime_hashes(),
        'settings': {'generator': 'current saved rule-based v36', 'extractor': 'rule-based',
                     'test_budget_per_history': 4, 'model_called': False,
                     'source_memories': 'automatically extracted, provisionally supplied; both reviewers must check them against source',
                     'relationship_metadata': 'automatically extracted relationship types, not human gold'},
        'review': 'Two distinct human reviewers independently judge each generated prompt and expected behavior against source. Reviewers see neither guard flags nor one another\'s labels. AI assistance and prior exposure must be recorded honestly.',
        'metrics': 'On source-valid items with two reviewer-agreed structural verdicts, report flagged invalid / all invalid, flagged valid / all valid, denominators and uncertainty/disagreement separately. Record missing generated slots and source-invalid or unresolved cases. No target threshold or hypothesis is set.',
        'stopping_rule': 'All ten sources and all generated questions; no cherry-picking. Do not revise v2 using these outcomes and then call the same set held out.',
    }
    write_new(OUT/'protocol.json', protocol)
    print('Frozen 10 source histories and current code; no questions or flags generated.')


def prepare():
    from app.extraction.rule_based import RuleBasedMemoryExtractor
    from app.schemas import AuditRun, Conversation
    from app.test_generator.rule_based import RuleBasedTestGenerator
    protocol = json.loads((OUT/'protocol.json').read_bytes())
    if (protocol['runner_sha256'] != digest(Path(__file__).read_bytes())
            or protocol['guard_sha256'] != digest(GUARD.read_bytes())
            or protocol['application_sha256'] != runtime_hashes()
            or any(digest((ROOT/p).read_bytes()) != h for p,h in protocol['source_sha256'].items())):
        raise ValueError('Frozen input or source code changed')
    spec = importlib.util.spec_from_file_location('guard_v2_frozen', GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    questions, histories, identity, ledger = [], [], {}, []
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    for relative in protocol['source_sha256']:
        path = ROOT/relative
        source = json.loads(path.read_bytes())
        hid = path.stem
        conversation = Conversation(conversation_id=hid, created_at=now, authorised=True,
                                    source_origin='synthetic', messages=source['messages'])
        memories = RuleBasedMemoryExtractor().extract(conversation)
        for memory in memories:
            memory.status = 'confirmed'  # provisional research fixture, not a human confirmation
        run = AuditRun(run_id=hid, conversation_id=hid, status='CREATED', target_configuration='weak',
                       provider='rule_based', model='local', temperature=0, random_seed=42,
                       test_budget=4, prompt_template_version='rule-based-v36', created_at=now)
        suite = RuleBasedTestGenerator().generate(memories, run)
        if RuleBasedTestGenerator.VERSION != 'rule-based-v36':
            raise ValueError('Unexpected generator version')
        history = {'history_id': hid, 'source_messages': source['messages'],
                   'provisional_memories': [m.model_dump(mode='json') for m in memories]}
        histories.append(history)
        reltypes = [r.type.value for m in memories for r in m.relationships]
        for test in suite:
            blind_id = secrets.token_hex(16)
            if blind_id in identity:
                raise ValueError('Random identity collision')
            q = {'blind_id': blind_id, 'history_id': hid, 'prompt': test.prompt,
                 'expected_behavior': test.expected_behavior, 'supporting_memory_ids': test.supporting_memory_ids}
            questions.append(q)
            identity[blind_id] = {'flag': module.issue(test.prompt, [m['content'] for m in source['messages']], reltypes),
                                  'history_id': hid, 'dimension': test.dimension.value}
        ledger.append({'history_id': hid, 'generated': len(suite), 'scheduled': 4, 'missing': 4-len(suite),
                       'provisional_extracted_memories': len(memories), 'provisional_relationships': len(reltypes)})
    secrets.SystemRandom().shuffle(questions)
    material = {'format': 'ac2-scope-v2-blind-material-v1', 'histories': histories, 'questions': questions}
    material_sha = digest(canonical(material))
    reviewer_dir = OUT/'human-review'
    reviewer_dir.mkdir(exist_ok=False, mode=0o700)
    for slot in (1, 2):
        packet = {'format': 'ac2-scope-v2-human-review-v1', 'reviewer_slot': slot, 'material_sha256': material_sha,
                  'reviewer_declaration': {'reviewer_label': None, 'completed_by_human': None,
                    'completed_independently': None, 'seen_other_review': None, 'seen_guard_flags': None,
                    'used_ai_assistance': None, 'prior_exposure_to_sources': None},
                  **{k: material[k] for k in ('histories', 'questions')},
                  'decisions': [{'blind_id': q['blind_id'], 'grounded': None, 'structurally_executable': None,
                                 'reason': ''} for q in questions]}
        write_new(reviewer_dir/f'reviewer-{slot}.json', packet)
    private = OUT/'private'
    private.mkdir(exist_ok=False, mode=0o700)
    write_new(private/'material.json', material)
    write_new(private/'key.json', {'format': 'ac2-scope-v2-private-key-v1', 'material_sha256': material_sha,
                                  'protocol_sha256': digest((OUT/'protocol.json').read_bytes()),
                                  'identity': identity, 'ledger': ledger})
    print(json.dumps({'histories': len(histories), 'scheduled': 40, 'generated': len(questions),
                      'missing': sum(x['missing'] for x in ledger), 'human_labels_created': False}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['freeze', 'prepare'])
    args = parser.parse_args()
    {'freeze': freeze, 'prepare': prepare}[args.stage]()
