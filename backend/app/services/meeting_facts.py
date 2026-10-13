"""Bounded meeting-platform values, shared by extraction and lexical review."""
import re

PLATFORM_PATTERN = r"(?:Zoom|(?:Microsoft\s+)?Teams|Webex|Google\s+Meet)"
PLATFORM_NAMES = frozenset({'zoom', 'teams', 'webex', 'google meet'})
_EXCLUSIVE_PLATFORM = re.compile(rf"\bonly\s+(?P<value>{PLATFORM_PATTERN})\s+(?P<time>is|will\s+be)\s+(?:allowed|permitted)\b", re.I)


def is_meeting_platform_topic(text: str) -> bool:
    """Recognise a bounded platform clause, regardless of name/meeting order."""
    meeting = r"\b(?:meetings?|reviews?|conferences?|calls?)\b"
    platform = rf"\b(?:platform|held|video|{PLATFORM_PATTERN})\b"
    return bool(re.search(rf"(?:{meeting}[^.;!?]{{0,100}}{platform}|{platform}[^.;!?]{{0,100}}{meeting})", text, re.I))


def platform_value(text: str) -> str | None:
    """Read an explicit positive requirement, not an unresolved pair of names."""
    for match in re.finditer(rf"\b(?:uses?|requires?|(?:must|should)\s+use|held\s+(?:on|via))\s+(?P<value>{PLATFORM_PATTERN})\b", text, re.I):
        prefix = re.split(r'[.!?;\n]', text[:match.start()])[-1]
        if re.search(r"\b(?:not|never|no\s+longer)\s+(?:\w+\s+){0,2}$", prefix, re.I):
            continue
        return re.sub(r'^microsoft\s+', '', match['value'].lower())
    return None


def exclusive_platform_value(text: str) -> str | None:
    """Recognise an explicit allowed-only platform without weakening its source text."""
    for match in _EXCLUSIVE_PLATFORM.finditer(text):
        prefix = re.split(r'[.!?;\n]', text[:match.start()])[-1]
        # Not-only is inclusive; conditional statements are not unconditional rules.
        if re.search(r"\b(?:not|if|unless|whether|perhaps|maybe|suppose|imagine)\b", prefix, re.I):
            continue
        return re.sub(r'^microsoft\s+', '', match['value'].lower())
    return None


def equivalent_exclusive_platform_rules(left: str, right: str) -> bool:
    """Prove only a bounded wording equivalence; retain all other scope/qualifiers.

    Moving the identical scope before/after the only-allowed clause and using
    allowed/permitted or Teams/Microsoft Teams does not create a contradiction.
    Changed qualifiers, time, multiple clauses or unknown forms are not certified.
    """
    def key(text: str) -> tuple[str, str, str] | None:
        value = exclusive_platform_value(text)
        matches = list(_EXCLUSIVE_PLATFORM.finditer(text))
        if value is None or len(matches) != 1:
            return None
        match = matches[0]
        remainder = text[:match.start()] + ' ' + text[match.end():]
        scope = re.sub(r'[^\w]+', ' ', remainder.casefold()).strip()
        time = re.sub(r'\s+', ' ', match['time'].casefold())
        return value, scope, time
    left_key, right_key = key(left), key(right)
    return left_key is not None and left_key == right_key
