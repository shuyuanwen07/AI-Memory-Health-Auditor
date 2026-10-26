"""Legacy quote validator checks plus strict candidate-only live analyzer checks.

The old ASCII binder remains a pure validator seam; no fake live response may
use the retired quote/record/occurrence request shape.
"""
import copy

import pytest

from app.extraction.llm import PipelineRequestError
from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
from app.memory_agent.quote_candidate_catalog import build_catalog
from app.schemas.target_identity import IdentityEvidenceDraft

SOURCE = 'My friend Rowan finally visited the quiet gallery.'
MODEL = 'openai/gpt-6-luna'


def draft(quote='my friend Rowan', record=1, occurrence=0):
    return {'quotes': [{'quote_id': 'Q1', 'record_index': record, 'quote': quote, 'occurrence': occurrence}],
            'mentions': [{'mention_id': 'M1', 'quote_id': 'Q1'}], 'relations': [],
            'limitations': 'Synthetic source provenance only; no identity merge.'}


def legacy_validate(value=None, context=None, adjustments=None):
    """Exercise only the retained pure validator, never analyzer.analyze."""
    texts = [SOURCE] if context is None else context
    return TargetIdentityEvidenceAnalyzer._validated_result(
        IdentityEvidenceDraft.model_validate(draft() if value is None else value), texts,
        question='Compare the supplied narratives.', context=texts,
        version='legacy-validator-only', binding_adjustments=adjustments,
    )


def legacy_reject(value, context=None):
    before = copy.deepcopy(value)
    with pytest.raises(ValueError):
        legacy_validate(value, context)
    assert value == before


def selection(contents, *, quote=None, occurrence=0):
    candidate = next(c for c in build_catalog(contents).candidates
                     if c.record_index == 1 and c.quote == (contents[0] if quote is None else quote)
                     and c.occurrence == occurrence)
    return {'quotes': [{'quote_id': 'Q1', 'candidate_id': candidate.candidate_id}],
            'mentions': [{'mention_id': 'M1', 'quote_id': 'Q1'}], 'relations': [],
            'limitations': 'Synthetic source provenance only; no identity merge.'}


class Client:
    def __init__(self, value):
        self.value = copy.deepcopy(value)
        self.calls = []
        self.last_execution = None

    def complete_json(self, **kwargs):
        self.calls.append(kwargs)
        self.last_execution = {'status': 'parsed', 'reported_model': MODEL, 'request_attempts': 1}
        return copy.deepcopy(self.value)


def live(value=None, context=None):
    texts = [SOURCE] if context is None else context
    value = selection(texts) if value is None else value
    client = Client(value)
    agent = TargetIdentityEvidenceAnalyzer('openrouter', MODEL, client=client)
    result = agent.analyze(question='Compare the supplied narratives.', context=texts)
    return agent, client, result


def test_legacy_unique_ascii_case_binding_has_exact_quote_and_explicit_receipt():
    value = draft()
    before = copy.deepcopy(value)
    result = legacy_validate(value)
    quote = result.quotes[0]
    assert quote.quote == 'My friend Rowan'
    assert SOURCE[quote.char_start:quote.char_end] == quote.quote
    assert result.quote_binding_adjustments[0].model_dump() == {
        'quote_id': 'Q1', 'record_index': 1, 'model_quote': 'my friend Rowan',
        'source_quote': 'My friend Rowan', 'model_occurrence': 0, 'char_start': 0,
        'char_end': len('My friend Rowan'),
        'reason_code': 'unique_ascii_case_insensitive_exact_substring',
    }
    assert value == before


def test_legacy_exact_quote_occurrence_semantics_are_unchanged():
    text = 'My friend Rowan. My friend Rowan.'
    result = legacy_validate(draft('My friend Rowan', occurrence=1), [text])
    assert result.quotes[0].char_start == text.rfind('My friend Rowan')
    assert result.quote_binding_adjustments == []


def test_legacy_internal_possessive_deletion_rejected_contiguous_span_allowed():
    text = "My colleague's friend Rowan joined the workshop."
    legacy_reject(draft('My friend Rowan'), [text])
    result = legacy_validate(draft('friend Rowan'), [text])
    assert result.quotes[0].quote == 'friend Rowan'
    assert result.quote_binding_adjustments == []


def test_legacy_exact_quote_not_reassigned_to_differently_cased_earlier_match():
    text = 'MY friend Rowan. my friend Rowan.'
    result = legacy_validate(draft('my friend Rowan'), [text])
    assert result.quotes[0].char_start == text.index('my friend Rowan')
    assert result.quote_binding_adjustments == []


def test_legacy_ascii_binding_preserves_unicode_codepoint_offsets():
    text = '🌿 Élan: My Friend Rowan finally arrived.'
    quote = legacy_validate(draft('my friend rowan'), [text]).quotes[0]
    assert quote.char_start == text.index('My Friend Rowan')
    assert quote.char_end == quote.char_start + len('My Friend Rowan')
    assert text[quote.char_start:quote.char_end] == 'My Friend Rowan'


@pytest.mark.parametrize('quote,text', [
    ('istanbul', 'İstanbul'), ('STRASSE', 'Straße'), ('K', 'K'),
    ('my  friend Rowan', SOURCE), ('my friend Rowan!', SOURCE),
    ('my acquaintance Rowan', SOURCE), ('my friend Rown', SOURCE),
    ('my friend Rowan', 'My friend Rowan; MY FRIEND ROWAN'), ('aa', 'AAA'),
])
def test_legacy_other_edits_unicode_folding_and_ambiguous_candidates_rejected(quote, text):
    legacy_reject(draft(quote), [text])


def test_legacy_record_index_is_not_repaired_or_searched_elsewhere():
    legacy_reject(draft(), ['Nothing about that person here.', SOURCE])


def test_legacy_occurrence_not_silently_reset_for_unique_case_candidate():
    legacy_reject(draft(occurrence=1), [SOURCE])


def test_legacy_duplicate_mention_rule_rejects_after_binding_with_receipt():
    value = draft()
    value['mentions'].append({'mention_id': 'M2', 'quote_id': 'Q1'})
    adjustments = []
    with pytest.raises(ValueError, match='Duplicate mention quote references'):
        legacy_validate(value, adjustments=adjustments)
    assert len(adjustments) == 1


def test_legacy_canonicalized_duplicate_spans_still_rejected():
    value = draft()
    value['quotes'].append({'quote_id': 'Q2', 'record_index': 1, 'quote': 'My friend Rowan', 'occurrence': 0})
    value['mentions'].append({'mention_id': 'M2', 'quote_id': 'Q2'})
    legacy_reject(value)


@pytest.mark.parametrize('mutation', ['unknown_endpoint', 'missing_endpoint_evidence', 'blank_caveat'])
def test_legacy_relation_constraints_survive_quote_binding(mutation):
    value = draft()
    value['quotes'].append({'quote_id': 'Q2', 'record_index': 2, 'quote': 'Another account.', 'occurrence': 0})
    value['mentions'].append({'mention_id': 'M2', 'quote_id': 'Q2'})
    value['relations'] = [{'relation_id': 'R1', 'left_mention_id': 'M1', 'right_mention_id': 'M2',
                          'level': 'possible', 'evidence_quote_ids': ['Q1', 'Q2'],
                          'cues': ['generic_role_only'], 'caveat': 'No positive identity link is established.'}]
    if mutation == 'unknown_endpoint':
        value['relations'][0]['right_mention_id'] = 'M99'
    elif mutation == 'missing_endpoint_evidence':
        value['quotes'].append({'quote_id': 'Q3', 'record_index': 2, 'quote': 'account.', 'occurrence': 0})
        value['relations'][0]['evidence_quote_ids'] = ['Q1', 'Q3']
    else:
        value['relations'][0]['caveat'] = ' '
    legacy_reject(value, [SOURCE, 'Another account.'])


def test_legacy_positive_relation_preserved_without_semantic_promotion():
    value = draft()
    value['quotes'].append({'quote_id': 'Q2', 'record_index': 2, 'quote': 'Another account.', 'occurrence': 0})
    value['mentions'].append({'mention_id': 'M2', 'quote_id': 'Q2'})
    relation = {'relation_id': 'R1', 'left_mention_id': 'M1', 'right_mention_id': 'M2',
                'level': 'possible', 'evidence_quote_ids': ['Q1', 'Q2'], 'cues': ['generic_role_only'],
                'caveat': 'The source does not establish whether this is the same person.'}
    value['relations'] = [relation]
    assert legacy_validate(value, [SOURCE, 'Another account.']).relations[0].model_dump() == relation


def test_live_positive_selects_real_natural_full_span_without_ascii_repair():
    value = selection([SOURCE])
    agent, client, result = live(value)
    assert result.quotes[0].quote == SOURCE
    assert (result.quotes[0].char_start, result.quotes[0].char_end) == (0, len(SOURCE))
    assert result.quote_binding_adjustments == []
    assert agent.last_observation['raw_model_selection'] == value
    assert agent.last_observation['candidate_selection_receipt']['bindings'][0]['quote'] == SOURCE
    assert len(client.calls) == 1
    assert set(value['quotes'][0]) == {'quote_id', 'candidate_id'}


def test_live_natural_clause_uses_exact_unicode_offsets_and_requested_occurrence():
    text = '🌿 Élan: My Friend Rowan finally arrived. My Friend Rowan finally arrived.'
    value = selection([text], quote='My Friend Rowan finally arrived.', occurrence=1)
    _, _, result = live(value, [text])
    quote = result.quotes[0]
    assert quote.char_start == text.rfind('My Friend Rowan finally arrived.')
    assert text[quote.char_start:quote.char_end] == quote.quote
    assert result.quote_binding_adjustments == []


def test_live_prompt_and_schema_require_candidate_ids_not_quote_copying():
    _, client, _ = live()
    request = client.calls[0]
    assert 'candidate_id' in request['instructions']
    assert 'Never write quote text, record_index, offsets or occurrence' in request['instructions']
    assert request['prompt_template_version'] == TargetIdentityEvidenceAnalyzer.VERSION
    schema = request['schema']['$defs']['CandidateQuoteReference']['properties']
    assert set(schema) == {'quote_id', 'candidate_id'}


def test_live_retired_quote_shape_fails_closed_with_original_private_raw_selection():
    value = draft()
    client = Client(value)
    agent = TargetIdentityEvidenceAnalyzer('openrouter', MODEL, client=client)
    with pytest.raises(PipelineRequestError):
        agent.analyze(question='Compare narratives.', context=[SOURCE])
    assert agent.last_observation['raw_model_selection'] == value
    assert agent.last_observation['unvalidated_output_data'] == value
    assert agent.last_observation['output_data'] is None
    assert agent.last_observation['candidate_selection_receipt'] is None
    assert len(client.calls) == 1


def test_live_candidate_selection_snapshot_is_not_a_reference_to_client_value():
    value = selection([SOURCE])
    agent, client, _ = live(value)
    client.value['quotes'][0]['candidate_id'] = 'C999999'
    assert agent.last_observation['raw_model_selection'] == value


def test_live_hydrated_full_quote_still_obeys_final_advisory_character_limit():
    value = selection([SOURCE])
    client = Client(value)
    agent = TargetIdentityEvidenceAnalyzer('openrouter', MODEL, client=client)
    agent.MAX_ADVISORY_CHARACTERS = 100
    with pytest.raises(PipelineRequestError):
        agent.analyze(question='Compare narratives.', context=[SOURCE])
    assert agent.last_observation['raw_model_selection'] == value
    assert agent.last_observation['hydrated_quote_draft']['quotes'][0]['quote'] == SOURCE
    assert agent.last_observation['candidate_selection_receipt']['bindings'][0]['quote'] == SOURCE
    assert agent.last_observation['output_data'] is None
    assert len(client.calls) == 1
