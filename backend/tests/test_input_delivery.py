from types import SimpleNamespace
import pytest
from app.services.input_delivery import input_delivery


def record(key, fact='Project uses SQLite', source='source1'):
    return SimpleNamespace(memory_id=key, canonical_value=fact, source_message_ids=[source])


def test_selected_support_missing_from_final_receipt_is_observable():
    fact = record('a')
    result = input_delivery([fact], [fact], ['a'], [], [])
    assert result['complete_retrieved_match'] is True
    assert result['selected_not_supplied_fact_units'] == 1


def test_unknown_receipt_is_not_an_empty_final_input():
    fact = record('a')
    result = input_delivery([fact], [fact], ['a'], None, [])
    assert result['selected_not_supplied_fact_units'] is None
    assert result['retrieved_fact_units'] == 1


def test_equivalent_exact_copy_removes_delivery_and_budget_gap():
    fact, copy = record('a'), record('b')
    result = input_delivery([fact], [fact, copy], ['a'], ['b'], [
        {'memory_id':'a', 'eligible':True, 'selected':False, 'reason':'profile_context_budget_excluded'}])
    assert result['selected_not_supplied_fact_units'] == 0
    assert result['context_budget_excluded_fact_units'] == 0


@pytest.mark.parametrize('entries', [
    [{'memory_id':'a', 'selected':False, 'reason':'profile_context_budget_excluded'}],
    [{'memory_id':'a', 'eligible':False, 'selected':False, 'reason':'profile_context_budget_excluded'}],
    [{'memory_id':'a', 'eligible':True, 'selected':True, 'reason':'profile_context_budget_excluded'}],
    [{'memory_id':'a', 'eligible':True, 'selected':False, 'reason':'profile_context_budget_excluded'}]*2,
])
def test_budget_attribution_requires_unambiguous_observed_eligible_exclusion(entries):
    fact = record('a')
    assert input_delivery([fact], [fact], [], [], entries)['context_budget_excluded_fact_units'] == 0


def test_unrelated_budget_exclusion_does_not_become_a_support_gap():
    fact, other = record('a'), record('b', 'Unrelated preference', 'source2')
    result = input_delivery([fact], [fact,other], [], [], [
        {'memory_id':'b','eligible':True,'selected':False,'reason':'profile_context_budget_excluded'}])
    assert result['context_budget_excluded_fact_units'] == 0


def test_partial_selection_does_not_claim_all_support_was_retrieved():
    fact, other = record('a'), record('b','Task requires Ruby','source2')
    result = input_delivery([fact,other], [fact,other], ['a'], [], [])
    assert result['complete_retrieved_match'] is False
    assert result['retrieved_fact_units'] == result['selected_not_supplied_fact_units'] == 1


def test_profile_filters_are_distinct_from_context_budgets():
    fact = record('a')
    result = input_delivery([fact], [fact], [], [], [
        {'memory_id':'a','eligible':True,'selected':False,'reason':'profile_excluded_other_project'}])
    assert result['profile_filter_excluded_fact_units'] == 1
    assert result['context_budget_excluded_fact_units'] == 0
