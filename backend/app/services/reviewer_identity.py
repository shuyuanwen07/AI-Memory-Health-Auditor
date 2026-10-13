"""Pseudonym consistency only; names cannot authenticate human independence."""
from datetime import timezone


def reviewer_identity(label: str) -> str:
    return label.strip().casefold()


def distinct_reviewers(reviews) -> set[str]:
    return {identity for review in reviews if (identity := reviewer_identity(review.reviewer_label))}


def unique_independent_reviews(reviews) -> list:
    """Preserve stored rows; count only the latest label for each pseudonym."""
    latest = {}
    def order(review):
        timestamp = review.updated_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp, getattr(review, 'review_id', getattr(review, 'id', ''))
    for review in reviews:
        if getattr(review.review_role, 'value', review.review_role) != 'independent':
            continue
        key = reviewer_identity(review.reviewer_label)
        if key and (key not in latest or order(review) > order(latest[key])):
            latest[key] = review
    return list(latest.values())
