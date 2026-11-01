"""Reconcile two blinded AI judgments without manufacturing human labels."""
from collections import Counter
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'output/proposal-delivery/bc-reader-retest-20261101-v2'


def read(path):
    return json.loads(path.read_text())


def main(review_root='review'):
    items = {}
    sources = {}
    batches = []
    for pack in sorted((BASE/'C/compact-review').glob('batch-*.json')):
        if '.private-key.' in pack.name:
            continue
        name = pack.stem
        reviews = [BASE/f'{review_root}/reviewer-{n}/C-{name}.review.json' for n in (1, 2)]
        if not all(p.exists() for p in reviews):
            continue
        material = read(pack)
        judges = [read(p) for p in reviews]
        key = read(pack.with_name(name+'.private-key.json'))['mapping']
        private = {v['review_id']: v for v in key}
        expected = set(private)
        answer_maps = [{v['review_id']: v for v in j['items']} for j in judges]
        source_maps = [{v['source_handle']: v for v in j['sources']} for j in judges]
        if any(set(m) != expected or len(m) != len(j['items']) for m, j in zip(answer_maps, judges)):
            raise ValueError('Review handles differ from frozen batch')
        source_ids = {s['source_handle'] for s in material['sources']}
        if any(set(m) != source_ids for m in source_maps):
            raise ValueError('Source review handles differ from frozen batch')
        case_by_question = {s['question']: s['question_id'] for s in read(BASE/'C/selected-source.json')}
        for s in material['sources']:
            handle = s['source_handle']
            source_labels = [m[handle] for m in source_maps]
            source_row = {'study': 'C', 'case_id': case_by_question.get(s['question']), 'source_handle': handle,
                'reviewer_judgments': [{k: r.get(k) for k in ('question_validity', 'reference_validity', 'review_reason')} for r in source_labels],
                'accepted_by_both_ai': all(r.get('question_validity') == 'valid' and r.get('reference_validity') == 'valid' for r in source_labels)}
            if handle not in sources:
                sources[handle] = source_row
            elif [(r['question_validity'], r['reference_validity']) for r in sources[handle]['reviewer_judgments']] != [(r['question_validity'], r['reference_validity']) for r in source_row['reviewer_judgments']]:
                sources[handle]['accepted_by_both_ai'] = False
                sources[handle].setdefault('later_assessment_changes', []).append(source_row['reviewer_judgments'])
        for rid in sorted(expected):
            a, b = (m[rid] for m in answer_maps)
            handle = a['source_handle']
            if b['source_handle'] != handle:
                raise ValueError('Reviewer source bindings differ')
            source_labels = [m[handle] for m in source_maps]
            supported = sources[handle]['accepted_by_both_ai']
            answer_labels = [a.get('answer_verdict'), b.get('answer_verdict')]
            if any(v not in ('pass', 'fail', 'uncertain') for v in answer_labels):
                raise ValueError('Unsupported answer label')
            consensus = answer_labels[0] if supported and answer_labels[0] == answer_labels[1] else 'uncertain'
            row = {'review_id': rid, 'study': 'C', 'case_id': private[rid]['case_id'], 'source_handle': handle,
                'strategy': private[rid]['strategy'], 'repeat': private[rid]['repeat'],
                'verdict': consensus, 'answer_judgments': answer_labels,
                'source_validity_confirmed_by_both_ai': supported,
                'reasons': [a.get('review_reason'), b.get('review_reason')],
                'behavior_quality': [a.get('behavior_quality'), b.get('behavior_quality')]}
            if rid in items:
                raise ValueError('Answer duplicated across incremental review batches')
            items[rid] = row
        batches.append({'pack': str(pack.relative_to(ROOT)), 'pack_sha256': hashlib.sha256(pack.read_bytes()).hexdigest(),
            'reviews': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in reviews}})
    for pack in sorted((BASE/'B/blind-review').glob('compact-batch-*.json')):
        number = pack.stem.removeprefix('compact-batch-')
        reviews = [BASE/f'{review_root}/reviewer-{n}/B-batch-{number}.review.json' for n in (1, 2)]
        if not all(p.exists() for p in reviews):
            continue
        material = read(pack); judges = [read(p) for p in reviews]
        key = read(BASE/f'B/private-review-batches/compact-batch-{number}.private-key.json')
        if key['public_sha256'] != hashlib.sha256(pack.read_bytes()).hexdigest():
            raise ValueError('B private key differs from frozen review pack')
        private = {v['review_id']: v for v in key['mapping']}
        amap = [{v['review_id']: v for v in j['items']} for j in judges]
        qmap = [{v['question_id']: v for v in j['questions']} for j in judges]
        if any(set(m) != set(private) or len(m) != len(j['items']) for m, j in zip(amap, judges)):
            raise ValueError('B review answer handles differ')
        qids = {q['question_id'] for q in material['questions']}
        dimensions = {q['question_id']: q['dimension'] for q in material['questions']}
        if any(set(m) != qids for m in qmap):
            raise ValueError('B question review handles differ')
        for qid in qids:
            handle = 'B-'+qid
            labels = [m[qid] for m in qmap]
            source_row = {'study': 'B', 'question_id': qid, 'source_handle': handle,
                'reviewer_judgments': [{k: q.get(k) for k in ('question_validity', 'reference_validity', 'reason')} for q in labels],
                'accepted_by_both_ai': all(q.get('question_validity') == 'valid' and q.get('reference_validity') == 'valid' for q in labels)}
            if handle not in sources:
                sources[handle] = source_row
            elif [(q['question_validity'], q['reference_validity']) for q in sources[handle]['reviewer_judgments']] != [(q['question_validity'], q['reference_validity']) for q in source_row['reviewer_judgments']]:
                sources[handle]['accepted_by_both_ai'] = False
                sources[handle].setdefault('later_assessment_changes', []).append(source_row['reviewer_judgments'])
        for rid, mapping in private.items():
            a, b = (m[rid] for m in amap)
            if a['question_id'] != b['question_id']:
                raise ValueError('B answer question binding differs')
            handle = 'B-'+a['question_id']
            labels = [a['strict_answer_verdict'], b['strict_answer_verdict']]
            if any(v not in ('pass', 'fail', 'uncertain') for v in labels):
                raise ValueError('Invalid B verdict')
            supported = sources[handle]['accepted_by_both_ai']
            row = {'review_id': rid, 'study': 'B', 'history_id': mapping['history_id'],
                'case_id': a['question_id'], 'dimension': dimensions[a['question_id']], 'source_handle': handle, 'strategy': mapping['strategy'],
                'repeat': mapping['repetition'], 'verdict': labels[0] if supported and labels[0] == labels[1] else 'uncertain',
                'answer_judgments': labels, 'source_validity_confirmed_by_both_ai': supported,
                'reasons': [a.get('reason'), b.get('reason')],
                'safe_but_incomplete': [a.get('safe_but_incomplete'), b.get('safe_but_incomplete')]}
            if rid in items:
                raise ValueError('Duplicate reviewed B answer')
            items[rid] = row
        batches.append({'pack': str(pack.relative_to(ROOT)), 'pack_sha256': hashlib.sha256(pack.read_bytes()).hexdigest(),
            'reviews': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in reviews}})
    for row in items.values():
        if not sources[row['source_handle']]['accepted_by_both_ai']:
            row['source_validity_confirmed_by_both_ai'] = False
            row['verdict'] = 'uncertain'
    result = {'format': 'bc-independent-ai-consensus-v2', 'created_at': datetime.now(timezone.utc).isoformat(),
        'review_model': 'gpt-6-astra', 'review_reasoning_effort': 'max' if review_root == 'review-max' else 'high',
        'completed_by_human': False, 'human_confirmation_pending': True, 'batches': batches,
        'counts': dict(Counter(v['verdict'] for v in items.values())), 'sources': list(sources.values()), 'items': list(items.values()),
        'rule': 'Question and reference must be accepted by both AI reviewers; otherwise unresolved. Answer disagreements remain unresolved. No gold or labels changed.'}
    path = BASE/'review/consensus.json'; path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.json.tmp'); temp.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n'); temp.replace(path)
    print(json.dumps({'reviewed': len(items), 'primary': result['counts'], 'question_sources': len(sources)}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-root', choices=['review','review-max'], default='review')
    args=parser.parse_args()
    main(args.review_root)
