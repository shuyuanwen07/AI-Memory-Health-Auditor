"""Verify the opt-in evaluator preserves the validated research contract."""
import sys
import httpx
import pytest
from app.evaluator.taxonomy_evaluator import TaxonomyEvidenceEvaluator
from app.schemas import Dimension
from test_llm_judge import _memories, _response, _test_case


def test_prompt_matches_frozen_candidate_and_excludes_private_label():
    sys.path.insert(0,'/output/proposal-delivery/ac3-taxonomy-development-tools-2026-10-28')
    try:
        from taxonomy_candidate import TaxonomyCandidate
        candidate=TaxonomyCandidate('openrouter',model='openai/gpt-6-luna')
        product=TaxonomyEvidenceEvaluator()
        test=_test_case();answer=_response();memories=_memories()[:2]
        prompt=product._judge_prompt(test,answer,memories)
        assert prompt==candidate._judge_prompt(test,answer,memories)
        assert prompt==product._judge_prompt(test.model_copy(update={'dimension':Dimension.ACCURACY,
                         'expected_behavior':'PRIVATE SENTINEL'}),answer,memories)
    finally:
        sys.path.pop(0)


def test_returns_valid_provider_judgment_even_if_rule_gate_disagrees(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','synthetic')
    evaluator=TaxonomyEvidenceEvaluator()
    raw={'passed':True,'reason':'Evidence supports the answer.','evidence_memory_ids':['M002'],
         'failure_type':None,'classification_reason':'No failure category applies.'}
    monkeypatch.setattr(evaluator,'_judge',lambda *args:raw)
    result=evaluator.evaluate(_test_case(),_response('Use MySQL.'),_memories())
    assert result.passed is True and result.evaluator=='taxonomy-evidence-openrouter-v1'
    assert result.judge_execution.verdict_status=='valid'
    assert result.judge_execution.rule_cross_check_verdict is False


def test_invalid_evidence_falls_back_to_uncertain_without_leaking_secret(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','synthetic-secret')
    evaluator=TaxonomyEvidenceEvaluator()
    monkeypatch.setattr(evaluator,'_judge',lambda *args:{'passed':True,'reason':'bad','evidence_memory_ids':['UNKNOWN'],
        'failure_type':None,'classification_reason':'none'})
    result=evaluator.evaluate(_test_case(),_response(),_memories())
    assert result.passed is None and result.evaluator.startswith('fallback-')
    assert 'synthetic-secret' not in result.reason


def test_single_attempt_and_fixed_output_budget(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','synthetic')
    calls=[]
    def fake_post(*args,**kwargs):
        calls.append(kwargs['json'])
        raise httpx.ConnectError('synthetic transport failure')
    monkeypatch.setattr('app.evaluator.taxonomy_evaluator.httpx.post',fake_post)
    result=TaxonomyEvidenceEvaluator().evaluate(_test_case(),_response(),_memories())
    assert result.passed is None and len(calls)==1
    assert calls[0]['max_tokens']==2048 and 'temperature' not in calls[0]


def test_rejects_unvalidated_model():
    with pytest.raises(ValueError):TaxonomyEvidenceEvaluator(model='openai/other')


def test_explicit_reassessment_selection_preserves_existing_defaults():
    from app.evaluator.factory import configured_evaluator, get_behaviour_evaluator
    from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
    from app.schemas import ReassessmentRequest
    from pydantic import ValidationError
    choice=ReassessmentRequest(evaluator_provider='openrouter_taxonomy',evaluator_model='openai/gpt-6-luna')
    assert configured_evaluator(choice.evaluator_provider,choice.evaluator_model)==('openrouter_taxonomy','openai/gpt-6-luna')
    assert isinstance(get_behaviour_evaluator(choice.evaluator_provider,choice.evaluator_model),TaxonomyEvidenceEvaluator)
    assert isinstance(get_behaviour_evaluator('rule_based'),RuleBasedBehaviourEvaluator)
    with pytest.raises(ValidationError):
        ReassessmentRequest(evaluator_provider='openrouter_taxonomy',evaluator_model='openai/other')
