"""Development-only source warning for explicit later time replacements.

The caller must establish source ordering and pass only the cited original
source IDs. This warning is not a verdict and cannot prove relation absence.
"""
import re

_TIME = re.compile(r'\b(1[0-2]|0?[1-9])\s*(?:[:.]\s*(\d{2}))?\s*([ap])\s*\.?\s*m\.?', re.I)
_REPLACE = re.compile(r'\b(?:replac(?:e|es|ed|ing)|instead\s+of)\b', re.I)


def _times(text):
    return {(int(h), int(m or 0), ap.lower()) for h, m, ap in _TIME.findall(text)}


def explicit_later_update(messages, cited_ids, *, chronology_trusted=False):
    """Return an advisory reason, or None when no explicit case was found."""
    if not chronology_trusted:
        return 'Source ordering is not verified; review chronology before relying on the reference.'
    positions = {m['source_id']: i for i, m in enumerate(messages)}
    if len(positions) != len(messages) or not cited_ids or not set(cited_ids) <= positions.keys():
        raise ValueError('Source IDs are missing or duplicated')
    for source_id in cited_ids:
        old_index = positions[source_id]
        old_times = _times(messages[old_index]['text'])
        for later in messages[old_index + 1:]:
            later_times = _times(later['text'])
            if _REPLACE.search(later['text']) and old_times & later_times and len(later_times) >= 2:
                return 'A later source explicitly describes a time replacement involving the cited time; review the question and reference.'
    return None
