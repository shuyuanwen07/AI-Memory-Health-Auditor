"""Isolated, conservative advisory for relative-date questions.

Not used by the application or the completed studies. A recorded message time
can be an inferred ordering time, particularly in older imports.
"""
import re

_RELATIVE = re.compile(
    r'\b(?:today|tomorrow|yesterday|tonight|this\s+(?:morning|afternoon|evening|week|month|year)|'
    r'next\s+(?:week|month|year)|last\s+(?:week|month|year)|'
    r'in\s+\d+\s+(?:days?|weeks?|months?))\b|今天|明天|昨天|今晚|本周|下周|上周',
    re.IGNORECASE,
)

def relative_date_advice(question: str, reference: str, source_texts: list[str]) -> str | None:
    """Ask for source-date review; never decide that the question is invalid."""
    if any(_RELATIVE.search(text or '') for text in (question, reference, *source_texts)):
        return ('A relative date appears in the question, answer or source. '
                'Verify its real-world anchor against the original conversation; '
                'an ordering timestamp alone may have been generated.')
    return None
