"""Bounded affirmative possessive assertions, not a general coreference solver.

A bare name remains a valid short answer. Only an explicit conflicting owner
for the same named person and relation is rejected; ambiguous prose is left to
semantic/human review. All inputs are source text, never target-store metadata.
"""
import re

_RELATION = r'(?:partner|supervisor|manager|mentor|colleague|client|sister|brother|mother|father|daughter|son)'
_KIN = r'(?:sister|brother|mother|father|daughter|son|wife|husband|partner)'
_OWNER = rf"(?:(?:my|your|the user's)\s+{_KIN}'s|(?:my|your|the user's)|[A-Z][a-z]+'s)"
_NAME = r'(?P<name>(?-i:[A-Z][a-z]+))(?=[.!?,;]|$|\s+(?:and|but|not|is)\b)'
_FORWARD = re.compile(rf"(?P<owner>{_OWNER})\s+(?P<relation>{_RELATION})\s+is\s+{_NAME}", re.I)
_REVERSE = re.compile(rf"{_NAME}\s+is\s+(?P<owner>{_OWNER})\s+(?P<relation>{_RELATION})\b", re.I)


def _owner(value: str) -> str:
    text = value.lower().replace('the user\'s', 'your')
    text = re.sub(r'^(?:my|your)\s+', 'user/', text)
    if text in {'my','your'}:
        return 'user'
    return text.removesuffix("'s")


def affirmative_bindings(text: str) -> set[tuple[str, str, str]]:
    text=text.replace('’', "'")
    bindings=set()
    for pattern in (_FORWARD, _REVERSE):
        for match in pattern.finditer(text):
            # Do not promote a hypothetical, quoted-denied or explicitly
            # negated assertion into a factual claim.
            prefix=re.split(r'[.!?;\n]',text[:match.start()])[-1]
            if re.search(r'\b(?:not|never|if|unless|maybe|perhaps|hypothetically)\b',prefix,re.I):
                continue
            bindings.add((_owner(match['owner']),match['relation'].lower(),match['name'].lower()))
    return bindings


def explicit_owner_conflicts(answer: str, sources: list[str]) -> list[str]:
    source_bindings=set().union(*(affirmative_bindings(source) for source in sources))
    issues=[]
    for owner,relation,value in affirmative_bindings(answer):
        supported={o for o,r,v in source_bindings if r==relation and v==value}
        if supported and owner not in supported:
            issues.append(f'explicit owner {owner} for {relation} of {value} differs from source owner '+', '.join(sorted(supported)))
    return sorted(issues)
