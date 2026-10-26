"""Resolve conversational time expressions without asserting event dates.

These helpers describe references in untrusted text.  In particular, a message
which says "I was thinking about the trip today" does not date the trip.
"""
import calendar
from datetime import datetime, timedelta
import re


_NUMBERS = {word: index for index, word in enumerate(
    ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"), 1)}
_NUMBERS.update({"a": 1, "an": 1})
_NUMBER = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|an?)"
_RELATIVE = re.compile(
    r"\b(?P<approx>about\s+|around\s+|approximately\s+)?(?:"
    r"(?P<simple>today|yesterday)|"
    r"(?P<number>" + _NUMBER + r")\s+(?P<unit>days?|weeks?|months?|years?)\s+ago|"
    r"last\s*(?P<weekend>weekend)|"
    r"last\s+(?P<last>week|month|year)|"
    r"(?:this|current)\s+(?:calendar\s+)?(?P<current>week|month|year))\b", re.I)
_CAUTION = ("Resolved time expression anchored to the source observation; not a verified event date. "
            "The expression may date recollection, planning, or another clause rather than the event in question.")


def temporal_question(prompt: str) -> bool:
    """Detect requests for time, order, elapsed duration, or a dated event."""
    # The appended date is metadata, not evidence that the question is temporal.
    question = re.split(r"\nQuestion date:", prompt, flags=re.I)[0]
    return bool(_RELATIVE.search(question) or re.search(
        r"\b(?:when|how\s+long|how\s+many\s+(?:days|weeks|months|years)|"
        r"first|earliest|latest|before|after|earlier|later|chronolog\w*|"
        r"order\s+of|past\s+(?:\w+\s+)?(?:days|weeks|months|years)|"
        r"last\s+(?:visit\w*|attend\w*|meet\w*|see|saw|do|did)|"
        r"how\s+old|what\s+age)\b", question, re.I))


def query_date(prompt: str) -> datetime | None:
    """Read only a final, explicit reader metadata line, never an arbitrary date."""
    match = re.search(r"(?:^|\n)Question date:\s*([^\n]+)\s*\Z", prompt, re.I)
    if not match:
        return None
    try:
        return datetime.fromisoformat(match.group(1).strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _shift_months(value: datetime, months: int) -> datetime:
    ordinal = value.year * 12 + value.month - 1 + months
    year, month_zero = divmod(ordinal, 12)
    month = month_zero + 1
    return value.replace(year=year, month=month,
                         day=min(value.day, calendar.monthrange(year, month)[1]))


def temporal_references(value: str, observed_at: datetime | None) -> list[dict]:
    """Return source-anchored ranges for explicit relative expressions.

    Ranges are inclusive calendar dates, not timezone-normalized instants. Month
    and year offsets are coarse estimates even though their nominal date is
    rendered; the original phrase, precision, and uncertainty remain visible.
    Missing anchors yield no fabricated dates.
    """
    if not isinstance(value, str) or not isinstance(observed_at, datetime):
        return []
    result = []
    for match in _RELATIVE.finditer(value):
        precision = "day"
        approximate = bool(match.group("approx"))
        metadata = {}
        try:
            if match.group("simple"):
                days = 0 if match.group("simple").lower() == "today" else 1
                start = end = observed_at - timedelta(days=days)
            elif match.group("weekend"):
                precision = "weekend"
                # Calendar convention only: locale, attendance and the date of
                # any event are not inferred from this phrase or its anchor.
                saturday = observed_at - timedelta(days=(observed_at.weekday() - 5) % 7)
                if observed_at.weekday() < 5:
                    start, end = saturday, saturday + timedelta(days=1)
                else:
                    previous = saturday - timedelta(days=7)
                    start, end = previous, saturday + timedelta(days=1)
                    approximate = True
                    metadata = {
                        "ambiguity": "weekend_day_last_weekend_reference",
                        "range_kind": "candidate_envelope",
                        "candidate_ranges": [
                            {"resolved_start": candidate.date().isoformat(),
                             "resolved_end": (candidate + timedelta(days=1)).date().isoformat()}
                            for candidate in (previous, saturday)
                        ],
                    }
                metadata["weekend_convention"] = "Saturday-Sunday; locale not inferred"
            elif match.group("current"):
                precision = match.group("current").lower()
                if precision == "week":
                    start = observed_at - timedelta(days=observed_at.weekday())
                    end = start + timedelta(days=6)
                elif precision == "month":
                    start = observed_at.replace(day=1)
                    end = observed_at.replace(day=calendar.monthrange(observed_at.year, observed_at.month)[1])
                else:
                    start = observed_at.replace(month=1, day=1)
                    end = observed_at.replace(month=12, day=31)
            elif match.group("last"):
                precision = match.group("last").lower()
                if precision == "week":
                    end = observed_at - timedelta(days=observed_at.weekday() + 1)
                    start = end - timedelta(days=6)
                elif precision == "month":
                    end = observed_at.replace(day=1) - timedelta(days=1)
                    start = end.replace(day=1)
                else:
                    start = observed_at.replace(year=observed_at.year - 1, month=1, day=1)
                    end = start.replace(month=12, day=31)
            else:
                raw = match.group("number").lower()
                number = int(raw) if raw.isdigit() else _NUMBERS[raw]
                if number > 36500:
                    continue
                precision = match.group("unit").lower().rstrip("s")
                if precision in {"month", "year"}:
                    start = end = _shift_months(observed_at, -number * (12 if precision == "year" else 1))
                    approximate = True
                else:
                    start = end = observed_at - timedelta(days=number * (7 if precision == "week" else 1))
            result.append({"phrase": match.group(0), "span": [match.start(), match.end()],
                           "resolved_start": start.date().isoformat(), "resolved_end": end.date().isoformat(),
                           "precision": precision, "approximate": approximate,
                           "anchor_basis": "source_observed_at", "caution": _CAUTION + (
                               " On a weekend day, last weekend can mean the preceding or current weekend. "
                               "The outer range is only a candidate envelope; intervening weekdays are not "
                               "candidate dates. The current weekend may include a future Sunday."
                               if metadata.get("ambiguity") else ""), **metadata})
        except (ValueError, OverflowError, KeyError):
            # Impossible calendar arithmetic cannot become a memory assertion.
            continue
    return result


def query_window(prompt: str) -> dict | None:
    """Describe the first relative date requested by a question, if anchored."""
    anchor = query_date(prompt)
    question = re.split(r"\nQuestion date:", prompt, flags=re.I)[0]
    references = temporal_references(question, anchor)
    if not references:
        return None
    reference = references[0]
    return {**reference, "anchor_basis": "question_date",
            "caution": "Question-relative reference window; record observation within it is not proof an event occurred within it. "
            + reference["caution"]}
