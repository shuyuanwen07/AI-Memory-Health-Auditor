"""Quality-filtered rule-based generator; v36 remains independently importable."""
from app.schemas import Dimension, TestQualityStatus
from app.test_generator.quality import RuleBasedTestQualityValidator
from app.test_generator.rule_based import RuleBasedTestGenerator


class QualityFilteredRuleBasedTestGenerator(RuleBasedTestGenerator):
    VERSION = 'rule-based-v37'

    def generate(self, memories, audit):
        # Each relationship produces at most two candidates. Request the full
        # pool before filtering, without changing the caller's frozen budget.
        total_bound = len(memories) + 2 * sum(len(m.relationships) for m in memories)
        all_audit = audit.model_copy(update={'test_budget': max(1, total_bound)})
        candidates = super().generate(memories, all_audit)
        validator = RuleBasedTestQualityValidator()
        usable, rejected = [], []
        for candidate in candidates:
            assessment = validator.validate(candidate, memories)
            if assessment.quality_status == TestQualityStatus.REJECTED:
                rejected.append({
                    'candidate_id': candidate.test_id,
                    'dimension': candidate.dimension.value,
                    'prompt': candidate.prompt,
                    'expected_behavior': candidate.expected_behavior,
                    'supporting_memory_ids': list(candidate.supporting_memory_ids),
                    'grounding_status': assessment.grounding_status.value,
                    'validator_version': assessment.validator_version,
                    'reason': assessment.reason,
                })
            else:
                usable.append(candidate)
        selected = usable[:audit.test_budget]
        self.last_observation = {
            'version': 'generator-observation-v1',
            'agent_version': self.VERSION,
            'status': 'completed' if selected else 'failed',
            'scope': 'Local deterministic prefilter, not independent validation.',
            'requested_test_count': audit.test_budget,
            'budget_semantics': 'maximum',
            'generated_test_count': len(selected),
            'candidate_count': len(candidates),
            'locally_usable_candidate_count': len(usable),
            'rejected_candidate_count': len(rejected),
            'rejected_candidates': rejected,
            'validator_version': validator.VERSION,
            'count_target_met': len(selected) == audit.test_budget,
            'quantity_shortfall_reason': None if len(selected) == audit.test_budget else 'Fewer candidates passed the existing local quality check than the requested budget.',
            'local_candidate_counts_by_dimension': {dim.value: sum(c.dimension == dim for c in usable) for dim in Dimension},
            'attempts': [],
        }
        return selected
