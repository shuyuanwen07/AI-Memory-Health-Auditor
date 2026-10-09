"""Answer-time eligibility observations, separate from current trace states."""
from app.services.evidence_correspondence import evidence_units


VERSION = "answer-time-memory-availability-v2"


def availability(reference, records, ranking, supplied=None):
    def units(items):
        return set().union(*(evidence_units(r) for r in items))
    expected = units(reference)
    observed = {}
    for entry in ranking or []:
        key = entry.get('memory_id')
        if key in observed:  # Ambiguous legacy duplicate evidence is unknown.
            observed[key] = None
        else:
            observed[key] = entry
    statuses = []
    for record in records:
        entry = observed.get(record.memory_id)
        status = 'unobserved'
        if entry and type(entry.get('eligible')) is bool:
            if entry['eligible']:
                status = 'eligible'
            elif 'capacity_evicted_excluded' in str(entry.get('reason', '')):
                status = 'capacity_excluded'
            elif 'superseded_excluded_by_strategy' in str(entry.get('reason', '')):
                status = 'superseded_excluded'
            elif 'diagnostic_packet_excluded' in str(entry.get('reason', '')):
                status = 'diagnostic_excluded'
            else:
                status = 'excluded_other'
        statuses.append((record,status))
    groups = {status:units([r for r,s in statuses if s==status]) for status in {
        'eligible','capacity_excluded','superseded_excluded','diagnostic_excluded','excluded_other','unobserved'}}
    known = set().union(*(v for k,v in groups.items() if k!='unobserved'))
    facts = []
    for index, fact in enumerate(reference,1):
        wanted = evidence_units(fact)
        related = [{'record_text':r.canonical_value,'eligibility':status}
            for r,status in statuses if wanted.intersection(evidence_units(r))]
        facts.append({'reference_label':f'Supporting fact {index}','reference_text':fact.canonical_value,
            'matching_record_eligibility':related})
    # Duplicate exact facts can be both evicted and eligible. An eligible copy
    # prevents claiming that this required unit is unavailable by capacity.
    unavailable_evicted = (expected & groups['capacity_excluded']) - groups['eligible']
    # A historical-only observation must not conceal a second matching copy
    # with unknown eligibility or a different exclusion reason.
    historical_only = (expected & groups['superseded_excluded']) - set().union(
        *(value for status, value in groups.items() if status != 'superseded_excluded'))
    historical_missing = historical_only - units(supplied) if supplied is not None else None
    return {'version':VERSION,'expected_fact_units':len(expected),'observed_fact_units':len(expected&known),
        'eligible_fact_units':len(expected&groups['eligible']),
        'capacity_excluded_fact_units':len(unavailable_evicted),
        'superseded_only_excluded_fact_units':len(historical_only),
        'superseded_only_missing_fact_units':len(historical_missing) if historical_missing is not None else None,
        'other_excluded_fact_units':len((expected & set().union(groups['superseded_excluded'],groups['diagnostic_excluded'],groups['excluded_other']))-groups['eligible']),
        'facts':facts}
