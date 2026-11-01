"""Eligible evidence must still become validated, model-written questions."""
from dataclasses import asdict
from datetime import datetime, timezone
import json

import pytest
from pydantic import ValidationError

from app.extraction.llm import PipelineRequestError
from app.schemas import AuditRun, AuditStatus, Memory, MemoryRelationship, TargetConfiguration, TargetProvider, TestCase
from app.test_generator.agent import AgentTestGenerator
from app.test_generator.evidence_slot_inventory import PlanningEvidenceSlot


def inputs():
    def memory(mid,text,relations=()):
        return Memory(memory_id=mid,conversation_id='C',canonical_value=text,status='confirmed',
                      source_message_ids=['source-'+mid],relationships=list(relations))
    def edge(kind,target):
        return MemoryRelationship(type=kind,target_memory_id=target)
    memories=[memory('old',"The visitor's palette was amber."),
              memory('new',"The visitor's palette changed to violet.",[edge('UPDATE','old')]),
              memory('other','For the same period the palette is exclusively ivory.',[edge('CONFLICT','new')]),
              memory('scope','For the exhibition only use amber.',[edge('CONTEXTUAL_OVERRIDE','new')]),
              memory('fact','The visitor collects stamps.')]
    audit=AuditRun(run_id='R',conversation_id='C',status=AuditStatus.CREATED,
                   target_configuration=TargetConfiguration.WEAK,provider=TargetProvider.RULE_BASED,
                   model='rule-based-target-ai',temperature=0,random_seed=42,test_budget=4,
                   prompt_template_version='fixture',created_at=datetime.now(timezone.utc))
    return memories,audit


class Planner:
    def __init__(self):
        self.requests=[]

    def complete_json(self,**request):
        self.requests.append(request)
        payload=json.loads(request['prompt'].split('\n\n',1)[1])
        return {'selected_candidate_ids_by_dimension':{
            dim:ids[:payload['required_available_quota_by_dimension'][dim]]
            for dim,ids in payload['candidate_ids_by_dimension'].items()},'coverage_notes':[]}


class GenericWriter:
    def __init__(self):
        self.requests=[]

    def complete_json(self,**request):
        self.requests.append(request)
        properties=request['schema']['properties']['tests']['items']['properties']
        dimension=properties['dimension']['enum'][0]
        kind=properties['test_type']['enum'][0]
        ids=properties['supporting_memory_ids']['items']['enum']
        prompts={
            'accuracy':"What is the user's recorded stored information?",
            'freshness':'How did the palette change, and what must be clarified before choosing its current value?',
            'conflict_resolution':'Which palette descriptions need clarification before relying on either?',
            'appropriate_use':'How should the exhibition instruction be used alongside the disputed general palette?',
        }
        expected={
            'accuracy':'The visitor collects stamps.',
            'freshness':'Explain the amber-to-violet update, preserve the incompatible ivory record and ask the user for clarification.',
            'conflict_resolution':'Keep the violet and ivory records visible and ask the user for clarification before selecting either.',
            'appropriate_use':'Use amber only at the exhibition. Preserve the violet and ivory disagreement outside that scope and ask the user for clarification.',
        }
        return {'tests':[{'dimension':dimension,'test_type':kind,'prompt':prompts[dimension],
                          'expected_behavior':expected[dimension],'supporting_memory_ids':ids}]}


class PermissiveReviewer:
    def complete_json(self,**request):
        return {'duplicate_pairs':[],'quality_findings':[],'slot_alignment_findings':[]}


def test_eligible_unknown_topic_reaches_writer_but_generic_actual_question_still_fails():
    memories,audit=inputs();planner=Planner();writer=GenericWriter()
    generator=AgentTestGenerator(client=writer,planner_client=planner,reviewer_client=PermissiveReviewer())
    seeds,_,available=generator._coverage_seed_inventory(memories,4)
    evidence_only=[slot for slot in seeds if isinstance(slot,PlanningEvidenceSlot)]
    assert evidence_only
    assert all(n>0 for n in available.values())
    with pytest.raises(ValidationError):
        TestCase.model_validate(asdict(evidence_only[0]))
    with pytest.raises(PipelineRequestError):
        generator.generate(memories,audit)
    assert planner.requests and len(writer.requests)>=4
    assert generator.last_observation['status']=='failed'
    rejections=[q for stage in generator.last_observation['quality_gate'] for q in stage['rejected_candidates']]
    assert any('does not identify the fact or event' in q['reason'] for q in rejections)
    payload=json.loads(planner.requests[0]['prompt'].split('\n\n',1)[1])
    assert all('prompt' not in slot and 'expected_behavior' not in slot for slot in payload['candidate_slots'])
    assert generator.last_observation.get('generated_test_count',0)==0


@pytest.mark.parametrize(('policy','version'),[
    ('strict_full_v1','coverage-planner-agent-v4'),
    ('evidence_supported_only_v1','coverage-planner-agent-v3'),
])
def test_strict_source_inventory_has_a_distinct_planner_protocol(policy,version):
    memories,audit=inputs();planner=Planner()
    audit=audit.model_copy(update={'reproducibility':audit.reproducibility.model_copy(update={'coverage_policy':policy})})
    generator=AgentTestGenerator(client=object(),planner_client=planner,reviewer_client=object())
    generator._agent_observation={}
    inventory=generator._coverage_seed_inventory(memories,4,coverage_policy=policy)
    if policy=='evidence_supported_only_v1':
        assert all(isinstance(slot,TestCase) for slot in inventory[0])
    plan=generator._build_coverage_plan(memories,audit,inventory=inventory)
    assert plan
    assert planner.requests[0]['prompt_template_version']==version
    assert generator._agent_observation['coverage_planner']['prompt_template_version']==version
    if policy=='strict_full_v1':
        assert len(plan)==4
        assert all(row['accepted_question_count']==0 for row in generator._agent_observation['dimension_coverage'])
        assert all('eligible evidence slot' in row['reason'] for row in generator._agent_observation['dimension_coverage'])
