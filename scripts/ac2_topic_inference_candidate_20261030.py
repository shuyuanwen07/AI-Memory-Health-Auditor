"""Isolated conservative topic candidate, not registered in the product."""
import re
from app.test_generator.conflict_aware import ConflictAwareRuleBasedTestGenerator

_OS = re.compile(r'\b(?:operating system|windows|macos|linux|ubuntu|fedora|debian|android|ios|chrome\s*os)\b', re.I)
_WORK = re.compile(r'\b(?:working arrangement|remote work|hybrid work|work(?:s|ing)?\s+(?:from home|remotely|on[ -]site|in the office|at the office))\b', re.I)
_TASK = re.compile(r"\b(?:my|the user's|the)\s+current task\s*(?:is|:)\s*\S", re.I)


class TopicInferenceCandidate(ConflictAwareRuleBasedTestGenerator):
    VERSION = 'development-topic-inference-v1'

    @staticmethod
    def _topic(*memories):
        topic = ConflictAwareRuleBasedTestGenerator._topic(*memories)
        texts = [m.canonical_value for m in memories]
        # Every supporting item must justify the inferred label; combining a
        # topic from an unrelated endpoint with another fact can mislead.
        checks = {'operating system': _OS, 'working arrangement': _WORK, 'current task': _TASK}
        if topic in checks and not all(checks[topic].search(text) for text in texts):
            return 'stored information'
        if topic == 'stored information' and texts and all(_WORK.search(text) for text in texts):
            return 'working arrangement'
        return topic
