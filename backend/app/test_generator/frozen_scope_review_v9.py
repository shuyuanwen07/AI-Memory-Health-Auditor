"""Versioned, opt-in advisory checks for a saved question suite.

The absence of a warning does not certify question validity. Source messages
must be the original, same-conversation user messages, not generated memories.
"""
import re

VERSION = 'source-scope-review-v9'
_GENERIC = re.compile(r"^What is the user's recorded stored information(?:\s+[^?]+)?\?", re.I)
_PROJECT = re.compile(r'\bfor the\s+([A-Z][A-Za-z0-9-]*)\s+project\b')
_BROAD_REQUIREMENT = re.compile(r'^For the current task, what is the recorded requirement about [^?]+\?', re.I)
_BROAD_PREFERENCE = re.compile(r"^What is the user's recorded (?:preference|communication style)\?", re.I)
_BROAD_SUBJECT = re.compile(r'^What is recorded about\s+([^?]{1,80})\?', re.I)
_CURRENT_TASK = re.compile(r"^What is the user's recorded current task\?", re.I)
_EXPLICIT_TASK = re.compile(r"\b(?:my|the user(?:'s)?|the)\s+current task\s*(?:is|:)\s*\S", re.I)
_SECOND_PERSON_SOURCE = re.compile(r"\b(?:you\s+(?:said|mentioned|told|stated)|did\s+you\s+(?:say|mention|tell|state))\b", re.I)
_TIME = re.compile(r'\b(1[0-2]|0?[1-9])\s*(?:[:.]\s*(\d{2}))?\s*([ap])\s*\.?\s*m\.?', re.I)
_TIME_REPLACEMENT = re.compile(
    r'\b(?:replac(?:e|es|ed|ing)|instead\s+of)\b'
    r'|\b(?:changed|moved|shifted|rescheduled)\b[^.!?]{0,80}\bfrom\b', re.I)
_REQUIREMENT = re.compile(
    r'\b(?:requires?|required|must|mandatory|needs? to|has to)\b'
    r'|\bfor\b[^.!?;]{0,100}\bonly\s*[,;:]\s*(?:use|choose|send|bring|provide|make|keep|avoid|include|follow|prepare)\b', re.I)


def later_explicit_time_update_advice(source_ids: set[str], messages: list[dict]) -> str | None:
    """Flag possible replacement later in supplied message order, not a validity verdict.

    A shared time does not establish event identity, and imported order is not
    proof of real-world chronology. Ambiguous order is not used for inference.
    """
    ids = [message['source_id'] for message in messages]
    sequences = [message['sequence'] for message in messages]
    if (not source_ids or len(ids) != len(set(ids)) or len(sequences) != len(set(sequences))
            or not source_ids.issubset(set(ids))):
        return None
    ordered = sorted(messages, key=lambda message: message['sequence'])
    positions = {message['source_id']: index for index, message in enumerate(ordered)}
    def times(text):
        return {(int(hour), int(minute or 0), suffix.lower()) for hour, minute, suffix in _TIME.findall(text)}
    for source_id in source_ids:
        index = positions[source_id]
        cited_times = times(ordered[index]['text'])
        for later in ordered[index + 1:]:
            later_times = times(later['text'])
            if _TIME_REPLACEMENT.search(later['text']) and cited_times & later_times and len(later_times) >= 2:
                return ('A later message in the supplied conversation mentions a replacement involving a cited time. '
                        'Check whether it concerns the same event and affects this question or reference.')
    return None


def scope_warning(prompt: str, dimension: str, source_texts: list[str], *, source_complete: bool,
                  related_topic_count: int = 1, conversation_source_texts: list[str] | None = None) -> str | None:
    """Return a reason for human review; never infer relation completeness.

    Even a complete set of source messages does not prove that extracted
    relationships are exhaustive. Relation-dependent tests therefore require
    review instead of assuming that no recorded relation means none exists.
    """
    if not source_complete or not source_texts or any(not text.strip() for text in source_texts):
        return 'Original source messages are missing; check this question against its source before use.'
    if _GENERIC.search(prompt):
        return 'This broad question may not identify a single fact. Check the intended scope against the source.'
    if _SECOND_PERSON_SOURCE.search(prompt):
        return 'The question says “you” about a prior statement. Check whether it means the user or the answering assistant.'
    if dimension == 'accuracy' and related_topic_count > 1:
        return 'Several confirmed memories share this topic. Check which source fact the question asks about.'
    subject = _BROAD_SUBJECT.search(prompt)
    if subject and conversation_source_texts:
        # Count distinct source sentences which explicitly mention the same
        # subject. Pronouns and semantic equivalence are intentionally not
        # inferred; absence of a warning cannot establish uniqueness.
        name = ' '.join(subject.group(1).split())
        if name and len(name.split()) <= 8:
            pattern = re.compile(r'(?<!\w)' + r'\s+'.join(map(re.escape, name.split())) + r'(?!\w)', re.I)
            statements = {sentence.strip().casefold() for text in conversation_source_texts
                          for sentence in re.split(r'[.!?;]+', text)
                          if sentence.strip() and pattern.search(sentence)}
            if len(statements) > 1:
                return 'Several source statements mention this subject. Check which fact the question asks about.'
    if _CURRENT_TASK.search(prompt) and any(_REQUIREMENT.search(text) for text in source_texts) \
            and not any(_EXPLICIT_TASK.search(text) for text in source_texts):
        return 'The cited source describes a requirement but does not explicitly identify the current task. Check the question and reference.'
    match = _PROJECT.search(prompt)
    if match:
        name = re.escape(match.group(1))
        named = re.compile(r'\b(?:[Pp]roject\s+' + name + r'|' + name + r'\s+(?:project|capstone|backend|deployment|logs|service))\b')
        if not any(named.search(text) for text in source_texts):
            return 'The named project is not explicit in the source. Verify the intended scope.'
    if dimension in {'freshness', 'conflict_resolution', 'appropriate_use'}:
        return 'Verify the relevant source statements and their relationship; the relationship list may be incomplete.'
    if _BROAD_REQUIREMENT.search(prompt) or _BROAD_PREFERENCE.search(prompt):
        return 'This broad question may not identify which task or preference is intended. Verify the scope in the source.'
    return None
