"""Synthetic reviewed-fact declarations for tests; not real human review."""
import copy
import hashlib
import json
import pytest
from scripts.ac3_reviewed_fact_map import validate_fact_plan

@pytest.fixture
def fixture():
    messages = [
        {'message_id': 'H-M1', 'text': 'A marker is copper.'},
        {'message_id': 'H-M2', 'text': 'The prior location is east.'},
        {'message_id': 'H-M3', 'text': 'The new location is west.'},
        {'message_id': 'H-M4', 'text': 'The plan is greenhouse. The booking is courtyard.'},
        {'message_id': 'H-M5', 'text': 'Generally paper. For Cedar encrypted.'}]
    suite = {'cases': [{'history_id': 'H', 'source_messages': messages, 'tests': [
        {'dimension': 'freshness', 'supporting_source_message_ids': ['H-M2', 'H-M3']},
        {'dimension': 'conflict_resolution', 'supporting_source_message_ids': ['H-M4']},
        {'dimension': 'appropriate_use', 'supporting_source_message_ids': ['H-M5']},
    ]}]}
    facts = [{'memory_id': f'F{i}', 'source_message_id': source, 'source_span': span, 'canonical_value': span} for i, (source, span) in enumerate([
        ('H-M1', 'A marker is copper.'), ('H-M2', 'The prior location is east.'), ('H-M3', 'The new location is west.'),
        ('H-M4', 'The plan is greenhouse.'), ('H-M4', 'The booking is courtyard.'),
        ('H-M5', 'Generally paper.'), ('H-M5', 'For Cedar encrypted.')])]
    # Synthetic human-reviewed context expansion: the canonical value need not
    # be a substring, but both reviewers must approve the exact plan.
    facts[4]['canonical_value'] = 'The Cedar event booking is courtyard.'
    facts[6]['canonical_value'] = 'For the Cedar project, use encrypted records.'
    edges = [
        {'memory_id': 'F2', 'target_memory_id': 'F1', 'relationship_type': 'UPDATE', 'evidence_message_ids': ['H-M3']},
        {'memory_id': 'F3', 'target_memory_id': 'F4', 'relationship_type': 'CONFLICT', 'evidence_message_ids': ['H-M4']},
        {'memory_id': 'F6', 'target_memory_id': 'F5', 'relationship_type': 'CONTEXTUAL_OVERRIDE', 'evidence_message_ids': ['H-M5']}]
    plan = {'histories': {'H': {'facts': facts, 'relationships': edges}}}
    sha = hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    reviews = [{'reviewer_label': f'test-{i}', 'completed_by_human': True, 'completed_independently': True,
                'reviewed_fact_and_relation_semantics': True, 'fact_plan_sha256': sha} for i in (1, 2)]
    snapshot = {'histories': {'H': {'memories': [{'memory_id': f['memory_id'], 'canonical_value': f['canonical_value'],
        'status': 'confirmed', 'source_message_ids': [f['source_message_id']]} for f in facts], 'relationships': copy.deepcopy(edges)}}}
    return suite, plan, reviews, snapshot


def test_reviewed_distinct_compound_facts_are_representable(fixture):
    result = validate_fact_plan(*fixture)
    assert result['history_count'] == 1 and result['execution_authorized'] is False


def test_unreviewed_or_changed_plan_is_rejected(fixture):
    suite, plan, reviews, snapshot = fixture
    reviews[0]['completed_by_human'] = False
    with pytest.raises(ValueError, match='Human review'): validate_fact_plan(suite, plan, reviews, snapshot)
    reviews[0]['completed_by_human'] = True
    plan['histories']['H']['facts'][0]['source_span'] = 'wrong'
    with pytest.raises(ValueError, match='Human review'): validate_fact_plan(suite, plan, reviews, snapshot)


def test_saved_relations_and_fact_text_must_match_review(fixture):
    suite, plan, reviews, snapshot = fixture
    snapshot['histories']['H']['relationships'].pop()
    with pytest.raises(ValueError, match='relationships differ'): validate_fact_plan(suite, plan, reviews, snapshot)
    snapshot['histories']['H']['relationships'] = copy.deepcopy(plan['histories']['H']['relationships'])
    snapshot['histories']['H']['memories'][3]['canonical_value'] = 'incorrect'
    with pytest.raises(ValueError, match='memory content'): validate_fact_plan(suite, plan, reviews, snapshot)
