"""A contextual rule's scope is not determined by its observation time."""
from datetime import datetime, timezone

import pytest

from app.extraction.llm import PipelineRequestError
from app.extraction.relationship_agent import RelationshipAnalysisAgent
from app.schemas import Conversation, ConversationMessage, Memory


class Client:
    provider='test'
    model='fixture'
    last_execution=None

    def __init__(self, relationships):
        self.relationships=relationships
        self.calls=0

    def complete_json(self, **kwargs):
        self.calls+=1
        return {'relationships':self.relationships}


def inputs():
    texts=['The project normally uses weekly planning.',
           'The project now uses two-week planning instead of weekly.',
           'For the launch only, use daily planning.',
           'The general project preference is two-week planning.']
    dates=[1,3,2,4]
    messages=[ConversationMessage(message_id=f'S{i}',role='user',content=text,
              timestamp=datetime(2026,5,day,tzinfo=timezone.utc)) for i,(text,day) in enumerate(zip(texts,dates),1)]
    conversation=Conversation(conversation_id='C',authorised=True,created_at=messages[0].timestamp,messages=messages)
    memories=[Memory(memory_id=f'M{i:03}',conversation_id='C',canonical_value=m.content,
              status='candidate',source_message_ids=[m.message_id],timestamp=m.timestamp) for i,m in enumerate(messages,1)]
    return conversation,memories


def relation(current,prior,kind):
    return {'current_memory_id':f'M{current:03}','prior_memory_id':f'M{prior:03}','type':kind,
            'current_evidence_message_ids':[f'S{current}'],'prior_evidence_message_ids':[f'S{prior}'],
            'confidence':.9,'rationale':'The cited source explicitly establishes this scoped relation.'}


def test_earlier_observed_scoped_rule_is_not_rejected_with_the_whole_batch():
    conversation,memories=inputs()
    client=Client([relation(2,1,'UPDATE'),relation(3,4,'CONTEXTUAL_OVERRIDE')])
    result=RelationshipAnalysisAgent(client).analyze(conversation,memories)
    assert len(result['relationships'])==2
    assert client.calls==1
    assert memories[1].relationships[0].type.value=='UPDATE'
    assert memories[2].relationships[0].type.value=='CONTEXTUAL_OVERRIDE'


@pytest.mark.parametrize('kind',['UPDATE','CONFLICT'])
def test_reverse_direction_remains_rejected_for_chronologically_ordered_edge_types(kind):
    conversation,memories=inputs()
    agent=RelationshipAnalysisAgent(Client([relation(3,4,kind)]))
    with pytest.raises(PipelineRequestError):
        agent.analyze(conversation,memories)
    assert all(not m.relationships for m in memories)
    assert agent.last_observation['error_code']=='temporal_direction_mismatch'
    diagnostic=agent.last_observation['error_diagnostics']['validation_errors'][0]
    assert diagnostic['relationship_type']==kind
    assert diagnostic['field']=='relationships.0'


def test_scope_time_exemption_does_not_bypass_endpoint_citations():
    conversation,memories=inputs()
    bad=relation(3,4,'CONTEXTUAL_OVERRIDE');bad['current_evidence_message_ids']=['S999']
    agent=RelationshipAnalysisAgent(Client([relation(2,1,'UPDATE'),bad]))
    with pytest.raises(PipelineRequestError):
        agent.analyze(conversation,memories)
    assert all(not m.relationships for m in memories)
    assert agent.last_observation['error_code']=='endpoint_evidence_mismatch'
