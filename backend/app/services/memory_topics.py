"""Shared conservative topic detection for deterministic memory components."""
import re

LANGUAGE_WORDS = frozenset({
    'python', 'java', 'rust', 'javascript', 'typescript', 'kotlin', 'swift',
    'golang', 'ruby', 'php', 'perl', 'scala', 'haskell', 'julia', 'lua', 'matlab',
})
_LANGUAGE = re.compile(r'\b(?:' + '|'.join(sorted(LANGUAGE_WORDS)) + r')\b', re.I)
_GO = re.compile(r'\b(?:prefer|favour|favorite|favourite|requires?|required|using|use)\s+(?:using\s+)?go\s*(?:[.!?,;]|$)|\bgo\s+(?:programming\s+)?language\b|(?<!to )\bgo\s+is\s+required\b', re.I)


def language_words(text: str) -> set[str]:
    words = {match.group().lower() for match in _LANGUAGE.finditer(text)}
    if _GO.search(text):
        words.add('go')
    return words


def is_language_topic(text: str) -> bool:
    return bool(language_words(text) or re.search(r'\b(?:programming|scripting)[ -]+languages?\b', text, re.I))
