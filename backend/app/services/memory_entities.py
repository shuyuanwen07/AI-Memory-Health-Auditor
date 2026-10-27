"""Conservative named-project matching from source text, never gold answers."""
import re

_GENERIC = {'all', 'the', 'this', 'that', 'current', 'another', 'unrelated', 'conflicting',
            'our', 'my', 'your', 'a', 'an', 'which', 'what', 'same', 'deployment',
            'or', 'and', 'both', 'should', 'must', 'can', 'could', 'would', 'does', 'do', 'is', 'are', 'for'}


def named_projects(text: str) -> set[str]:
    prefix_names = re.findall(r'\b[Pp]roject\s+([A-Z][\w-]*(?:\s+[A-Z][\w-]*){0,3})\b', text)
    if prefix_names:
        return {' '.join(name.lower().split()) for name in prefix_names}
    capitalised = re.findall(r'\b([A-Z][\w-]*(?:\s+[A-Z][\w-]*){0,3})\s+(?:(?:capstone|web|production)\s+)*(?:capstones?|backends?|frontends?|deployments?|logs|logging|services?|projects?|reviews?|meetings?)\b', text)
    if capitalised:
        return {' '.join(part.lower() for part in name.split() if part.lower() not in _GENERIC)
                for name in capitalised if any(part.lower() not in _GENERIC for part in name.split())}
    names = re.findall(r'\b([\w-]+)\s+(?:backend|deployment|logs|logging|service|project)\b', text.lower())
    return {name for name in names if name not in _GENERIC}
