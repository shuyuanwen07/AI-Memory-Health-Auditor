from datetime import datetime, timezone
from app.schemas import AuditRun, AuditStatus, Memory, MemoryStatus, TargetConfiguration, TargetProvider
from scripts.ac2_topic_inference_candidate_v3_20261030 import TopicInferenceCandidateV3


def generate(value):
    memory = Memory(memory_id='M', conversation_id='C', canonical_value=value,
                    status=MemoryStatus.CONFIRMED, source_message_ids=['S'])
    audit = AuditRun(run_id='R', conversation_id='C', status=AuditStatus.CREATED,
                     target_configuration=TargetConfiguration.WEAK, provider=TargetProvider.RULE_BASED,
                     model='rules', temperature=0, random_seed=42, test_budget=4,
                     prompt_template_version='v1', created_at=datetime.now(timezone.utc))
    return TopicInferenceCandidateV3().generate([memory], audit)


def test_scoped_question_retains_scope_without_the_value():
    questions = generate('For the architecture assignment only, use the 35 mm lens.')
    assert len(questions) == 1
    assert questions[0].prompt == 'Which lens is specified for the architecture assignment?'
    assert '35' not in questions[0].prompt and '35 mm' in questions[0].expected_behavior


def test_unrelated_laptop_does_not_become_an_operating_system_question():
    assert not any('operating system' in q.prompt for q in generate('I watch films on a laptop.'))
