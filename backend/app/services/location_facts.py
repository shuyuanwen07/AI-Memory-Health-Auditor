"""Conservative concrete values for explicit personal-location statements."""
import re


def location_value(text: str) -> str | None:
    def concrete(value: str) -> str:
        # A statement such as "moved to Utrecht and now live there" has one
        # location value. Preserve conjunctions in names (Trinidad and Tobago).
        return re.sub(r"\s+and\s+(?:i\s+)?(?:now\s+)?(?:live|reside)\s+there\s*$", '', value, flags=re.I).strip()
    labelled = re.search(r"\b(?:current\s+location|location)\s*(?::|is)\s*([^.;!?]+)", text, re.I)
    if labelled:
        return concrete(labelled.group(1))
    movement = re.search(r"\b(?:(?:based|located|living|lives?|reside|resides)\s+(?:in|at)|(?:moved|relocated)\s+to)\s+([^.;!?]+)", text, re.I)
    if movement:
        return concrete(movement.group(1))
    city = re.search(r"(?:^|:\s*)([a-z][a-z'-]*(?:\s+[a-z][a-z'-]*){0,3})\s+is\s+my\s+(?:current\s+)?(?:city|location)\s*[.!?]*$", text, re.I)
    return city.group(1).strip() if city else None
