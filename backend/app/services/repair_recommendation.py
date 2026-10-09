"""Evidence-qualified exploratory candidates, never a causal diagnosis guarantee."""
from app.schemas.target_profile import TargetMemoryProfile


def recommend_repair(cases: list[dict], profile: TargetMemoryProfile, strategy: str,
                     capacity: int, record_count: int, *, configurable: bool) -> dict:
    candidate_profile = profile
    candidate_strategy = strategy
    candidate_capacity = capacity
    status = 'requires_review' if cases else 'no_detected_gap'
    title = 'Review the evidence before choosing a repair' if cases else 'No memory gap detected in these assessments'
    rationale = ('Review assessment validity, source provenance, fact correspondence and answer-time evidence before selecting a memory intervention. '
                 'The current configuration is retained; you can still design an explicitly exploratory experiment.' if cases else
                 'No automatic configuration change is suggested. Passing answers alone do not establish memory use or complete coverage.')
    # Only decided failures support a candidate. A pass lacking provenance and an
    # uncertain assessment must not silently become evidence for a repair.
    failures = {case['layer'] for case in cases if case['automated_passed'] is False}
    focus = 'evidence_review'
    if configurable and strategy == 'no_memory' and failures == {'no_memory_reference'}:
        status, focus = 'baseline_reference', 'baseline_ablation'
        title = 'Memory intentionally disabled for this baseline'
        rationale = ('The observed zero-memory input matches this reference setting. Keep the original configuration; '
                     'this is not a retrieval repair recommendation. You may explicitly compare a condition with memory enabled, '
                     'but that changes the experimental condition and does not by itself prove a diagnosed defect was repaired.')
    elif configurable and 'retention_hypothesis' in failures and capacity < 500:
        candidate_capacity = min(500, max(capacity + 1, record_count))
        candidate_profile = profile.model_copy(update={'label': 'Retention capacity candidate', 'version': profile.version + 1})
        status, focus = 'exploratory_candidate', 'retention_capacity'
        title = 'Test a larger memory capacity first'
        rationale = ('Observed capacity exclusions support this candidate. Change retained-record capacity only; keep retrieval, '
                     'model and instructions fixed. The larger memory budget can increase cost. Review other diagnostic cases separately.')
    elif configurable and 'retrieval_hypothesis' in failures and 'retention_hypothesis' not in failures and strategy != 'scope_aware':
        candidate_strategy = 'scope_aware'
        candidate_profile = profile.model_copy(update={'label': 'Retrieval strategy candidate', 'version': profile.version + 1})
        status, focus = 'exploratory_candidate', 'retrieval_strategy'
        title = 'Test retrieval that matches the task and project'
        rationale = ('Observed missing supplied source evidence supports investigating retrieval. Change the retrieval strategy while '
                     'preserving capacity and existing instructions. Inspect filtering, source relevance and any reader-setting changes '
                     'before attributing benefit to this strategy. Review other diagnostic cases separately.')
    elif not configurable:
        rationale = ('This target does not expose its memory controls. Review its observed behaviour and assess an intervention in the '
                     'target service; auditor configuration alone cannot repair that service.')
    elif 'retention_hypothesis' in failures:
        rationale = ('The retained-record capacity is already at the supported limit. Review retention policy and competing records; '
                     'the auditor cannot suggest a larger capacity. Existing retrieval and instructions are retained.')
    return {'profile': candidate_profile, 'strategy': candidate_strategy, 'capacity': candidate_capacity,
            'recommendation': {'status': status, 'focus': focus, 'title': title, 'rationale': rationale,
                               'notice': 'A candidate needs original and generic controls, independent new histories and human review before a value claim.'}}
