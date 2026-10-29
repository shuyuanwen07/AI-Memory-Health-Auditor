"""Aggregate the received human reviews for the saved tutor repair example.

This is a retrospective descriptive comparison, not a blind, held-out estimate.
No reviewer decisions or saved automated scores are changed.
"""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECONCILIATION = ROOT / 'output/proposal-delivery/reconciliation-user-2026-10-28.json'
CONFIRMATION = ROOT / 'output/proposal-delivery/human-review-user-confirmation-2026-10-28.json'
DISTINCT = ROOT / 'output/proposal-delivery/human-review-distinct-reviewers-confirmation-2026-10-28.json'
INDEPENDENCE = ROOT / 'output/proposal-delivery/human-review-independence-user-confirmation-2026-10-28.json'
PACKET = ROOT / 'output/proposal-delivery/live-current-source-repair-2026-10-28/human-review'
BUNDLE = PACKET.parent / 'experiment.bundle.json'
OUTPUT = ROOT / 'output/proposal-delivery/tutor-repair-human-review-summary-2026-10-28-v2.json'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    reconciliation = json.loads(RECONCILIATION.read_text())
    confirmation = json.loads(CONFIRMATION.read_text())
    distinct, independence = (json.loads(p.read_text()) for p in (DISTINCT, INDEPENDENCE))
    manifest = json.loads((PACKET / 'packet-manifest.json').read_text())
    key_path = PACKET / 'review-key-private.json'
    key = json.loads(key_path.read_text())
    if confirmation['reconciliation_sha256'] != digest(RECONCILIATION):
        raise ValueError('User confirmation does not bind to the reconciliation.')
    if distinct['earlier_confirmation_sha256'] != digest(CONFIRMATION) or independence['prior_confirmation_sha256'] != digest(DISTINCT):
        raise ValueError('Later user confirmations do not bind to the earlier ones.')
    expected_returns = [reconciliation['source_integrity']['reviewer_a_return_source_sha256'], reconciliation['source_integrity']['reviewer_b_return_source_sha256']]
    if any(item['applies_to_return_sha256'] != expected_returns for item in (confirmation, distinct, independence)):
        raise ValueError('The confirmation files do not bind to both reviewer returns.')
    if digest(key_path) != manifest['files']['review-key-private.json'] or digest(BUNDLE) != key['bundle_sha256']:
        raise ValueError('Saved review key or source bundle does not match its frozen hash.')
    if key['experiment_id'] != manifest['experiment_id'] or len(key['rows']) != 24:
        raise ValueError('Review key identifies a different experiment or row count.')
    mapping = {row['review_id']: row for row in key['rows']}
    if len(mapping) != 24:
        raise ValueError('Duplicate blinded review identifiers.')
    items = [row for row in reconciliation['items'] if row['queue_id'] == 'current_source_repair_24']
    if len(items) != 24 or {row['item_id'] for row in items} != set(mapping):
        raise ValueError('Human judgments do not exactly match the frozen 24-answer packet.')
    counts: collections.Counter[tuple[str, str]] = collections.Counter()
    automatic: collections.Counter[tuple[str, str]] = collections.Counter()
    questions: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for row in items:
        judgments = {entry['field']: entry for entry in row['primary_judgments']}
        if set(judgments) != {'question_validity', 'answer_verdict'} or any(entry['comparison'] != 'agreed' for entry in judgments.values()):
            raise ValueError('Do not collapse disagreement or uncertainty into a reviewer consensus.')
        if judgments['question_validity']['reviewer_slot_1']['value'] != 'valid':
            raise ValueError('This descriptive comparison requires each question to be reviewed as valid.')
        verdict = judgments['answer_verdict']['reviewer_slot_1']['value']
        if verdict not in {'Pass', 'Fail'}:
            raise ValueError('Unexpected reviewed answer verdict.')
        identity = mapping[row['item_id']]
        condition = identity['condition']
        subject = row['identity_fields']['subject']
        if condition in questions[subject]:
            raise ValueError('Duplicate condition for a question.')
        questions[subject][condition] = verdict
        counts[condition, verdict] += 1
        automatic[identity['automatic_label'], verdict] += 1
    conditions = ['Original configuration', 'Generic instruction control', 'Retrieval strategy candidate']
    if len(questions) != 8 or any(set(answers) != set(conditions) for answers in questions.values()):
        raise ValueError('The comparison is not paired across all eight questions.')
    matched = collections.Counter((answers[conditions[0]], answers[conditions[2]]) for answers in questions.values())
    data = {
        'format': 'tutor-repair-human-review-summary-v1',
        'experiment_id': key['experiment_id'],
        'scope': 'One synthetic history, one run per condition and eight shared questions. User reports two independent human reviewers who had not seen automatic results; the original files record conflicting provenance and AI assistance. Neither account has been independently authenticated.',
        'human_confirmation': 'User confirmed two different people performed independent human reviews without seeing automatic scores before review; the original files state AI assistance and result exposure. Both records are preserved without independently resolving the conflict.',
        'agreement': {'question_validity': '24/24', 'answer_verdict': '24/24', 'note': 'Agreement is not formal adjudication.'},
        'conditions': [{'name': c, 'pass': counts[c, 'Pass'], 'fail': counts[c, 'Fail'], 'total': sum(counts[c, v] for v in ('Pass', 'Fail'))} for c in conditions],
        'paired_original_to_target': {'both_pass': matched['Pass', 'Pass'], 'target_only_pass': matched['Fail', 'Pass'], 'original_only_pass': matched['Pass', 'Fail'], 'both_fail': matched['Fail', 'Fail']},
        'automatic_vs_human': {'decided_agree': automatic['pass', 'Pass'] + automatic['fail', 'Fail'], 'decided_disagree': automatic['pass', 'Fail'] + automatic['fail', 'Pass'], 'automatic_uncertain_human_pass': automatic['uncertain', 'Pass'], 'automatic_uncertain_human_fail': automatic['uncertain', 'Fail']},
        'source_sha256': {'reconciliation': digest(RECONCILIATION), 'confirmation': digest(CONFIRMATION), 'distinct_people_confirmation': digest(DISTINCT), 'independence_confirmation': digest(INDEPENDENCE), 'key': digest(key_path), 'bundle': digest(BUNDLE)},
    }
    if OUTPUT.exists():
        raise FileExistsError('Refusing to overwrite existing analysis.')
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(data, ensure_ascii=False))


if __name__ == '__main__':
    main()
