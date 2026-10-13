from types import SimpleNamespace as Row

from app.services.memory_availability import availability


def record(key,value='Use Go',source='MSG1',state='ACTIVE'):
    return Row(memory_id=key,canonical_value=value,source_message_ids=[source],lifecycle_state=state)


def test_answer_time_capacity_exclusion_is_separate_from_current_state():
    fact=record('reference')
    result=availability([fact],[record('target',state='ACTIVE')],[{'memory_id':'target','eligible':False,'reason':'capacity_evicted_excluded'}])
    assert result['capacity_excluded_fact_units']==1 and result['eligible_fact_units']==0
    assert result['facts'][0]['matching_record_eligibility'][0]['eligibility']=='capacity_excluded'
    # Current EVICTED state alone must never fabricate answer-time evidence.
    unknown=availability([fact],[record('target',state='EVICTED')],[])
    assert unknown['observed_fact_units']==unknown['capacity_excluded_fact_units']==0


def test_eligible_duplicate_fact_prevents_claiming_capacity_unavailability():
    result=availability([record('ref')],[record('old'),record('copy')],[
        {'memory_id':'old','eligible':False,'reason':'capacity_evicted_excluded'},
        {'memory_id':'copy','eligible':True}])
    assert result['eligible_fact_units']==1 and result['capacity_excluded_fact_units']==0


def test_different_source_or_fact_never_counts_as_exact_availability():
    result=availability([record('ref')],[record('old',value='Use Java'),record('other',source='MSG2')],[
        {'memory_id':'old','eligible':False,'reason':'capacity_evicted_excluded'},
        {'memory_id':'other','eligible':True}])
    assert result['observed_fact_units']==result['eligible_fact_units']==result['capacity_excluded_fact_units']==0


def test_missing_duplicate_and_nonboolean_eligibility_stay_unknown():
    for ranking in [[],[{'memory_id':'target','eligible':'false','reason':'capacity_evicted_excluded'}],
        [{'memory_id':'target','eligible':False,'reason':'capacity_evicted_excluded'},{'memory_id':'target','eligible':True}]]:
        result=availability([record('ref')],[record('target',state='EVICTED')],ranking)
        assert result['observed_fact_units']==result['capacity_excluded_fact_units']==0


def test_superseded_and_diagnostic_exclusions_are_not_capacity_removal():
    for reason,status in [('superseded_excluded_by_strategy','superseded_excluded'),('diagnostic_packet_excluded','diagnostic_excluded')]:
        result=availability([record('ref')],[record('target')],[{'memory_id':'target','eligible':False,'reason':reason}])
        assert result['other_excluded_fact_units']==1 and result['capacity_excluded_fact_units']==0
        assert result['facts'][0]['matching_record_eligibility'][0]['eligibility']==status


def test_historical_missing_units_are_checked_against_actual_supply_and_copies():
    old = record('old', value='Use MySQL')
    current = record('current', value='Use PostgreSQL')
    ranking = [{'memory_id':'old','eligible':False,'reason':'superseded_excluded_by_strategy'},
               {'memory_id':'current','eligible':True}]
    expected = [old, current]
    assert availability(expected, expected, ranking, [current])['superseded_only_missing_fact_units'] == 1
    assert availability(expected, expected, ranking, [old])['superseded_only_missing_fact_units'] == 0
    assert availability(expected, expected, ranking)['superseded_only_missing_fact_units'] is None
    # An unobserved copy makes the historical-only attribution ambiguous.
    assert availability(expected, [*expected, record('copy', value='Use MySQL')], ranking,
                        [current])['superseded_only_missing_fact_units'] == 0
