from types import SimpleNamespace
from datetime import datetime, timezone
from app.schemas import AuditRun, AuditStatus, Memory, MemoryStatus, TargetConfiguration, TargetProvider
from app.test_generator.conflict_aware import ConflictAwareRuleBasedTestGenerator
from scripts.ac2_topic_inference_candidate_20261030 import TopicInferenceCandidate


def topic(*texts):
    return TopicInferenceCandidate._topic(*(SimpleNamespace(canonical_value=text) for text in texts))


def test_broad_terms_do_not_establish_a_specific_topic():
    assert topic('I watch films on a laptop.') == 'stored information'
    assert topic('The library is near my office.') == 'stored information'
    assert topic('For the architecture assignment only, use the 35 mm lens.') == 'stored information'


def test_explicit_information_retains_specific_topics():
    assert topic('My laptop runs Ubuntu.') == 'operating system'
    assert topic('I work remotely.') == 'working arrangement'


def test_mixed_supporting_memories_do_not_borrow_topic_from_one_endpoint():
    assert topic('My laptop runs Ubuntu.', 'I bought a laptop.') == 'stored information'


def test_generation_exposes_coverage_tradeoff_instead_of_unsupported_os_question():
    memory = Memory(memory_id='M1', conversation_id='C', canonical_value='I watch films on a laptop.',
                    status=MemoryStatus.CONFIRMED, source_message_ids=['S1'])
    audit = AuditRun(run_id='R', conversation_id='C', status=AuditStatus.CREATED,
                     target_configuration=TargetConfiguration.WEAK, provider=TargetProvider.RULE_BASED,
                     model='rules', temperature=0, random_seed=42, test_budget=4,
                     prompt_template_version='v1', created_at=datetime.now(timezone.utc))
    old = ConflictAwareRuleBasedTestGenerator().generate([memory], audit)
    candidate = TopicInferenceCandidate()
    new = candidate.generate([memory], audit)
    assert len(old) == 1 and 'operating system' in old[0].prompt
    assert not new and candidate.last_observation['rejected_candidate_count'] == 1
