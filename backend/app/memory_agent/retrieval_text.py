"""Pure lexical retrieval hints, never canonical facts or identity evidence.

Contractions are expanded only in a temporary search string. Inflection aliases
are candidate-matching hints: English morphology is ambiguous, so the original
term is retained. No function here edits source text, fingerprints or memories.
"""
from __future__ import annotations

import re
from collections.abc import Collection

from app.services.fact_identity import FACT_TOKENS

# Expansions remove grammatical fragments without banning a literal m/d/re/ve.
_PRONOUN_CONTRACTION = re.compile(
    r"\b(i|you|we|they|he|she|it|that|there|what|who)['’](m|re|ve|ll|d|s)\b", re.I)
_CONTRACTION_AUXILIARY = {'m':'am','re':'are','ve':'have','ll':'will','d':'would','s':'is'}
_ALLOWED_SUFFIXES = {'i':{'m','ve','ll','d'}, 'you':{'re','ve','ll','d'},
    'we':{'re','ve','ll','d'}, 'they':{'re','ve','ll','d'},
    'he':{'s','ll','d'}, 'she':{'s','ll','d'}, 'it':{'s','ll','d'},
    'that':{'s','ll','d'}, 'there':{'s','ll','d'}, 'what':{'s','ll','d'}, 'who':{'s','ll','d'}}
_GRAMMAR_STOP = frozenset({'i','my','we','our','you','your','they','their','them','he','his','she','her',
    'it','its','is','am','are','was','were','be','been','being','have','has','had','do','does','did',
    'will','would','shall','can','could','should','s'})
_SENTENCE_BOUNDARY = re.compile(r'[.!?;\n]+')


def expand_pronoun_contractions(text: str) -> str:
    """Retrieval-only auxiliary expansion; do not use to interpret tense/truth.

    'd and 's may mean had/has rather than would/is; their auxiliaries are stop
    words either way. Possessive names and literal unit/project labels remain.
    """
    if not isinstance(text, str): raise TypeError('Retrieval text must be a string.')
    def replace(match):
        pronoun,suffix=match.group(1),match.group(2).lower()
        return pronoun+' '+_CONTRACTION_AUXILIARY[suffix] if suffix in _ALLOWED_SUFFIXES[pronoun.lower()] else match.group(0)
    return _PRONOUN_CONTRACTION.sub(replace,text)


def inflection_aliases(term: str) -> set[str]:
    """Small deterministic English matching aliases, not a semantic lemmatizer."""
    aliases={term}
    # Preserve quantities, mixed identifiers and units exactly as tokenized.
    if not term.isalpha() or len(term)<4:return aliases
    if len(term)>4 and term.endswith('ies'):aliases.add(term[:-3]+'y')
    elif term.endswith(('ches','shes','xes','zes','sses','oes')):aliases.add(term[:-2])
    elif len(term)>3 and term.endswith('s') and not term.endswith(('ss','us','is')):aliases.add(term[:-1])
    if len(term)>5 and term.endswith('ied'):aliases.add(term[:-3]+'y')
    for suffix in ('ing','ed'):
        if not term.endswith(suffix) or len(term)-len(suffix)<3:continue
        stem=term[:-len(suffix)];doubled=(len(stem)>2 and stem[-1]==stem[-2] and stem[-1] in 'bdgmnprt')
        if doubled:stem=stem[:-1]
        aliases.add(stem)
        # Optional silent-e alias for simple CVC stems (baking -> bake).
        # Keep the undeduced original and bare stem because hoping/hopping-like
        # forms cannot be fully disambiguated without a lexicon.
        if not doubled and re.search(r'[b-df-hj-np-tv-z][aeiou][b-df-hj-np-tv-z]$',stem):aliases.add(stem+'e')
    return aliases


def retrieval_tokens(text: str, *, normalise_inflections: bool=False,
                     stop_words: Collection[str]=()) -> set[str]:
    """Tokenize temporary expanded text with the existing fact token alphabet.

    Integrating callers may pass their current _STOP | _RETRIEVAL_STOP. The
    underlying canonical _tokens/fingerprint functions must remain untouched.
    """
    expanded=expand_pronoun_contractions(text)
    stop=_GRAMMAR_STOP|{word.lower() for word in stop_words}
    terms={word.lower() for word in FACT_TOKENS.findall(expanded) if word.lower() not in stop}
    if not normalise_inflections:return terms
    terms-= {'bit','lately','find','ideas'}  # Grammatical fragments are removed by expansion, not global bans.
    terms|={part for term in terms for part in re.split(r'[-+/]',term) if part}
    return {alias for term in terms for alias in inflection_aliases(term) if alias not in stop}


# Shared with both packing and task-specific source-recall selection. Evidence
# roles still belong to the caller; an intent hint never verifies assistant text.
_EXPLICIT_ASSISTANT_RECALL = re.compile(
    r"\b(?:you|assistant)\s+(?:(?:had|have|previously|earlier|once)\s+)*"
    r"(?:recommended|suggested|told|said|gave|mentioned|provided|advised|explained|taught)\b|"
    r"\bdid\s+you\s+(?:recommend|suggest|say|tell|mention|provide|advise|explain|teach)\b",re.I)
_YOUR_REPLY_REFERENCE = re.compile(r"\byour\s+(?:(?:earlier|previous|prior|last)\s+)?"
    r"(?:recommendations?|suggestions?|advice|answers?)\b",re.I)
_YOUR_PAST_REPLY = re.compile(r"\byour\s+(?:earlier|previous|prior|last)\s+"
    r"(?:recommendations?|suggestions?|advice|answers?)\b",re.I)
_HISTORY_EXCHANGE = re.compile(
    r"\b(?:we|you|assistant)\s+(?:(?:had|have|previously|earlier|once)\s+)*"
    r"(?:talked\s+about|discussed|mentioned)\b",re.I)
_HISTORICAL_ANCHOR = re.compile(r'\b(?:last\s+time|earlier|previously|before|prior|last\s+conversation|our\s+(?:chat|conversation))\b',re.I)
_RECALL_REQUEST = re.compile(r'\b(?:remind\s+me|recall|remember|what\s+was|which\s+was|what\s+were|which\s+were)\b',re.I)
_NEGATED_HISTORY = re.compile(r"\b(?:never|not)\b.{0,35}\b(?:talked\s+about|discussed|mentioned|recommended|suggested)\b|"
    r"\b(?:did|have|had)\s+not\b.{0,20}\b(?:talk|discuss|mention|recommend|suggest)\w*\b",re.I)


def assistant_history_intent(question: str) -> bool:
    """Detect past conversational recall, without promoting all fresh advice.

    Clause-level heuristics, not a model of negation/coreference. Quoted example
    requests or complex scope can remain ambiguous; callers must retain source
    roles, evidence relevance and budgets rather than treat this as permission
    to answer from arbitrary old assistant text.
    """
    if not isinstance(question,str):raise TypeError('Question must be a string.')
    text=re.split(r'\nQuestion date:',question,flags=re.I)[0]
    text=expand_pronoun_contractions(text)
    # Normalize negative auxiliaries only for the intent negation check.
    text=re.sub(r"\b(did|have|had|do|does|was|were|is|are|can|could|would|should)n['’]t\b",r'\1 not',text,flags=re.I)
    for clause in _SENTENCE_BOUNDARY.split(text):
        if _NEGATED_HISTORY.search(clause):continue
        if _EXPLICIT_ASSISTANT_RECALL.search(clause) or _YOUR_PAST_REPLY.search(clause):return True
        if _RECALL_REQUEST.search(clause) and _YOUR_REPLY_REFERENCE.search(clause):return True
        # "We discussed..." is itself a past conversational anchor; fresh
        # "recommend/suggest..." alone has neither this nor a recall request.
        if _HISTORY_EXCHANGE.search(clause):return True
        if _RECALL_REQUEST.search(clause) and _HISTORICAL_ANCHOR.search(clause):return True
    return False
