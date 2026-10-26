"""Anonymous calibration contract; fake-client checks are not model-semantic tests."""
import copy
import hashlib
import json

import pytest

from app.extraction.llm import PipelineRequestError
from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer as Analyzer
from app.memory_agent.quote_candidate_catalog import build_catalog


CONTENTS = ['I attended an exhibit described by a coordinator at a community hall.',
            'Another report describes an exhibit by the coordinator at the community hall.']
FROZEN16_SCHEMA_SHA256 = 'cf49bea4d0339acc0241549fec36cf24e47ad2e0fc628b67d49ca071c6c5ac90'


def selection(level='likely'):
    catalog = build_catalog(CONTENTS)
    return {'quotes': [{'quote_id': f'Q{i}', 'candidate_id': next(c.candidate_id for c in catalog.candidates
                if c.record_index == i and c.quote == text)} for i, text in enumerate(CONTENTS, 1)],
        'mentions': [{'mention_id': 'M1', 'quote_id': 'Q1'}, {'mention_id': 'M2', 'quote_id': 'Q2'}],
        'relations': [{'relation_id': 'R1', 'left_mention_id': 'M1', 'right_mention_id': 'M2',
            'level': level, 'evidence_quote_ids': ['Q1', 'Q2'], 'cues': ['shared_participant', 'shared_venue_only'],
            'caveat': 'No direct source equivalence statement; matching descriptions may recur.'}],
        'limitations': 'Identity candidates only; no answer or event total.'}


class Client:
    def __init__(self, value):
        self.value = copy.deepcopy(value)
        self.calls = []
        self.last_execution = None

    def complete_json(self, **request):
        self.calls.append(request)
        self.last_execution = {'request_attempts': 1, 'reported_model': 'openai/gpt-6-luna', 'status': 'parsed'}
        return copy.deepcopy(self.value)


def analyze(value):
    client = Client(value)
    analyzer = Analyzer('openrouter', 'openai/gpt-6-luna', client=client)
    return analyzer, client


def test_explicit_requires_source_identity_of_occurrence_not_matching_descriptors():
    text = Analyzer.INSTRUCTIONS
    assert 'SAME historical occurrence' in text
    assert 'not merely the same event name or description' in text
    assert 'Matching person, title, medium, venue or date' in text
    assert 'even in combination' in text
    assert 'not an explicit link' in text
    assert 'absence of a separate date' in text
    assert 'absence of a stated difference' in text
    assert 'Cite the source assertion or reference' in text


def test_likely_inference_cross_message_coreference_and_possible_remain_useful():
    text = Analyzer.INSTRUCTIONS
    assert 'Distinctive matching attributes can support likely rather than forcing abstention' in text
    assert 'generic unresolved overlap supports possible' in text
    assert 'across messages can establish explicit identity' in text
    assert 'unambiguously refers back to that same occurrence' in text
    assert 'containing possible to a likely/explicit whole group' in text
    assert 'a likely identity does not establish a year' in text


def test_continuous_source_narrative_is_not_a_provenance_or_venue_alias():
    text = Analyzer.INSTRUCTIONS
    assert 'within_source_narrative only when supplied source text contains a continuous narrative' in text
    assert 'shared venue, topic, speaker or provenance label across separate passages' in text
    assert 'same source_groups alone does not prove continuity' in text
    assert 'Preserve topic switches and unresolved reference scope' in text


def test_wire_schema_exactly_matches_release16_public_schema_snapshot():
    schema = Analyzer.REQUEST_SCHEMA.model_json_schema()
    digest = hashlib.sha256(json.dumps(schema, ensure_ascii=False, sort_keys=True,
                                      separators=(',', ':')).encode()).hexdigest()
    assert digest == FROZEN16_SCHEMA_SHA256
    quote_schema = schema['properties']['quotes']['items']['$ref'].split('/')[-1]
    assert set(schema['$defs'][quote_schema]['properties']) == {'quote_id', 'candidate_id'}
    relation = schema['$defs']['IdentityRelation']['properties']
    assert relation['level']['enum'] == ['explicit', 'likely', 'possible', 'distinct']
    assert relation['evidence_quote_ids']['minItems'] == 2
    assert relation['evidence_quote_ids']['maxItems'] == 6
    assert relation['cues']['minItems'] == 1 and relation['cues']['maxItems'] == 6


@pytest.mark.parametrize('level', ['explicit', 'likely', 'possible', 'distinct'])
def test_typed_level_is_preserved_without_semantic_posthoc_downgrade_or_retry(level):
    value = selection(level)
    analyzer, client = analyze(value)
    result = analyzer.analyze(question='How are these descriptions related?', context=CONTENTS)
    assert result.relations[0].level == level
    assert client.value == value and len(client.calls) == 1
    assert analyzer.last_observation['raw_model_selection'] == value
    assert analyzer.last_observation['raw_model_draft'] == value
    assert Analyzer.VERSION == 'target-identity-evidence-v10-source-explicitness'
    assert client.calls[0]['prompt_template_version'] == Analyzer.VERSION
    assert client.calls[0]['schema_name'] == 'target_identity_evidence'
    assert client.calls[0]['instructions'] == Analyzer.INSTRUCTIONS
    # In particular, a synthetic unsupported explicit level is not rewritten.
    # This verifies mechanical preservation, NOT semantic correctness of that level.


def test_exact_source_catalog_and_hydrated_bindings_unchanged():
    value = selection()
    analyzer, client = analyze(value)
    result = analyzer.analyze(question='How are the supplied descriptions related?', context=CONTENTS)
    observation = analyzer.last_observation
    assert observation['input_payload']['selected_records'] == [
        {'record_index': i, 'content': text, 'source_groups': []} for i, text in enumerate(CONTENTS, 1)]
    assert result.relations[0].cues == value['relations'][0]['cues']
    assert not result.quote_binding_adjustments and not result.relation_cue_adjustments
    for binding in observation['candidate_selection_receipt']['bindings']:
        assert CONTENTS[binding['record_index'] - 1][binding['char_start']:binding['char_end']] == binding['quote']
    assert len(client.calls) == 1


@pytest.mark.parametrize('mutation', ['duplicate_pair', 'unknown_endpoint', 'missing_endpoint_evidence', 'invented_candidate'])
def test_old_graph_and_quote_constraints_still_fail_closed_without_repair(mutation):
    value = selection()
    if mutation == 'duplicate_pair':
        second = copy.deepcopy(value['relations'][0])
        second.update(relation_id='R2', left_mention_id='M2', right_mention_id='M1')
        value['relations'].append(second)
    elif mutation == 'unknown_endpoint':
        value['relations'][0]['right_mention_id'] = 'M9'
    elif mutation == 'missing_endpoint_evidence':
        value['relations'][0]['evidence_quote_ids'] = ['Q1', 'Q9']
    else:
        value['quotes'][0]['candidate_id'] = 'C999999'
    analyzer, client = analyze(value)
    with pytest.raises(PipelineRequestError):
        analyzer.analyze(question='Compare the descriptions.', context=CONTENTS)
    assert len(client.calls) == 1 and client.value == value
    assert analyzer.last_observation['status'] == 'failed'
    assert analyzer.last_observation['raw_model_selection'] == value
