"""Auditor-only correspondence checks; exact text is not semantic equivalence."""
import re


VERSION = "source-fact-correspondence-v1"


def evidence_units(record):
    value = " ".join(re.findall(r"\w+", record.canonical_value.casefold()))
    return {(source, value) for source in record.source_message_ids or []} if value else set()


def correspondence(reference, stored, supplied):
    """Preserve source overlap and exact fact overlap as separate observations."""
    def units(records):
        return set().union(*(evidence_units(r) for r in records))
    expected = units(reference)
    kept = units(stored)
    sent = units(supplied) if supplied is not None else None
    facts = []
    for index, fact in enumerate(reference, 1):
        sources = set(fact.source_message_ids or [])
        related_stored = [r for r in stored if sources.intersection(r.source_message_ids or [])]
        related_sent = [r for r in supplied or [] if sources.intersection(r.source_message_ids or [])]
        facts.append({"reference_label": f"Supporting fact {index}", "reference_text": fact.canonical_value,
            "stored_related_text": list(dict.fromkeys(r.canonical_value for r in related_stored)),
            "supplied_related_text": list(dict.fromkeys(r.canonical_value for r in related_sent)) if supplied is not None else None})
    return {"version": VERSION, "expected_fact_units": len(expected),
        "stored_fact_units": len(expected & kept),
        "supplied_fact_units": len(expected & sent) if sent is not None else None,
        "complete_stored_match": bool(expected) and expected.issubset(kept),
        "complete_supplied_match": bool(expected) and sent is not None and expected.issubset(sent),
        "facts": facts}
