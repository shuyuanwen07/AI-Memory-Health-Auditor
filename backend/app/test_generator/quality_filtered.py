"""Current rule generator; the v37 research implementation remains frozen."""
import re

from app.services.memory_entities import named_projects
from app.test_generator.frozen_quality_filtered_v37 import (
    QualityFilteredRuleBasedTestGenerator as FrozenV37Generator,
)


class QualityFilteredRuleBasedTestGenerator(FrozenV37Generator):
    VERSION = 'rule-based-v38'

    @classmethod
    def _scoped_topic(cls, *memories):
        # Keep v37's existing project, event and scenario handling. Extend
        # only the project-anchor spelling it could not recognise safely.
        existing = super()._scoped_topic(*memories)
        topic = cls._topic(*memories)
        if existing != topic:
            return existing
        names = [{name.lower() for name in named_projects(memory.canonical_value)} for memory in memories]
        common = set.intersection(*names) if names and all(names) else set()
        if len(common) != 1:
            return existing
        name = next(iter(common))
        project_phrase = (r'\b(?:project\s+' + re.escape(name) + r'|' + re.escape(name)
                          + r'\s+(?:projects?|reviews?|meetings?|backends?|frontends?|deployments?|logs|logging|services?))\b')
        if all(re.search(project_phrase, memory.canonical_value, re.I) for memory in memories) and cls._anchor_safe(name, memories, project_phrase):
            return f'{topic} for the {name.title()} project'
        return existing
