"""Conservative source-derived deployment-region values for test grounding."""
import re


def deployment_region_value(text: str) -> str | None:
    if not re.search(r"\b(?:production|deployment|cloud|hosting|datacenter|datacentre|data center|data centre)\b", text, re.I):
        return None
    match = re.search(r"\b(?:region|zone)\s*(?:is\s+|:\s*|=\s*)([^.;,!\n?]{1,100})", text, re.I)
    if match is None:
        match = re.search(r"\b(?:region|zone)\s+([A-Z0-9][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)*)\s*[.!?;,]?$", text)
    return match.group(1).strip(" \t\"'`") if match else None
