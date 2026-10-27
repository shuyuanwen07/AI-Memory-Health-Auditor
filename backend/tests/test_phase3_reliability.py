"""Development-only regressions; validation specifications live separately."""
import json
from pathlib import Path
from datetime import datetime,timezone
from types import SimpleNamespace
import pytest
from app.services.relationship_bindings import explicit_owner_conflicts
from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.schemas import Memory,MemoryStatus


@pytest.mark.parametrize('answer',[
    "Your brother's partner is Mira.","Your partner is Mira.",
    "Mira is your brother's partner.","The user's brother's partner is Mira.",
])
def test_explicit_wrong_owner_does_not_pass_because_the_name_is_correct(answer):
    assert explicit_owner_conflicts(answer,["My sister's partner is Mira."])


@pytest.mark.parametrize('answer',[
    'Mira',"Your sister's partner is Mira.","Mira is your sister's partner.",
    "Your sister's partner is Mira, not your brother's partner.",
    "If your brother's partner is Mira, that would be hypothetical.",
    "Your brother's partner is not Mira.",
])
def test_short_correct_negated_or_hypothetical_owner_does_not_invent_failure(answer):
    assert not explicit_owner_conflicts(answer,["My sister's partner is Mira."])


def test_another_supported_owner_does_not_invent_contradiction():
    assert not explicit_owner_conflicts("Your brother's partner is Mira.",[
        "My sister's partner is Mira.","My brother's partner is Mira."])


@pytest.mark.parametrize('value',[
    'None of that was a database change to either project',
    'That was not a database change to either project',
    'Food suggestions are separate from our technical work, and there is no need to bring my diet into decisions about programming languages, databases or deployment',
])
def test_boundary_instruction_and_denied_change_are_not_lifecycle_edges(value):
    extractor=RuleBasedMemoryExtractor()
    memories=[Memory(memory_id='M1',conversation_id='C',canonical_value='The Harbour web frontend uses TypeScript',status=MemoryStatus.CONFIRMED),
              Memory(memory_id='M2',conversation_id='C',canonical_value='A friend mentioned SQLite in a tutorial',status=MemoryStatus.CONFIRMED)]
    assert extractor._relationships(Memory(memory_id='M3',conversation_id='C',canonical_value=value,status=MemoryStatus.CONFIRMED),memories)==[]


def test_frozen_development_retrieval_contracts_and_weak_invariance(tmp_path):
    import subprocess,sys
    root=Path(__file__).resolve().parents[2]
    output=tmp_path/'contracts.json'
    subprocess.run([sys.executable,str(root/'scripts/verify_phase3_contracts.py'),'--backend-root',str(root/'backend'),'--split','development','--output',str(output)],cwd=root,check=True,capture_output=True)
    result=json.loads(output.read_text())
    assert result['summary']['evaluation_contracts_passed']==10
    assert result['summary']['strong_retrieval_contracts_passed']==3
    for row in result['retrieval']:
        if row['policy']=='weak_first_hit':
            assert len(row['context'])==1 and 'MySQL' in row['context'][0]
        else:
            assert len(row['options_delivered']) in {0,2}
            assert len(row['context'])<=int(row['id'].rsplit('-',1)[1])


def test_semantic_pass_cannot_override_an_explicit_owner_mismatch(monkeypatch):
    from app.evaluator.llm_judge import LLMBehaviourEvaluator
    from app.schemas import TestCase,TargetResponse
    case=TestCase(test_id='T-owner',run_id='R-owner',dimension='accuracy',
        prompt="Who is the user's sister's partner?",expected_behavior="My sister's partner is Mira.",
        supporting_memory_ids=['M'],generator_version='development')
    answer=TargetResponse(response_id='A-owner',test_id=case.test_id,run_id=case.run_id,
        response_text="Your brother's partner is Mira.",model='fixture',temperature=0,
        created_at=datetime.now(timezone.utc))
    monkeypatch.setattr(LLMBehaviourEvaluator,'_credential',lambda _: 'isolated-fixture')
    monkeypatch.setattr(LLMBehaviourEvaluator,'_judge',lambda *_:{
        'passed':True,'reason':'Synthetic biased semantic acceptance',
        'evidence_memory_ids':['M'],'failure_type':None,'classification_reason':'No unique category.'})
    result=LLMBehaviourEvaluator('openrouter').evaluate(case,answer,[
        Memory(memory_id='M',conversation_id='C',canonical_value="My sister's partner is Mira.",status=MemoryStatus.CONFIRMED)])
    assert result.passed is None
    assert result.judge_execution.verdict_status=='review_disagreement'
    assert result.judge_execution.provider_verdict is True
    assert result.judge_execution.rule_cross_check_verdict is False
