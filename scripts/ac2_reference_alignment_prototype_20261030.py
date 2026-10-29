"""Conservative, post-outcome prototype for reference-question alignment.

This is an advisory flag, not a validity decision. Known samples informed it;
it is neither a product implementation nor an independent evaluation.
"""
import re

_OS_QUESTION = re.compile(r"\boperating system\b", re.I)
_OS_EVIDENCE = re.compile(r"\b(?:operating system|os|windows|macos|linux|ubuntu|fedora|debian|android|ios|chrome\s*os)\b", re.I)
_WORK_QUESTION = re.compile(r"\bworking arrangement\b", re.I)
_WORK_EVIDENCE = re.compile(r"\b(?:working arrangement|work(?:s|ing)?\s+(?:from home|remotely|on[ -]site|in the office|at the office)|remote work|hybrid work|in[ -]office work)\b", re.I)


def warning(question, source_texts):
    """Flag weak lexical support; absence of a flag cannot certify validity."""
    source = ' '.join(source_texts)
    if _OS_QUESTION.search(question) and not _OS_EVIDENCE.search(source):
        return 'No explicit operating-system term in the cited source; check question and reference.'
    if _WORK_QUESTION.search(question) and not _WORK_EVIDENCE.search(source):
        return 'No explicit work-arrangement term in the cited source; check question and reference.'
    return None
