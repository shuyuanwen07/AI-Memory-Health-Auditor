from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.schemas import AuditRun, AuditStatus, Memory, MemoryStatus, TargetConfiguration, TargetProvider, TestQualityStatus
from app.services.generation_coverage import assert_generation_coverage
from app.test_generator.quality import RuleBasedTestQualityValidator
from app.test_generator.quality_filtered import QualityFilteredRuleBasedTestGenerator
from app.test_generator.rule_based import RuleBasedTestGenerator


def audit(budget):
    return AuditRun(run_id='R', conversation_id='C', status=AuditStatus.CREATED,
        target_configuration=TargetConfiguration.WEAK, provider=TargetProvider.RULE_BASED,
        model='rules', temperature=0, random_seed=42, test_budget=budget,
        prompt_template_version='v1', created_at=datetime.now(timezone.utc))


def memory(key, value):
    return Memory(memory_id=key, conversation_id='C', canonical_value=value,
        status=MemoryStatus.CONFIRMED, source_message_ids=['S'+key])


def test_prefilter_records_rejected_and_fills_from_later_valid_candidates():
    memories=[memory('M001', 'I enjoy purple tulips.'),memory('M002','The user prefers Python programming.')]
    old = RuleBasedTestGenerator().generate(memories,audit(1))
    assert 'recorded stored information' in old[0].prompt
    g=QualityFilteredRuleBasedTestGenerator(); selected=g.generate(memories,audit(1))
    assert len(selected)==1 and selected[0].supporting_memory_ids==['M002']
    assert selected[0].generator_version=='rule-based-v38'
    assert RuleBasedTestQualityValidator().validate(selected[0],memories).quality_status==TestQualityStatus.ACCEPTED
    obs=g.last_observation
    assert obs['count_target_met'] is True and obs['rejected_candidate_count']==1
    assert obs['rejected_candidates'][0]['supporting_memory_ids']==['M001']
    assert 'recorded stored information' in obs['rejected_candidates'][0]['prompt']
    assert obs['rejected_candidates'][0]['reason']
    assert RuleBasedTestGenerator.VERSION=='rule-based-v36'


def test_frozen_v37_source_matches_development_protocol():
    import hashlib
    from pathlib import Path
    from app.test_generator import frozen_quality_filtered_v37
    assert frozen_quality_filtered_v37.QualityFilteredRuleBasedTestGenerator.VERSION == 'rule-based-v37'
    assert hashlib.sha256(Path(frozen_quality_filtered_v37.__file__).read_bytes()).hexdigest() == '38a48363fbcbb3f17d4cb5f761c2c2ddfd3eeb5a82a3c3028d56ecc480053319'


def test_product_generator_uses_project_prefix_without_leaking_the_answer():
    from app.test_generator.factory import get_test_generator
    cedar = memory('M001', 'For project Cedar, Java is required.')
    generator = get_test_generator('rule_based')
    selected = generator.generate([cedar], audit(1))
    assert len(selected) == 1
    assert selected[0].generator_version == 'rule-based-v40'
    assert 'Cedar project' in selected[0].prompt
    assert 'Java' not in selected[0].prompt
    assert RuleBasedTestQualityValidator().validate(selected[0], [cedar]).quality_status == TestQualityStatus.ACCEPTED


def test_shortfall_is_saved_and_maximum_is_not_a_new_quota():
    memories=[memory('M001','I enjoy purple tulips.'),memory('M002','The user prefers Python programming.')]
    g=QualityFilteredRuleBasedTestGenerator(); selected=g.generate(memories,audit(2))
    assert len(selected)==1 and g.last_observation['count_target_met'] is False
    checked=[x.model_copy(update={'quality_status':TestQualityStatus.ACCEPTED}) for x in selected]
    assert_generation_coverage(g.last_observation,checked,2)
    frozen={**g.last_observation, 'coverage_plan': [{'dimension':'accuracy', 'supporting_memory_ids':['M001']}]}
    with pytest.raises(HTTPException, match='frozen accuracy evidence slot'):
        assert_generation_coverage(frozen,checked,2)


def test_no_locally_acceptable_candidate_is_not_declared_complete():
    g=QualityFilteredRuleBasedTestGenerator(); assert g.generate([memory('M001','I enjoy purple tulips.')],audit(2))==[]
    assert g.last_observation['count_target_met'] is False
    assert g.last_observation['rejected_candidate_count']==1
