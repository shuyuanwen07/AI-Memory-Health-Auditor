"""Evidence-integrity checks only: all declarations below are synthetic fixtures."""
import copy
import json
import unittest
from scripts.prepare_ac3_retest_review_intake import PACKET, inspect


def synthetic_documents():
    source = (PACKET / 'candidate-inputs.json').read_bytes()
    plan = (PACKET / 'proposed-fact-plan.json').read_bytes()
    documents = []
    for slot in (1, 2):
        doc = json.loads((PACKET / f'reviewer-{slot}.json').read_text())
        doc['reviewer_declaration'].update(reviewer_label=f'SYNTHETIC-{slot}',
            completed_by_human=True, completed_independently=True, used_ai_assistance=False)
        for case in doc['cases']:
            for item in case['questions'] + case['relationships']:
                item['review']['validity'] = 'valid'
            for item in case['facts']:
                item['review']['support'] = 'valid'
        documents.append(doc)
    return source, plan, documents


def run(source, plan, documents):
    return inspect(source, plan, [json.dumps(doc).encode() for doc in documents])


def test_synthetic_complete_and_disagreement():
    source, plan, docs = synthetic_documents()
    result = run(source, plan, docs)
    assert result['all_items_valid_in_both_reviews']
    assert not result['run_authorized'] and not result['database_written']
    assert not result['existing_fact_validator_projection']['fact_plan_validation']['database_snapshot_checked']
    docs[0]['cases'][0]['questions'][0]['review'].update(validity='uncertain', note='Synthetic test reason')
    result = run(source, plan, docs)
    assert not result['all_items_valid_in_both_reviews'] and len(result['unresolved']) == 1


def reject_tampering_or_unsubstantiated_declaration(change):
    source, plan, docs = synthetic_documents()
    docs = copy.deepcopy(docs)
    if change == 'source':
        docs[0]['cases'][0]['source_messages'][0]['text'] += ' changed'
    elif change == 'declaration':
        docs[0]['reviewer_declaration']['completed_independently'] = None
    elif change == 'identity':
        docs[1]['reviewer_declaration']['reviewer_label'] = docs[0]['reviewer_declaration']['reviewer_label']
    elif change == 'question':
        docs[0]['cases'][0]['questions'][0]['test']['question'] += ' changed'
    else:
        docs[0]['cases'][0]['facts'].pop()
    try:
        run(source, plan, docs)
    except ValueError:
        return
    raise AssertionError(f"Failed to reject {change}")


class IntakeTests(unittest.TestCase):
    def test_valid_and_uncertain(self):
        test_synthetic_complete_and_disagreement()

    def test_integrity_gates(self):
        for change in ('source', 'declaration', 'identity', 'question', 'missing_item'):
            with self.subTest(change=change):
                reject_tampering_or_unsubstantiated_declaration(change)
