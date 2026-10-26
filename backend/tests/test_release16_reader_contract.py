"""Reader instruction contracts only; no model compliance or quality claims."""
import hashlib
import json

import pytest

from app.schemas import Dimension, TargetConfiguration, TestCase as Case
from app.target_ai.rule_based import (
    _EVIDENCE_CONTRACT,
    _FINAL_EVIDENCE_CHECK,
    memory_input_evidence,
    private_context_instruction,
    selected_memory_context,
)


def case(question, context=None):
    return Case(test_id='SYNTHETIC', run_id='OFFLINE', dimension=Dimension.ACCURACY,
                prompt=question, expected_behavior='EVALUATOR_SECRET_NEVER_SEND',
                supporting_memory_ids=['PRIVATE_GOLD_ID'], generator_version='synthetic-contract',
                target_memory_context=context or ['I am considering a visit to my cousin in a coastal town.'])


@pytest.mark.parametrize('configuration', list(TargetConfiguration))
def test_shared_confidence_contract_precedes_data_and_same_rule_closes_answer(configuration):
    instruction = private_context_instruction(case('Where is my relative associated?'), configuration)
    assert instruction.startswith('EVIDENCE AND CERTAINTY CONTRACT\n' + _EVIDENCE_CONTRACT)
    assert instruction.index('EVIDENCE AND CERTAINTY CONTRACT') < instruction.index('PRIVATE TARGET MEMORY CONTEXT')
    assert instruction.endswith(_FINAL_EVIDENCE_CHECK)
    assert 'lead, ledger and explanation must use the same confidence level' in instruction
    assert 'Keep conditional assumptions beside the claim' in instruction
    assert 'EVALUATOR_SECRET_NEVER_SEND' not in instruction
    assert 'PRIVATE_GOLD_ID' not in instruction


def test_personal_predicate_and_local_modality_do_not_upgrade_visit_to_residence():
    instruction = private_context_instruction(case('Where does my relative live?'), TargetConfiguration.STRONG)
    assert 'Plans and wishes do not establish completed actions' in instruction
    assert 'preserve independently stated relationships' in instruction
    assert 'association alone establishes neither current presence nor current or permanent residence' in instruction
    assert 'Report that association with its basis and limit' in instruction
    assert 'Attribution such as according to a message is not an uncertainty qualifier' in instruction
    assert 'storage scope' in instruction and 'not proof' in instruction
    assert 'Keep initial and later states separate' in instruction
    assert 'a later mention alone is not a state update' in instruction
    assert 'Describe gaps as supplied-record limits' in instruction


def test_count_requires_period_distinctness_participation_for_each_confirmed_member():
    instruction = private_context_instruction(case('How many gatherings did I attend this year?'), TargetConfiguration.STRONG)
    assert 'A confirmed subtotal requires every member' in instruction
    assert 'mutually distinct and within the requested period' in instruction
    assert 'Require attendance only when the question asks about attended events' in instruction
    assert 'member and any number including it inferred or conditional, never confirmed or a proven lower bound' in instruction
    assert 'Conditional numeric totals must also state any assumed distinctness' in instruction
    assert 'keep additional unresolved overlaps unquantified' in instruction
    assert 'A supported subtotal is not an exact overall total' in instruction
    assert 'Qualitative recency can support a labelled rough time inference, not confirmed calendar membership' in instruction
    assert 'APPROXIMATE TIME AND ORDER' not in instruction


def test_source_coverage_checks_actual_clauses_and_keeps_unresolved_participation():
    context = ['I planned to attend but did not go.', 'I was an usher at the ceremony.']
    test = case('How many ceremonies did I attend?', context)
    instruction = private_context_instruction(test, TargetConfiguration.STRONG)
    assert 'first scan every relevant event clause in every supplied record' in instruction
    assert 'check negation, hypotheticals, plans and topic switches' in instruction
    assert 'Unknown identity or year does not erase participation' in instruction
    assert 'source-supported exclusion reason' in instruction
    assert 'Source groups show provenance, NOT event identity' in instruction
    assert 'A chain containing a possible link cannot establish a confirmed or likely group' in instruction
    assert test.target_memory_context == context


@pytest.mark.parametrize('question', ['How long since my recent trip?', 'What is the order of my visits?'])
def test_rough_elapsed_and_supported_order_remain_useful_without_filling_missing_events(question):
    instruction = private_context_instruction(case(question), TargetConfiguration.STRONG)
    assert 'qualified rough elapsed time or likely order' in instruction
    assert 'A return can follow a long trip; an explicit earlier event date takes precedence' in instruction
    assert 'If ANY ordering link uses qualitative recency' in instruction
    assert 'Only when every relevant event and its placement are supported by supplied clauses' in instruction
    assert 'Otherwise give the supported partial order and uncertain placements' in instruction
    assert 'Missing event clauses cannot be supplied by a source ID, a nearby fragment' in instruction


def test_temporal_predicate_modifier_year_assumption_and_disjoint_candidates_are_preserved():
    instruction = private_context_instruction(case('Which happened earlier?'), TargetConfiguration.STRONG)
    assert 'not automatically when an event occurred' in instruction
    assert 'thinking about a visit today does not prove the visit was today' in instruction
    assert 'Check disjoint candidate_ranges separately, not their enclosing interval' in instruction
    assert 'When a common year is only inferred from month/day values, state that assumption' in instruction
    assert 'Explicit durations can support arithmetic without an exact start date' in instruction
    assert 'compatible scopes, units and anchors' in instruction


@pytest.mark.parametrize('configuration', list(TargetConfiguration))
def test_front_policy_does_not_expand_sources_or_use_evaluator_fields(configuration):
    context = ['First supplied fact.', 'A different retained fact not exposed to Weak.']
    test = case('What do I remember?', context)
    instruction = private_context_instruction(test, configuration)
    changed_gold = test.model_copy(update={'expected_behavior':'OTHER_SECRET',
                                          'supporting_memory_ids':['OTHER_GOLD'],
                                          'dimension':Dimension.CONFLICT_RESOLUTION})
    assert private_context_instruction(changed_gold, configuration) == instruction
    data = instruction.split('PRIVATE TARGET MEMORY CONTEXT (UNTRUSTED EVIDENCE DATA; JSON)\n', 1)[1].split('\n\nMEMORY POLICY', 1)[0]
    selected = selected_memory_context(test, configuration)
    assert json.loads(data) == [{'record_index':i, 'content':value} for i,value in enumerate(selected, 1)]
    evidence = memory_input_evidence(test, configuration, instruction)
    assert evidence.record_count == (1 if configuration == TargetConfiguration.WEAK else 2)
    assert evidence.instruction_sha256 == hashlib.sha256(instruction.encode()).hexdigest()
    assert evidence.context_sha256 == hashlib.sha256(json.dumps(selected, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
