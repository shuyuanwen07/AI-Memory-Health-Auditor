"""Isolated duplicate-scope safeguard using the existing local validator first."""
from collections import defaultdict
from app.schemas import Dimension, TestCase as AuditTestCase, TestQualityStatus
from app.test_generator.quality import RuleBasedTestQualityValidator
from scripts.ac2_topic_inference_candidate_v3_20261030 import TopicInferenceCandidateV3


class TopicInferenceCandidateV5(TopicInferenceCandidateV3):
    VERSION = 'development-topic-inference-v5'

    def generate(self, memories, audit):
        self._validation_memories = memories
        self._validation_run_id = audit.run_id
        try:
            return super().generate(memories, audit)
        finally:
            self._validation_memories = None

    def _balanced_order(self, candidates):
        validator = RuleBasedTestQualityValidator()
        accepted = []
        references = defaultdict(set)
        for i, (dimension, prompt, expected, memory_ids, kind) in enumerate(candidates):
            case = AuditTestCase(test_id=f'PRE{i}', run_id=self._validation_run_id,
                                 dimension=dimension, prompt=prompt, expected_behavior=expected,
                                 supporting_memory_ids=memory_ids, test_type=kind,
                                 generator_version=self.VERSION)
            usable = validator.validate(case, self._validation_memories).quality_status != TestQualityStatus.REJECTED
            accepted.append(usable)
            if usable and dimension == Dimension.ACCURACY:
                references[validator.normalize_prompt(prompt)].add(expected.strip().casefold())
        ambiguous = {key for key, values in references.items() if len(values) > 1}
        kept = [candidate for i, candidate in enumerate(candidates)
                if not (accepted[i] and candidate[0] == Dimension.ACCURACY and
                        validator.normalize_prompt(candidate[1]) in ambiguous)]
        self._ambiguous_accuracy_count = len(candidates) - len(kept)
        return super()._balanced_order(kept)
