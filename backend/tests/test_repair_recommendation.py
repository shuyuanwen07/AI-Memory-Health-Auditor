"""Engineering decision boundaries, not a semantic gold diagnosis inventory."""
import pytest
from app.schemas.target_profile import TargetMemoryProfile
from app.services.repair_recommendation import recommend_repair


BASE = TargetMemoryProfile(label='Reviewed original', version=7, max_retrieved_records=3,
    context_character_budget=700, additional_instructions='Preserve customer boundaries.')


def recommend(cases, strategy='weak_first_hit', capacity=2, configurable=True):
    return recommend_repair(cases, BASE, strategy, capacity, 9, configurable=configurable)


@pytest.mark.parametrize('layer,verdict', [
    ('uncertain_assessment', None), ('unobserved', False), ('unobserved_pass', True),
    ('unattributed_pass', True), ('encoding_hypothesis', False), ('fact_correspondence_review', False),
    ('availability_review', False), ('policy_exclusion_hypothesis', False),
    ('fact_supply_review', False), ('generation_hypothesis', False),
    ('input_delivery_review', False), ('context_budget_review', False), ('profile_filter_review', False),
    ('retention_hypothesis', None), ('retrieval_hypothesis', True),
])
def test_review_only_evidence_preserves_original_configuration(layer, verdict):
    result = recommend([{'layer': layer, 'automated_passed': verdict}])
    assert result['profile'] == BASE
    assert result['strategy'] == 'weak_first_hit'
    assert result['capacity'] == 2
    assert result['recommendation']['status'] == 'requires_review'


def test_retention_candidate_preserves_retrieval_and_existing_instructions():
    result = recommend([{'layer': 'retention_hypothesis', 'automated_passed': False},
                        {'layer': 'retrieval_hypothesis', 'automated_passed': False}])
    assert result['capacity'] == 9
    assert result['strategy'] == 'weak_first_hit'
    assert result['profile'].model_dump(exclude={'label', 'version'}) == BASE.model_dump(exclude={'label', 'version'})
    assert result['recommendation']['focus'] == 'retention_capacity'


def test_retrieval_candidate_does_not_overwrite_instructions_or_capacity():
    result = recommend([{'layer': 'retrieval_hypothesis', 'automated_passed': False}])
    assert result['strategy'] == 'scope_aware'
    assert result['capacity'] == 2
    assert result['profile'].model_dump(exclude={'label', 'version'}) == BASE.model_dump(exclude={'label', 'version'})
    assert result['recommendation']['status'] == 'exploratory_candidate'


@pytest.mark.parametrize('cases,strategy,capacity,configurable', [
    ([], 'weak_first_hit', 2, True),
    ([{'layer': 'retrieval_hypothesis', 'automated_passed': False}], 'scope_aware', 2, True),
    ([{'layer': 'retention_hypothesis', 'automated_passed': False}], 'weak_first_hit', 500, True),
    ([{'layer': 'retrieval_hypothesis', 'automated_passed': False}], 'weak_first_hit', 2, False),
])
def test_absent_gap_noop_limits_and_external_target_do_not_suggest_a_change(cases, strategy, capacity, configurable):
    result = recommend(cases, strategy=strategy, capacity=capacity, configurable=configurable)
    assert result['profile'] == BASE
    assert result['strategy'] == strategy
    assert result['capacity'] == capacity
    assert result['recommendation']['status'] == ('requires_review' if cases else 'no_detected_gap')


def test_no_memory_reference_preserves_deliberate_ablation():
    result = recommend([{'layer':'no_memory_reference','automated_passed':False}],strategy='no_memory')
    assert result['strategy'] == 'no_memory'
    assert result['profile'] == BASE
    assert result['capacity'] == 2
    assert result['recommendation']['status'] == 'baseline_reference'

def test_no_memory_reference_does_not_hide_unobserved_failures():
    result = recommend([{'layer':'no_memory_reference','automated_passed':False},
                        {'layer':'unobserved','automated_passed':False}],strategy='no_memory')
    assert result['recommendation']['status'] == 'requires_review'
    assert result['strategy'] == 'no_memory'
