"""Isolated scoped-lens question prototype; not registered with the app."""
import re
from app.schemas import Dimension, TestType
from scripts.ac2_topic_inference_candidate_v2_20261030 import TopicInferenceCandidateV2

_LENS = re.compile(
    r'^For\s+(?P<scope>the\s+[A-Za-z][A-Za-z -]{0,40}\s+assignment)\s+only,\s*'
    r'use\s+(?:the\s+)?(?P<value>\d+(?:\.\d+)?\s*mm)\s+lens[.!]?$', re.I)


class TopicInferenceCandidateV3(TopicInferenceCandidateV2):
    VERSION = 'development-topic-inference-v3'

    @classmethod
    def _accuracy(cls, memory):
        match = _LENS.fullmatch(memory.canonical_value.strip())
        if not match:
            return super()._accuracy(memory)
        return (Dimension.ACCURACY, f"Which lens is specified for {match['scope']}?",
                f"State the recorded fact: {memory.canonical_value.rstrip('.!?')}.",
                [memory.memory_id], TestType.DIRECT)
