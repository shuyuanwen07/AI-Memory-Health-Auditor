"""Source-grounded subject/topic refinements; v41 remains available for replay."""
import re
from app.test_generator.topic_scoped_v41 import TopicScopedRuleBasedTestGenerator


class TopicScopedV42(TopicScopedRuleBasedTestGenerator):
    VERSION = 'rule-based-v42'

    @staticmethod
    def _topic(*memories):
        text = ' '.join(m.canonical_value for m in memories)
        if re.search(r'\banalysis\s+(?:deadline|due date)\b', text, re.I):
            return 'analysis deadline'
        if re.search(r'\b(?:deliver(?:y|ies)|shipping)\b', text, re.I) and re.search(r'\bprovider\b', text, re.I):
            return 'delivery provider'
        return TopicScopedRuleBasedTestGenerator._topic(*memories)

    @classmethod
    def _scoped_topic(cls, *memories):
        topic=super()._scoped_topic(*memories)
        if len(memories) < 2 or topic not in {'schedule', 'participant count', 'delivery provider'}:
            return topic
        nouns=('workshop','study','garden','shop','event','service','meeting','order')
        matches=[{noun for noun in nouns if re.search(r'\b'+noun+r'\b',m.canonical_value,re.I)} for m in memories]
        common=set.intersection(*matches) if matches and all(matches) else set()
        return f'{topic} for the {next(iter(common))}' if len(common)==1 else topic
