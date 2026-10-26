"""Synthetic one-edge contract; no source-specific examples or provider requests."""
import copy
import json

import pytest

from app.extraction.llm import PipelineRequestError
from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
from app.memory_agent.quote_candidate_catalog import build_catalog


CONTENTS=['A colleague described a recital in a stone hall.',
          'Another account mentioned a recital and a green curtain.']
QUESTION='Which supplied recital descriptions may refer to the same event?'


def selection():
    catalog=build_catalog(CONTENTS)
    return {'quotes':[{'quote_id':f'Q{i}','candidate_id':next(c.candidate_id for c in catalog.candidates
                          if c.record_index==i and c.quote==text)}for i,text in enumerate(CONTENTS,1)],
        'mentions':[{'mention_id':'M1','quote_id':'Q1'},{'mention_id':'M2','quote_id':'Q2'}],
        'relations':[{'relation_id':'R1','left_mention_id':'M1','right_mention_id':'M2','level':'possible',
            'evidence_quote_ids':['Q1','Q2'],'cues':['generic_role_only','shared_venue_only'],
            'caveat':'Possible overlap only; no confirmed identity, date or count.'}],
        'limitations':'These are uncertain candidate relations, not task conclusions.'}


class Client:
    def __init__(self,value):
        self.value=copy.deepcopy(value);self.calls=[];self.last_execution=None
    def complete_json(self,**request):
        self.calls.append(request)
        self.last_execution={'request_attempts':1,'reported_model':'openai/gpt-6-luna','status':'parsed'}
        return self.value


def analyze(value):
    client=Client(value)
    analyzer=TargetIdentityEvidenceAnalyzer('openrouter','openai/gpt-6-luna',client=client)
    return analyzer,client


def test_prompt_and_wire_schema_explain_single_unordered_pair_and_existing_multicue():
    analyzer,client=analyze(selection())
    result=analyzer.analyze(question=QUESTION,context=CONTENTS)
    request=client.calls[0]
    assert 'each unordered pair of mention IDs in at most one relation' in request['instructions']
    assert 'Swapping the two endpoints is the same pair' in request['instructions']
    assert "single relation's cues list" in request['instructions']
    assert 'One relation per unordered mention pair' in request['schema']['$defs']['IdentityRelation']['description']
    assert request['schema']['$defs']['IdentityRelation']['properties']['cues']['maxItems']==6
    assert analyzer.VERSION=='target-identity-evidence-v10-source-explicitness'
    assert request['prompt_template_version']==analyzer.VERSION
    assert request['schema_name']=='target_identity_evidence'
    assert len(result.relations)==1


@pytest.mark.parametrize('mutation',['same','different_cues','different_level','opposite_order'])
def test_duplicate_unordered_pairs_fail_closed_without_retry_merge_or_prune(mutation):
    value=selection();second=copy.deepcopy(value['relations'][0]);second['relation_id']='R2'
    if mutation=='different_cues':second['cues']=['within_source_narrative']
    elif mutation=='different_level':second['level']='distinct'
    elif mutation=='opposite_order':second['left_mention_id'],second['right_mention_id']='M2','M1'
    value['relations'].append(second);before=copy.deepcopy(value);analyzer,client=analyze(value)
    with pytest.raises(PipelineRequestError) as caught:
        analyzer.analyze(question=QUESTION,context=CONTENTS)
    assert isinstance(caught.value.__cause__,ValueError)
    assert str(caught.value.__cause__)=='Duplicate relation pairs.'
    assert len(client.calls)==1 and client.value==before
    observation=analyzer.last_observation
    assert observation['status']=='failed' and observation['error_code']=='invalid_identity_contract'
    assert observation['error_diagnostics']=={'phase':'output_validation','validation_type':'ValueError',
                                             'reason_code':'duplicate_relation_pair'}
    assert observation['output_data'] is None
    assert observation['raw_model_selection']==before
    assert observation['raw_model_draft']==before
    assert len(observation['hydrated_quote_draft']['relations'])==2
    assert observation['candidate_selection_receipt'] is not None
    assert not observation['quote_binding_adjustments']
    assert 'stone hall' not in json.dumps(observation['error_diagnostics'])


def test_single_multicue_edge_preserves_all_legal_cues_and_exact_source_receipt():
    value=selection();value['relations'][0]['cues']=['within_source_narrative','generic_role_only','distinctive_detail']
    before=copy.deepcopy(value);analyzer,client=analyze(value)
    result=analyzer.analyze(question=QUESTION,context=CONTENTS)
    assert len(client.calls)==1 and client.value==before
    assert result.relations[0].cues==value['relations'][0]['cues']
    assert len(result.relations)==1 and not result.relation_cue_adjustments
    observation=analyzer.last_observation
    assert observation['status']=='completed' and observation['error_code'] is None
    assert observation['raw_model_selection']==before
    for binding in observation['candidate_selection_receipt']['bindings']:
        assert CONTENTS[binding['record_index']-1][binding['char_start']:binding['char_end']]==binding['quote']


def test_different_unordered_pairs_can_still_share_one_mention():
    contents=[*CONTENTS,'A third account was reported separately.'];catalog=build_catalog(contents);value=selection()
    value['quotes'].append({'quote_id':'Q3','candidate_id':next(c.candidate_id for c in catalog.candidates
        if c.record_index==3 and c.quote==contents[2])})
    value['mentions'].append({'mention_id':'M3','quote_id':'Q3'})
    value['relations'].append({'relation_id':'R2','left_mention_id':'M1','right_mention_id':'M3','level':'distinct',
        'evidence_quote_ids':['Q1','Q3'],'cues':['separate_occurrence'],'caveat':'Explicitly separate account; no merged group.'})
    analyzer,client=analyze(value)
    result=analyzer.analyze(question=QUESTION,context=contents)
    assert len(result.relations)==2 and len(client.calls)==1
