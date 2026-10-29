"""Isolated guard against ambiguous duplicate generated accuracy prompts."""
from collections import defaultdict
from app.schemas import Dimension
from app.test_generator.quality import RuleBasedTestQualityValidator
from scripts.ac2_topic_inference_candidate_v3_20261030 import TopicInferenceCandidateV3


class TopicInferenceCandidateV4(TopicInferenceCandidateV3):
    VERSION = 'development-topic-inference-v4'

    def _balanced_order(self, candidates):
        # The original generator drops duplicate prompts after this stage. If
        # distinct references share a prompt, retaining the first can silently
        # turn ambiguity into a single-answer test. Conservatively drop all
        # such accuracy candidates, while leaving other dimensions unchanged.
        references = defaultdict(set)
        for dimension, prompt, expected, _, _ in candidates:
            if dimension == Dimension.ACCURACY:
                references[RuleBasedTestQualityValidator.normalize_prompt(prompt)].add(expected.strip().casefold())
        ambiguous = {prompt for prompt, values in references.items() if len(values) > 1}
        kept = [candidate for candidate in candidates if candidate[0] != Dimension.ACCURACY or
                RuleBasedTestQualityValidator.normalize_prompt(candidate[1]) not in ambiguous]
        self._ambiguous_accuracy_count = sum(candidate[0] == Dimension.ACCURACY and
            RuleBasedTestQualityValidator.normalize_prompt(candidate[1]) in ambiguous for candidate in candidates)
        return super()._balanced_order(kept)
