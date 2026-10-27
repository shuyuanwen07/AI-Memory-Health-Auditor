"""Bounded source-supported classification of explicit information abstentions.

No test dimension, expected-answer string or retrieval metadata is consulted.
An omission is not evidence that the reader selected an obsolete value or that
retrieval, encoding or the base model caused it. Ambiguous tasks stay untyped.
"""
import re
from app.schemas import Dimension
from app.services.deployment_facts import deployment_region_value
from app.services.memory_entities import named_projects
from app.services.memory_topics import language_words

_DATABASES={'mysql','postgresql','postgres','sqlite','mongodb','redis','mariadb','cassandra','dynamodb'}
_UNKNOWN=re.compile(r"\b(?:i|we)\s+(?:(?:do\s+not|don't)\s+have\s+(?:enough\s+)?(?:remembered\s+)?information|(?:cannot|can't)\s+(?:identify|determine|recall|establish))\b|\b(?:does\s+not|doesn't)\s+(?:identify|record|state|establish|specify|mention|provide)\b|\bno\s+(?:current\s+)?(?:database\s+(?:choice|technology)|information|requirement)\s+(?:is\s+)?(?:recorded|available)\b",re.I)

def classify_source_abstention(prompt,answer,support):
 text=answer.replace('’',"'")
 if not _UNKNOWN.search(text):return None
 # Hypothetical, quoted or advice-only descriptions are not actual abstention.
 if re.search(r'\b(?:if|unless|hypothetically|example|quote|quoted)\b',text,re.I):return None
 by_id={m.memory_id:m for m in support};query=prompt.lower();candidates={}
 projects=set().union(*(named_projects(m.canonical_value) for m in support)) if support else set()
 requested=named_projects(prompt)
 if projects and requested and (requested.isdisjoint(projects) or len(projects)>1):return None
 words=set(re.findall(r'\b[a-z]+\b',text.lower()))
 for memory in support:
  for edge in memory.relationships:
   prior=by_id.get(edge.target_memory_id)
   if prior is None or prior.memory_id==memory.memory_id:continue
   if edge.type.value=='UPDATE' and re.search(r'\bdatabase\b',query) and re.search(r'\b(?:current|now|latest|up-to-date)\b',query):
    current=_DATABASES.intersection(re.findall(r'\b[a-z]+\b',memory.canonical_value.lower()))
    old=_DATABASES.intersection(re.findall(r'\b[a-z]+\b',prior.canonical_value.lower()))
    # Require a one-value explicit source update and distinct historical value.
    current-=old
    if len(current)==1 and old and not current.intersection(words):
     candidates[Dimension.FRESHNESS]='The answer explicitly lacks the requested current database although a linked source update supplies a distinct replacement.'
   if edge.type.value=='CONTEXTUAL_OVERRIDE' and re.search(r'\b(?:programming.language|language)\b',query) and re.search(r'\b(?:task|project)\b',query):
    required=language_words(memory.canonical_value);general=language_words(prior.canonical_value)
    if len(required)==1 and general and required.isdisjoint(general) and not required.intersection(words) and re.search(r'\b(?:requires?|required|must|mandatory)\b',memory.canonical_value,re.I):
     candidates[Dimension.APPROPRIATE_USE]='The answer explicitly lacks a requested task-specific language requirement although a linked scoped override supplies it.'
   if edge.type.value=='CONFLICT' and re.search(r'\bdeployment\b',query) and re.search(r'\bregion\b',query):
    values={deployment_region_value(m.canonical_value) for m in [memory,prior]}-{None}
    if len(values)==2 and all(not re.search(r'(?<!\w)'+re.escape(v)+r'(?!\w)',text,re.I) for v in values):
     candidates[Dimension.CONFLICT_RESOLUTION]='The answer explicitly lacks deployment-region constraints although two linked source records supply distinct unresolved alternatives.'
 if len(candidates)==1:return next(iter(candidates.items()))
 return None
