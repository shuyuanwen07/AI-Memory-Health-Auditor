"""Prepare a guarded AC3 request using the actual target memory pipeline.

No provider is invoked here. Private context and the retrieval identifiers are
returned for durable request evidence; the caller must bind the resulting
private test to the exact request and preserve evidence before dispatch.
"""
from app.schemas import TargetProvider


def prepare_ac3_input(adapter, test, audit, frozen_test_id):
    if (audit.provider != TargetProvider.OPENROUTER or adapter.audit.run_id != audit.run_id or
        test.run_id != audit.run_id or not isinstance(frozen_test_id, str) or not frozen_test_id.strip()):
        raise ValueError('Expected matching OpenRouter audit and frozen question')
    profile = audit.target_memory_profile
    if (profile.identity_analysis != 'off' or profile.answer_validation != 'off' or
        audit.retrieval_mode.value != 'fixed' or audit.target_memory_writer.value != 'rule_based' or
        audit.reproducibility.intervention):
        raise ValueError('AC3 preparation requires local fixed retrieval without auxiliary model calls or interventions')
    private, retrieval, identity = adapter.prepare_answer(test, audit)
    ids = list(retrieval.evidence.selected_memory_ids)
    context = list(private.target_memory_context)
    if (identity is not None or private.expected_behavior or private.supporting_memory_ids or
        len(ids) != len(context) or not retrieval.evidence.retrieval_id):
        raise ValueError('Private target evidence is incomplete or contains reference data')
    return private, {'format':'ac3-private-request-evidence-v1', 'frozen_test_id':frozen_test_id,
                     'run_id':audit.run_id, 'retrieval_id':retrieval.evidence.retrieval_id,
                     'selected_memory_ids':ids, 'target_memory_context':context}
