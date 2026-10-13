from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as Row

from app.services.reviewer_identity import distinct_reviewers, unique_independent_reviews


def test_name_variants_and_blank_names_do_not_create_independent_reviewers():
    assert distinct_reviewers([Row(reviewer_label=name) for name in [' A ', 'a', 'Straße', 'STRASSE', ' ']]) == {'a', 'strasse'}


def test_legacy_aliases_preserve_original_rows_but_only_latest_label_counts():
    now = datetime.now(timezone.utc)
    old = Row(review_id='old', reviewer_label='Reviewer A', review_role='independent', updated_at=now, human_passed=True)
    new = Row(review_id='new', reviewer_label=' reviewer a ', review_role='independent', updated_at=now + timedelta(seconds=1), human_passed=False)
    reference = Row(review_id='reference', reviewer_label='B', review_role='reference', updated_at=now, human_passed=True)
    rows = [old, new, reference]
    assert unique_independent_reviews(rows) == [new]
    assert len(rows) == 3
    assert old.reviewer_label == 'Reviewer A' and old.human_passed is True
