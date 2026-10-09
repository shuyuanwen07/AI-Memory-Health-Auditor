"""Conservative concrete values for explicit personal-location statements."""
import re


def location_value(text: str) -> str | None:
    movement = re.search(r"\b(?:(?:based|located|living|live|reside|resides)\s+(?:in|at)|(?:moved|relocated)\s+to)\s+([^.;!?]+)", text, re.I)
    if movement:
        return movement.group(1).strip()
    city = re.search(r"(?:^|:\s*)([a-z][a-z'-]*(?:\s+[a-z][a-z'-]*){0,3})\s+is\s+my\s+(?:current\s+)?(?:city|location)\s*[.!?]*$", text, re.I)
    return city.group(1).strip() if city else None
