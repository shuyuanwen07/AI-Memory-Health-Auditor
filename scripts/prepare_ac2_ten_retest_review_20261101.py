"""Create source-only independent review packets from a frozen ten-source run."""
import argparse
import copy
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(run_dir, review_dir):
    protocol = json.loads((run_dir / 'protocol.json').read_text())
    summary = json.loads((run_dir / 'summary.json').read_text())
    sources = json.loads((run_dir / 'source-selection.json').read_text())['conversations']
    expected = [f'prospective-{i:02d}' for i in range(1, 30, 3)]
    if protocol['history_ids'] != expected or [s['conversation_id'] for s in sources] != expected:
        raise ValueError('This packet must cover the exact original ten source histories')
    if [r['history_id'] for r in summary['runs']] != expected:
        raise ValueError('Missing or reordered scenario accounting')
    by_source = {s['conversation_id']: s for s in sources}
    histories = []
    for result in summary['runs']:
        path = run_dir / (result['history_id'] + '.json')
        if sha(path) != result['record_sha256']:
            raise ValueError('Run record changed after summary')
        run = json.loads(path.read_text())
        returned = [r for r in run['requests'] if r['status'] == 'returned']
        extraction = next((r['response'] for r in returned if r['path'].endswith('/extract')), [])
        current = [r['response'] for r in returned if r['method']=='GET' and r['path'].endswith('/tests')]
        tests = current[-1] if current else next((r['response'] for r in returned if r['path'].endswith('/generate-tests')), [])
        facts = [{'memory_id':m['memory_id'], 'canonical_value':m['canonical_value'],
                  'source_message_ids':m['source_message_ids'], 'fact_validity':'', 'note':''}
                 for m in extraction]
        relationships = [{'source_memory_id':m['memory_id'], 'type':rel['type'],
                          'target_memory_id':rel['target_memory_id'], 'relationship_validity':'', 'note':''}
                         for m in extraction for rel in m.get('relationships', [])]
        questions = [{'test_id':q['test_id'], 'dimension':q['dimension'], 'test_type':q['test_type'],
                      'question':q['prompt'], 'expected_behavior':q['expected_behavior'],
                      'supporting_memory_ids':q['supporting_memory_ids'],
                      'source_grounding':'', 'question_executability':'',
                      'reference_answer_validity':'', 'dimension_alignment':'', 'note':''} for q in tests]
        if len({q['test_id'] for q in questions}) != len(questions):
            raise ValueError('Duplicate question identity')
        histories.append({'history_id':result['history_id'], 'setting':by_source[result['history_id']]['setting'],
                          'source_messages':by_source[result['history_id']]['messages'],
                          'facts':facts, 'relationships':relationships, 'questions':questions,
                          'source_coverage_validity':'', 'source_coverage_note':''})
    review_dir.mkdir(parents=True, exist_ok=False)
    source_hashes = {str(p.relative_to(ROOT)):sha(p) for p in (run_dir/'protocol.json',run_dir/'summary.json',run_dir/'source-selection.json')}
    for n in (1, 2):
        packet = {'reviewer':f'astra-high-{n}', 'model':'gpt-6-astra', 'reasoning_effort':'high',
                  'completed_by_human':False, 'review_kind':'Independent AI source-based review; not human approval',
                  'instructions':'Read every source and every fact, edge and question. Also judge whether the extracted set covers the source statements, with source_coverage_validity and a concise note; partial coverage is not full coverage. Use valid/invalid/uncertain for every judgment. Judge source grounding, executable wording, reference validity and dimension alignment independently. Preserve unresolved same-period conflicts; do not infer a winner from observation order. Evaluate scoped instructions within their scope. Invalid or uncertain source evidence cannot be certified by agreement alone. No automatic scores or other reviewer judgments are supplied. Record quote/source IDs for concerns. Missing questions remain missing; never invent outputs.',
                  'histories':copy.deepcopy(histories)}
        rng = random.Random(20261110+n)
        rng.shuffle(packet['histories'])
        for history in packet['histories']:
            rng.shuffle(history['questions'])
        (review_dir/f'reviewer-{n}-blank.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2)+'\n')
    receipt = {'format':'ac2-original-ten-independent-review-v1', 'source_sha256':source_hashes,
               'histories':len(histories), 'planned_question_slots':40,
               'questions':sum(len(h['questions']) for h in histories),
               'facts':sum(len(h['facts']) for h in histories),
               'relationships':sum(len(h['relationships']) for h in histories),
               'automatic_scores_supplied':False, 'human_confirmation':'pending',
               'review_order_seeds':{'1':20261111,'2':20261112},
               'packet_preparer_sha256':sha(Path(__file__))}
    (review_dir/'protocol.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--review-dir',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(args.run_dir.resolve(),args.review_dir.resolve()),ensure_ascii=False))
