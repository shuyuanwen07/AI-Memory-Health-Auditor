"""Calendar-reference helpers use source text only and never assert event truth."""
from datetime import datetime, timezone

import pytest

from app.memory_agent.temporal_context import query_date, query_window, temporal_question, temporal_references


def test_relative_days_weeks_and_spans():
    anchor = datetime(2025, 7, 18, 9, tzinfo=timezone.utc)
    text = "Yesterday I unpacked; I travelled two weeks ago and called today."
    refs = temporal_references(text, anchor)
    assert [r["resolved_start"] for r in refs] == ["2025-07-17", "2025-07-04", "2025-07-18"]
    assert all(text[s:e] == r["phrase"] for r in refs for s, e in [r["span"]])
    assert all(r["anchor_basis"] == "source_observed_at" for r in refs)


@pytest.mark.parametrize("anchor,phrase,expected", [
    (datetime(2024, 3, 31), "a month ago", "2024-02-29"),
    (datetime(2024, 2, 29), "one year ago", "2023-02-28"),
    (datetime(2025, 1, 31), "two months ago", "2024-11-30"),
    (datetime(2025, 7, 18), "twelve weeks ago", "2025-04-25"),
])
def test_calendar_offsets(anchor, phrase, expected):
    ref = temporal_references(phrase, anchor)[0]
    assert ref["resolved_start"] == ref["resolved_end"] == expected
    assert ref["approximate"] == (ref["precision"] in {"month", "year"})


def test_last_intervals_and_approximate_phrase():
    anchor = datetime(2025, 1, 8)
    refs = temporal_references("last week; last month; last year; about three days ago", anchor)
    assert [(r["resolved_start"], r["resolved_end"]) for r in refs] == [
        ("2024-12-30", "2025-01-05"), ("2024-12-01", "2024-12-31"),
        ("2024-01-01", "2024-12-31"), ("2025-01-05", "2025-01-05")]
    assert refs[-1]["approximate"]


def test_recollection_does_not_assert_trip_date():
    ref = temporal_references("I was thinking about my trip today and remembered going with my aunt.",
                              datetime(2025, 6, 2))[0]
    assert ref["resolved_start"] == "2025-06-02"
    assert "not a verified event date" in ref["caution"]
    assert "recollection" in ref["caution"]
    assert "event_date" not in ref


def test_missing_or_invalid_anchor_and_unbounded_numbers_are_safe():
    assert temporal_references("yesterday", None) == []
    assert temporal_references("999999999999999999999 days ago", datetime(2025, 1, 1)) == []
    assert temporal_references("twelve years ago", datetime(5, 1, 1)) == []
    assert temporal_references("days ago", datetime(2025, 1, 1)) == []


def test_query_metadata_is_explicit_final_line_only():
    assert query_date("When did I leave?\nQuestion date: 2025-07-18T09:00:00Z") == datetime(2025, 7, 18, 9, tzinfo=timezone.utc)
    assert query_date("On 2025-07-18 I left.") is None
    assert query_date("Question date: invalid") is None
    assert query_date("Question date: 2025-07-18\nextra text") is None


def test_question_window_and_temporal_detection():
    prompt = "What did I finish two weeks ago?\nQuestion date: 2025-07-18T09:00:00+00:00"
    assert temporal_question(prompt)
    assert query_window(prompt)["resolved_start"] == "2025-07-04"
    assert query_window(prompt)["anchor_basis"] == "question_date"
    assert query_window("What happened yesterday?") is None
    assert temporal_question("Which task did I finish first?")
    assert temporal_question("What is the order of my visits?")
    assert not temporal_question("What colour do I like?\nQuestion date: 2025-07-18T09:00:00Z")


@pytest.mark.parametrize("phrase,start,end", [
    ("this week", "2024-02-26", "2024-03-03"),
    ("this month", "2024-02-01", "2024-02-29"),
    ("this year", "2024-01-01", "2024-12-31"),
    ("current calendar year", "2024-01-01", "2024-12-31"),
])
def test_current_periods_are_calendar_ranges_not_event_dates(phrase, start, end):
    anchor = datetime(2024, 2, 29, 12, tzinfo=timezone.utc)
    reference = temporal_references(phrase, anchor)[0]
    assert (reference["resolved_start"], reference["resolved_end"]) == (start, end)
    assert "not a verified event date" in reference["caution"]
    question = f"How many exhibitions have I attended in {phrase}?\nQuestion date: {anchor.isoformat()}"
    assert temporal_question(question)
    window = query_window(question)
    assert window["resolved_start"] == start and window["resolved_end"] == end
    assert window["anchor_basis"] == "question_date"


def test_count_without_period_does_not_become_temporal_from_metadata():
    assert not temporal_question("How many books do I own?\nQuestion date: 2024-02-29T12:00:00Z")


@pytest.mark.parametrize("day", [3, 4, 5, 6, 7])
def test_last_weekend_weekday_source_anchor_not_unrelated_date_clause(day):
    text = "On 2031-10-12 I wrote a note; I recalled an outing last weekend."
    ref = temporal_references(text, datetime(2025, 3, day, 13))[0]
    assert ref["phrase"] == "last weekend"
    assert text[slice(*ref["span"])] == ref["phrase"]
    assert (ref["resolved_start"], ref["resolved_end"]) == ("2025-03-01", "2025-03-02")
    assert ref["precision"] == "weekend" and not ref["approximate"]
    assert ref["anchor_basis"] == "source_observed_at"
    assert "not a verified event date" in ref["caution"]
    assert "event_date" not in ref and "attendance" not in ref


@pytest.mark.parametrize("day", [8, 9])
def test_last_weekend_on_weekend_preserves_two_noncontinuous_candidates(day):
    ref = temporal_references("I thought about the exhibition lastweekend.", datetime(2025, 3, day))[0]
    assert ref["phrase"] == "lastweekend"
    assert ref["candidate_ranges"] == [
        {"resolved_start": "2025-03-01", "resolved_end": "2025-03-02"},
        {"resolved_start": "2025-03-08", "resolved_end": "2025-03-09"},
    ]
    assert (ref["resolved_start"], ref["resolved_end"]) == ("2025-03-01", "2025-03-09")
    assert ref["range_kind"] == "candidate_envelope" and ref["approximate"]
    assert ref["ambiguity"] == "weekend_day_last_weekend_reference"
    assert "intervening weekdays are not candidate dates" in ref["caution"]
    assert "future Sunday" in ref["caution"]


def test_last_weekend_year_boundary_and_local_timezone_calendar():
    ref = temporal_references("last weekend", datetime.fromisoformat("2023-01-01T00:30:00+14:00"))[0]
    assert ref["candidate_ranges"] == [
        {"resolved_start": "2022-12-24", "resolved_end": "2022-12-25"},
        {"resolved_start": "2022-12-31", "resolved_end": "2023-01-01"},
    ]
    # This instant is Sunday in its supplied timezone but Monday in UTC.
    ref = temporal_references("last weekend", datetime.fromisoformat("2025-03-09T23:30:00-12:00"))[0]
    assert ref["ambiguity"] == "weekend_day_last_weekend_reference"
    assert ref["candidate_ranges"][-1]["resolved_end"] == "2025-03-09"


def test_last_weekend_question_window_preserves_ambiguity_and_metadata_boundary():
    prompt = "Which exhibit did I see lastweekend?\nQuestion date: 2023-01-01T12:00:00Z"
    assert temporal_question(prompt)
    assert temporal_question("When did I attend the exhibit?")
    window = query_window(prompt)
    assert window["anchor_basis"] == "question_date"
    assert window["range_kind"] == "candidate_envelope"
    assert len(window["candidate_ranges"]) == 2
    assert "intervening weekdays" in window["caution"]
    assert not temporal_question("Which colour?\nQuestion date: lastweekend")
    assert query_window("Which exhibit last weekend?") is None


@pytest.mark.parametrize("value", [None, 17, {}, [], "lastweekender", "blastweekend", "last weekendish", "next weekend"])
def test_last_weekend_unsupported_inputs_do_not_fabricate_dates(value):
    assert temporal_references(value, datetime(2025, 3, 8)) == []


def test_last_weekend_missing_anchor_and_calendar_underflow_are_safe():
    assert temporal_references("last weekend", "2025-03-08") == []
    assert temporal_references("last weekend", datetime(1, 1, 1)) == []
    assert temporal_references("last weekend", None) == []
