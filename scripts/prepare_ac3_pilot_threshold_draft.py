"""Compute four proposal metrics on the reviewed tutor development example.

Only this saved development source and its human reviews are read. No new
held-out answer or score is read, generated or relabeled. Draft thresholds are
not a frozen protocol and do not establish AC3 acceptance.
"""
import collections
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'output/proposal-delivery/live-current-source-repair-2026-10-28'
BUNDLE = DIR / 'experiment.bundle.json'
KEY = DIR / 'human-review/review-key-private.json'
REVIEW = ROOT / 'output/proposal-delivery/reconciliation-user-2026-10-28.json'
DEST = ROOT / 'output/proposal-delivery/ac3-pilot-threshold-draft-2026-10-28-v2.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    review, key = json.loads(REVIEW.read_text()), json.loads(KEY.read_text())
    manifest = json.loads((KEY.parent / 'packet-manifest.json').read_text())
    if sha(KEY) != manifest['files']['review-key-private.json'] or sha(BUNDLE) != key['bundle_sha256']:
        raise ValueError('Development experiment or private key is not the frozen source.')
    rows = {r['item_id']: r for r in review['items'] if r['queue_id'] == 'current_source_repair_24'}
    key_rows = {r['review_id']: r for r in key['rows']}
    if len(rows) != 24 or set(rows) != set(key_rows):
        raise ValueError('Unexpected development reference set.')
    matrix = collections.Counter()
    classifications = collections.Counter()
    validity = {}
    for item_id, row in rows.items():
        fields = row['actual_review_fields']
        a, b = fields['reviewer_slot_1'], fields['reviewer_slot_2']
        if a['question_validity'] != b['question_validity'] or a['answer_verdict'] != b['answer_verdict']:
            raise ValueError('Disputed human labels cannot silently become a gold reference.')
        subject = row['identity_fields']['subject']
        if subject in validity and validity[subject] != a['question_validity']:
            raise ValueError('Question validity differs across repeats.')
        validity[subject] = a['question_validity']
        automated = key_rows[item_id]
        outcome = automated['automatic_label']
        reference = a['answer_verdict'].lower()
        if outcome not in {'pass', 'fail', 'uncertain'} or reference not in {'pass', 'fail'}:
            raise ValueError('Unexpected development verdict.')
        matrix[outcome, reference] += 1
        if outcome == 'fail' and reference == 'fail':
            if not a['failure_type'] or a['failure_type'] != b['failure_type']:
                raise ValueError('Missing or disputed human failure category.')
            classifications['matched'] += automated['automatic_failure_type'] == a['failure_type']
            classifications['total'] += 1
    if len(validity) != 8:
        raise ValueError('Expected 8 unique development questions.')
    total = sum(matrix.values()); truth_fail = sum(matrix[x, 'fail'] for x in ('pass', 'fail', 'uncertain')); truth_pass = sum(matrix[x, 'pass'] for x in ('pass', 'fail', 'uncertain'))
    valid_count = sum(v == 'valid' for v in validity.values())
    data = {
        'format': 'ac3-pilot-threshold-draft-v1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'DRAFT NOT FROZEN; not held-out evaluation',
        'pilot': {'source': 'One synthetic development history, three conditions, eight repeated questions; 24 retrospective answers.', 'total_answers': total, 'unique_questions': len(validity), 'human_failure_count': truth_fail, 'human_pass_count': truth_pass, 'automatic_abstentions': sum(matrix['uncertain', x] for x in ('pass', 'fail')), 'confusion': {f'{a}_vs_human_{b}': matrix[a,b] for a in ('pass','fail','uncertain') for b in ('pass','fail')}},
        'metrics': {
            'failure_detection_recall': {'numerator': matrix['fail', 'fail'], 'denominator': truth_fail, 'value': matrix['fail', 'fail']/truth_fail, 'definition': 'Human failures detected automatically; automatic uncertain is included as not detected.'},
            'failure_classification_accuracy': {'numerator': classifications['matched'], 'denominator': classifications['total'], 'value': classifications['matched']/classifications['total'], 'definition': 'Matched category among automatic true-positive failures with two agreeing human categories; report joint coverage separately.'},
            'test_validity': {'numerator': valid_count, 'denominator': len(validity), 'value': valid_count/len(validity), 'definition': 'Unique questions agreed valid by both reviewers; repeated responses do not add questions.'},
            'false_positive_rate': {'numerator': matrix['fail', 'pass'], 'denominator': matrix['fail', 'pass'] + matrix['pass', 'pass'], 'value': matrix['fail', 'pass']/(matrix['fail', 'pass'] + matrix['pass', 'pass']), 'definition': 'False automatic failures over human passes with a decided automated outcome. Separately report the human-pass abstention count and the total human-pass denominator.'},
        },
        'proposed_thresholds': {'failure_detection_recall_min': 0.75, 'failure_classification_accuracy_min': 0.80, 'test_validity_min': 0.90, 'false_positive_rate_max': 0.10},
        'rationale': 'Exploratory candidate thresholds anchored to this development example (recall 13/17, classification 11/13, validity 8/8, decided-only FPR 0/6 with one human-pass abstention), rounded to interpretable values. This small pilot does not provide reliable bounds; these values require team scrutiny, explicit versioning and prospective freeze before a held-out run. Do not alter them after examining held-out results.',
        'preconditions': ['Resolve contradictory provenance: user says two different people reviewed independently without seeing automated scores; original files state AI assistance and exposure. Preserve both records.', 'Confirm pilot labels, grounding and suitability; eight questions from one history are correlated and 0/6 decided-only FPR does not establish a low population FPR.', 'Finalize admissible decision coverage, sample-size requirements, uncertainty intervals, model and budget before held-out outputs; report uncertainty/abstentions explicitly.', 'Fix the future held-out source/test set and full protocol prior to target output. This draft does not authorize paid calls or freeze a model.'],
        'sources_sha256': {'bundle': sha(BUNDLE), 'key': sha(KEY), 'reconciliation': sha(REVIEW)},
    }
    if DEST.exists(): raise FileExistsError('Refusing to overwrite an existing pilot draft.')
    fd = os.open(DEST, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2); f.write('\n')
    print(json.dumps({'path': str(DEST), 'metrics': data['metrics'], 'proposed_thresholds': data['proposed_thresholds']}, ensure_ascii=False))


if __name__ == '__main__': main()
