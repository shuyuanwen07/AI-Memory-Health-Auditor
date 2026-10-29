"""Conservative subject/scope hints for location claims.

This is not a geocoder or a semantic parser. A first-person source can discuss
another person's or organisation's location; unknown subjects must be reviewed.
"""
import re

_WORK = re.compile(
    r'\b(?:my|the user(?:[\'’]s)?)\s+(?:regular\s+|current\s+)?(?:work|office|workplace|job)\s+location\b'
    r'|\b(?:i|the user)\s+(?:currently\s+|normally\s+|usually\s+)?work(?:s)?\s+(?:in|at|from)\b', re.I)
_USER = re.compile(
    r'\b(?:i|the user)\s+(?:(?:now|currently|usually)\s+)?(?:live|lives|reside|resides|am based|is based|moved|relocated)\s+(?:in|at|to)\b'
    r'|\bmy\s+(?:current\s+)?(?:home|residential|personal)\s+location\s+(?:is|:)\b'
    r'|\bmy\s+(?:current\s+)?(?:city|location)\s+(?:is|:)\b'
    r'|\bthe user(?:[\'’]s)?\s+(?:current\s+)?(?:city|location)\s+(?:is|:)\b', re.I)
_REVERSE = re.compile(r"^(?:[A-Za-z][A-Za-z'-]*\s+){1,4}is\s+my\s+(?:current\s+)?(?:city|location)\s*[.!?]*$", re.I)
_NEGATED = re.compile(r"\b(?:i|the user)\s+(?:do(?:es)?\s+not|don't|doesn't|never)\s+(?:live|reside|move|relocate)\b|\b(?:it is|it's)\s+not\s+true\s+that\b[^.!?]{0,80}\b(?:i|the user)\b", re.I)
_REPORTED = re.compile(r'\b(?:says?|said|claims?|claimed|suggested|reported|told|believes?|wrote|writes?|written)\b[^.!?]{0,60}\b(?:i|the user)\b', re.I)
_TEMPORARY = re.compile(
    r'\b(?:for|during)\s+(?:(?:a|the)\s+)?(?:\d+|one|two|three|four|five|six|seven|short)'
    r'(?:[ -]+)(?:days?|weeks?|nights?)(?:[ -]+(?:trip|conference|visit|holiday))?\b'
    r'|\b(?:for|during)\s+(?:a|the)\s+(?:(?:temporary|short|brief)\s+(?:trip|visit|conference|stay)|weekend)\b', re.I)
_OTHER = re.compile(
    r'\b(?:the|my|our|a|his|her|their)\s+(?:cat|dog|pet|team|company|organization|organisation|project|friend|sister|brother|partner|child|mother|father|office|service)\b'
    r'[^.;!?]{0,35}\b(?:moved|relocated|lives|is located|is based)\s+(?:in|at|to)\b', re.I)


def classify_location_subject(text: str) -> str:
    """Return ``user_residence``, ``user_work``, ``other`` or ``unknown``.

    Mixed actors, negation, labels without an actor and unsupported forms are
    deliberately unresolved rather than assigned to the user.
    """
    work = _WORK.search(text)
    if _NEGATED.search(text) or _REPORTED.search(text) or _TEMPORARY.search(text):
        return 'unknown'
    user = _USER.search(text) or _REVERSE.search(text)
    other = _OTHER.search(text)
    if sum(bool(value) for value in (work, user, other)) > 1:
        return 'unknown'
    if work:
        return 'user_work'
    if user:
        return 'user_residence'
    if other:
        return 'other'
    return 'unknown'
