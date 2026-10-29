"""Isolated development candidate; not registered as a product strategy."""
from app.memory_agent.store import _question_requests_update_history
from app.schemas import MemoryStrategy, RelationshipType
from app.services.memory_entities import named_projects

def include_update_history(candidates, relations, question, strategy):
    """Allow a stored superseded predecessor when explicitly requested.

    This changes eligibility only in candidate copies. Evicted, missing or
    unlinked records stay excluded; it does not prove records are correct.
    """
    if strategy != MemoryStrategy.STRONG_RULE_BASED or not _question_requests_update_history(question):
        return
    by_id = {item['record'].id:item for item in candidates}
    requested_projects = named_projects(question)
    for relation in relations:
        if relation.relationship_type != RelationshipType.UPDATE.value:
            continue
        current=by_id.get(relation.memory_id); prior=by_id.get(relation.target_memory_id)
        if not current or not prior or not current.get('eligible') or not current.get('category_match'):
            continue
        if prior['record'].lifecycle_state != 'SUPERSEDED' or 'evicted' in prior.get('reason','').lower():
            continue
        current_projects = named_projects(current['record'].canonical_value)
        prior_projects = named_projects(prior['record'].canonical_value)
        if requested_projects and (not requested_projects.intersection(current_projects)
                                   or not requested_projects.intersection(prior_projects)):
            continue
        if current_projects and prior_projects and current_projects.isdisjoint(prior_projects):
            continue
        prior['eligible']=True
        prior['relevance']=max(prior['relevance'],current['relevance'])
        prior['reason']+=', candidate_update_history_for_explicit_question'
