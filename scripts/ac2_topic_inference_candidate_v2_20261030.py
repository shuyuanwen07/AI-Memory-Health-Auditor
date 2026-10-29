"""Second isolated topic candidate, preserving explicit work-location scope."""
import re
from app.test_generator.conflict_aware import ConflictAwareRuleBasedTestGenerator
from scripts.ac2_topic_inference_candidate_20261030 import TopicInferenceCandidate

_WORK_LOCATION = re.compile(r'\b(?:regular|usual|normal)\s+work\s+location\b', re.I)


class TopicInferenceCandidateV2(TopicInferenceCandidate):
    VERSION = 'development-topic-inference-v2'

    @staticmethod
    def _topic(*memories):
        original = ConflictAwareRuleBasedTestGenerator._topic(*memories)
        if original == 'working arrangement' and memories and all(_WORK_LOCATION.search(m.canonical_value) for m in memories):
            return original
        return TopicInferenceCandidate._topic(*memories)
