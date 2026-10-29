import pytest
from scripts.ac2_explicit_time_update_guard_20261030 import explicit_later_update


def test_explicit_later_replacement_warns():
    rows = [{'source_id': 'old', 'text': 'My dog eats breakfast at 7 a.m.'},
            {'source_id': 'new', 'text': 'We moved her breakfast to 8 a.m. permanently, replacing the 7 a.m. time.'}]
    assert explicit_later_update(rows, ['old'], chronology_trusted=True)
    assert 'ordering is not verified' in explicit_later_update(rows, ['old'])


def test_instead_of_and_non_replacement():
    old = {'source_id': 'old', 'text': 'Cleanup begins at 10 a.m.'}
    update = {'source_id': 'new', 'text': 'The organizer changed the start to 11 a.m. instead of 10 a.m.'}
    assert explicit_later_update([old, update], ['old'], chronology_trusted=True)
    assert explicit_later_update([old, {'source_id': 'x', 'text': 'Lunch starts at 11 a.m.'}], ['old'], chronology_trusted=True) is None


def test_reject_duplicate_and_missing_ids():
    with pytest.raises(ValueError):
        explicit_later_update([{'source_id': 'x', 'text': 'At 7 a.m.'}] * 2, ['x'], chronology_trusted=True)
    with pytest.raises(ValueError):
        explicit_later_update([{'source_id': 'x', 'text': 'At 7 a.m.'}], ['missing'], chronology_trusted=True)


def test_exploratory_guard_has_known_scope_and_wording_limitations():
    old = {'source_id': 'old', 'text': 'My dog eats breakfast at 7 a.m.'}
    unrelated = {'source_id': 'new', 'text': 'The meeting moved to 8 a.m., replacing its old 7 a.m. time.'}
    # Matching the old time alone does not prove the two events are related.
    assert explicit_later_update([old, unrelated], ['old'], chronology_trusted=True)
    paraphrased = {'source_id': 'new', 'text': 'Dog breakfast was rescheduled from 7 a.m. to 8 a.m.'}
    # This phrase indicates an update but the narrow lexical rule misses it.
    assert explicit_later_update([old, paraphrased], ['old'], chronology_trusted=True) is None
