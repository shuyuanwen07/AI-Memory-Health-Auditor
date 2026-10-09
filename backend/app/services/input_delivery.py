"""Observe selection, profile exclusions and final supply without inferring reliance."""
from app.services.evidence_correspondence import evidence_units


def input_delivery(reference, records, selected_ids, sent_ids, ranking):
    def units(items):
        return set().union(*(evidence_units(item) for item in items))
    by_id = {record.memory_id: record for record in records}
    expected = units(reference)
    selected = units([by_id[key] for key in selected_ids or [] if key in by_id]) if selected_ids is not None else None
    supplied = units([by_id[key] for key in sent_ids or [] if key in by_id]) if sent_ids is not None else None
    observations = {}
    for entry in ranking or []:
        key = entry.get('memory_id')
        observations[key] = None if key in observations else entry
    def excluded(marker):
        return units([record for key, record in by_id.items() if
            (entry := observations.get(key)) and entry.get('eligible') is True and
            entry.get('selected') is False and marker in str(entry.get('reason', ''))])
    already_present = (selected or set()) | (supplied or set())
    return {'version': 'input-stage-correspondence-v1', 'expected_fact_units': len(expected),
        'retrieved_fact_units': len(expected & selected) if selected is not None else None,
        'complete_retrieved_match': bool(expected) and selected is not None and expected.issubset(selected),
        'selected_not_supplied_fact_units': len((expected & selected) - supplied) if selected is not None and supplied is not None else None,
        'context_budget_excluded_fact_units': len((expected & excluded('profile_context_budget_excluded')) - already_present),
        'profile_filter_excluded_fact_units': len((expected & excluded('profile_excluded_')) - already_present),
        'notice': 'Exact source-and-fact matches are proxies. Paraphrases and duplicate facts may supply the same meaning; these observations do not establish the sole cause of failure.'}
