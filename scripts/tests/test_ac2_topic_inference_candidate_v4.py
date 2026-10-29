from datetime import datetime, timezone
from app.schemas import AuditRun, AuditStatus, Memory, MemoryStatus, TargetConfiguration, TargetProvider
from scripts.ac2_topic_inference_candidate_v4_20261030 import TopicInferenceCandidateV4


def memory(i, text):
    return Memory(memory_id=i, conversation_id='C', canonical_value=text,
                  status=MemoryStatus.CONFIRMED, source_message_ids=['S'+i])


def audit():
    return AuditRun(run_id='R', conversation_id='C', status=AuditStatus.CREATED,
                    target_configuration=TargetConfiguration.WEAK, provider=TargetProvider.RULE_BASED,
                    model='rules', temperature=0, random_seed=42, test_budget=4,
                    prompt_template_version='v1', created_at=datetime.now(timezone.utc))


def test_multiple_values_for_same_scope_do_not_become_single_answer():
    g = TopicInferenceCandidateV4()
    tests = g.generate([memory('1','For the architecture assignment only, use the 35 mm lens.'),
                        memory('2','For the architecture assignment only, use the 50 mm lens.')], audit())
    assert not any('Which lens is specified' in t.prompt for t in tests)
    assert g._ambiguous_accuracy_count == 2


def test_one_record_still_has_the_scoped_question():
    g = TopicInferenceCandidateV4()
    tests = g.generate([memory('1','For the architecture assignment only, use the 35 mm lens.')], audit())
    assert any('Which lens is specified' in t.prompt for t in tests)
    assert g._ambiguous_accuracy_count == 0
