"""Conservative lexical identity for source facts, including quantitative values."""
import re


FACT_TOKENS = re.compile(
    r"[$€£¥]?[+-]?\d+(?:[.,]\d+)*(?:%|[a-zA-Z]+)?|[a-zA-Z][a-zA-Z0-9_+-]*"
)


def fact_fingerprint(value: str) -> str:
    """Ignore case and prose punctuation, preserving value tokens and order."""
    return ' '.join(FACT_TOKENS.findall(value.lower()))
