"""Synthetic pure retrieval normalization; no model or dataset access."""
import pytest
from app.memory_agent.retrieval_text import (expand_pronoun_contractions, inflection_aliases,
    retrieval_tokens, assistant_history_intent)
from app.services.fact_identity import fact_fingerprint


@pytest.mark.parametrize('text', ["I'm jogging",'I’m jogging',"I'M jogging","we're jogging",'we’ve been jogging',
    "you'd been jogging","they'll be jogging","she's jogging"])
def test_pronoun_contractions_do_not_create_grammar_tokens(text):
    tokens=retrieval_tokens(text,normalise_inflections=True)
    assert 'jog' in tokens
    assert not tokens.intersection({'m','re','ve','d','ll','s'})


def test_literal_unit_and_project_m_are_not_removed():
    for normalise in [False,True]:
        terms=retrieval_tokens("I'm measuring 5m for Project M; literal m matters.",normalise_inflections=normalise)
        assert {'m','5m','project'}<=terms
        assert 'm' not in retrieval_tokens("I'm curious about the topic",normalise_inflections=normalise)
    assert 've' in retrieval_tokens('Project VE')


def test_source_canonical_fingerprint_is_not_changed():
    original="I'm jogging for Project M at 5m; Asha's notes."
    before=fact_fingerprint(original)
    assert 'i m' in before
    expanded=expand_pronoun_contractions(original)
    assert 'I am' in expanded and "Asha's" in expanded
    retrieval_tokens(original,normalise_inflections=True)
    assert fact_fingerprint(original)==before and original.startswith("I'm")


@pytest.mark.parametrize('word,base',[('jogging','jog'),('running','run'),('swimming','swim'),
    ('stopped','stop'),('planning','plan'),('baking','bake'),('baked','bake'),('cooking','cook'),
    ('walking','walk'),('studied','study'),('stories','story'),('classes','class'),('boxes','box'),('cars','car')])
def test_common_inflections_include_matching_base_without_deleting_original(word,base):
    aliases=inflection_aliases(word)
    assert word in aliases and base in aliases
    assert base in retrieval_tokens(word,normalise_inflections=True)


def test_numbers_compounds_stop_words_and_opt_out():
    assert {'12.5%','5m','project_m','c++'}<=retrieval_tokens('12.5% 5m project_M C++',normalise_inflections=True)
    assert 'run' not in retrieval_tokens('running',normalise_inflections=False)
    assert 'run' not in retrieval_tokens('running',normalise_inflections=True,stop_words={'run'})
    terms=retrieval_tokens('work-life',normalise_inflections=True)
    assert {'work-life','work','life'}<=terms


@pytest.mark.parametrize('question',[
    'Remind me of the place we talked about last time.',
    'What was the recipe we discussed before?',
    'Which tool did you recommend previously?',
    'Can you remind me of your earlier suggestions?',
    'You mentioned a hall; what was it called?',
    'We discussed some options yesterday; what were they?',
    "We’ve talked about a venue before. Please remind me.",
    'Remind me of that dessert shop from our conversation.',
    'What were your previous recommendations?',
])
def test_assistant_history_queries(question):
    assert assistant_history_intent(question)


@pytest.mark.parametrize('question',[
    'Can you recommend somewhere for a new gathering?',
    'Any tips on what to bake?',
    'I mentioned my running hobby. Suggest a new exercise.',
    'Recommend a place we have not discussed before.',
    "Suggest something we haven't discussed before.",
    'We never talked about venues; suggest a new one.',
    'I plan to visit next month. What should I do?',
    'I need your advice about a new issue.',
    'Remind me to buy ingredients tomorrow.',
])
def test_fresh_advice_or_negated_history_not_blanket_assistant_recall(question):
    assert not assistant_history_intent(question)


def test_question_date_footer_cannot_create_history_intent():
    assert not assistant_history_intent('Suggest a new topic.\nQuestion date: we discussed before')


def test_bad_inputs_are_not_silently_coerced():
    with pytest.raises(TypeError):retrieval_tokens(None)
    with pytest.raises(TypeError):assistant_history_intent(None)
