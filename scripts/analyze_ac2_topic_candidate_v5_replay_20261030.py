"""Offline paired generator replay on 30 previously observed histories.

This is not an API test, not an independent sample, and does not assess validity.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path
from app.schemas import AuditRun, Memory
from app.test_generator.conflict_aware import ConflictAwareRuleBasedTestGenerator
from scripts.ac2_topic_inference_candidate_v5_20261030 import TopicInferenceCandidateV5

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'output/proposal-delivery/ac2-v40-same-source-development-20261029-v1'
OUT = ROOT / 'output/proposal-delivery/ac2-topic-candidate-v5-paired-replay-20261030.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ledger_path, protocol_path = RUN / 'ledger.json', RUN / 'protocol.json'
    ledger, protocol = (json.loads(p.read_text()) for p in (ledger_path, protocol_path))
    assert ledger['protocol_sha256'] == sha(protocol_path)
    assert [h['history_id'] for h in ledger['histories']] == protocol['history_ids'] and len(ledger['histories']) == 30
    rows = []
    for h in ledger['histories']:
        memories = [Memory.model_validate(x) for x in h['simulated_confirmed_memories']]
        audit = AuditRun.model_validate(next(x['response'] for x in h['requests'] if x['path'] == '/audits'))
        arms = {}
        for label, cls in (('baseline', ConflictAwareRuleBasedTestGenerator), ('candidate', TopicInferenceCandidateV5)):
            generator = cls()
            tests = generator.generate([m.model_copy(deep=True) for m in memories], audit.model_copy(deep=True))
            arms[label] = {'questions': [{'dimension': t.dimension.value, 'prompt': t.prompt, 'expected_behavior': t.expected_behavior, 'supporting_memory_ids': t.supporting_memory_ids} for t in tests], 'rejected': generator.last_observation['rejected_candidate_count'], 'ambiguous_candidates_suppressed': getattr(generator, '_ambiguous_accuracy_count', 0), 'status': generator.last_observation['status']}
        rows.append({'history_id': h['history_id'], 'historical_api_status': h['status'], **arms})
    stats = {}
    for label in ('baseline', 'candidate'):
        tests = [q for r in rows for q in r[label]['questions']]
        stats[label] = {'histories_with_questions': sum(bool(r[label]['questions']) for r in rows), 'questions': len(tests), 'dimensions': dict(Counter(q['dimension'] for q in tests)), 'rejected_candidates': sum(r[label]['rejected'] for r in rows), 'ambiguous_candidates_suppressed': sum(r[label]['ambiguous_candidates_suppressed'] for r in rows)}
    exact = lambda q: (q['dimension'], q['prompt'], q['expected_behavior'], tuple(q['supporting_memory_ids']))
    for row in rows:
        old = {exact(q) for q in row['baseline']['questions']}; new = {exact(q) for q in row['candidate']['questions']}
        row['exact_pairs'] = len(old & new)
    output = {'ledger_sha256': sha(ledger_path), 'protocol_sha256': sha(protocol_path), 'candidate_sha256': sha(ROOT / 'scripts/ac2_topic_inference_candidate_v5_20261030.py'), 'v3_sha256': sha(ROOT / 'scripts/ac2_topic_inference_candidate_v3_20261030.py'), 'v2_sha256': sha(ROOT / 'scripts/ac2_topic_inference_candidate_v2_20261030.py'), 'parent_candidate_sha256': sha(ROOT / 'scripts/ac2_topic_inference_candidate_20261030.py'), 'statistics': stats, 'exact_pairs': sum(r['exact_pairs'] for r in rows), 'histories': rows, 'limitations': 'Post-outcome offline replay, current generator implementation on saved confirmed-memory snapshots; not the historical API or a live product-flow retest. Original run included additional API gates. Related synthetic histories were used in development and do not establish validity, statistical generalisation or live performance.'}
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'statistics': stats, 'exact_pairs': output['exact_pairs']}, indent=2))


if __name__ == '__main__':
    main()
