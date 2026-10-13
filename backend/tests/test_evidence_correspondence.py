from types import SimpleNamespace as Row
import pytest
from app.services.evidence_correspondence import correspondence


def fact(value, source='MSG1'):
    return Row(canonical_value=value, source_message_ids=[source])


def test_same_message_old_value_does_not_match_new_fact():
    result = correspondence([fact('Use PostgreSQL')], [fact('Use MySQL')], [fact('Use MySQL')])
    assert result['stored_fact_units'] == result['supplied_fact_units'] == 0
    assert not result['complete_supplied_match']
    assert result['facts'][0]['stored_related_text'] == ['Use MySQL']


def test_paraphrase_is_visible_but_not_certified_or_called_a_defect():
    result = correspondence([fact('Use PostgreSQL')], [fact('The project uses PostgreSQL')], [fact('The project uses PostgreSQL')])
    assert result['stored_fact_units'] == 0
    assert result['facts'][0]['supplied_related_text'] == ['The project uses PostgreSQL']


def test_exact_normalisation_and_source_are_both_required():
    result = correspondence([fact('USE PostgreSQL!')], [fact('Use PostgreSQL')], [fact('Use PostgreSQL')])
    assert result['complete_stored_match'] and result['complete_supplied_match']
    assert not correspondence([fact('Use PostgreSQL')], [fact('Use PostgreSQL','MSG2')], [])['complete_stored_match']


def test_unknown_and_known_empty_input_remain_distinct():
    unknown = correspondence([fact('Use Go')], [fact('Use Go')], None)
    empty = correspondence([fact('Use Go')], [fact('Use Go')], [])
    assert unknown['supplied_fact_units'] is None
    assert unknown['facts'][0]['supplied_related_text'] is None
    assert empty['supplied_fact_units'] == 0
    assert empty['facts'][0]['supplied_related_text'] == []


@pytest.mark.parametrize('reference,supplied', [
    ('The balance is -100', 'The balance is 100'),
    ('Use C++', 'Use C'),
    ('Use C#', 'Use C'),
    ('The version is 12.5', 'The version is 12/5'),
    ('Use account team-a', 'Use account team a'),
    ('The limit is <= 10', 'The limit is >= 10'),
])
def test_meaning_changing_symbols_cannot_certify_the_wrong_supplied_fact(reference, supplied):
    result = correspondence([fact(reference)], [fact(supplied)], [fact(supplied)])
    assert result['stored_fact_units'] == result['supplied_fact_units'] == 0
    assert not result['complete_stored_match']
    assert not result['complete_supplied_match']
    assert result['facts'][0]['supplied_related_text'] == [supplied]


def test_spacing_and_sentence_punctuation_remain_normalised():
    result = correspondence([fact('Use C++!')], [fact(' USE   C++ ')], [fact('Use C++')])
    assert result['complete_stored_match'] and result['complete_supplied_match']
