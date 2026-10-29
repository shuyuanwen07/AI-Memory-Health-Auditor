from types import SimpleNamespace
import pytest
from app.services.ac3_retest_taxonomy_adapter import adapt_taxonomy


def result(passed=None,category=None,status='unclassified'):
    return SimpleNamespace(passed=passed,failure_type=SimpleNamespace(value=category) if category else None,
        failure_classification=SimpleNamespace(status=status),reason='fixture',evidence_memory_ids=['f1'],judge_execution=None)


def provider(passed=False,category='accuracy'):
    return {'passed':passed,'failure_type':category,'reason':'fixture','classification_reason':'fixture','evidence_memory_ids':['f1']}


def test_preserves_provider_judgment_when_hybrid_abstains():
    out=adapt_taxonomy(result(),provider(),['f1'])
    assert out['hybrid']['verdict']=='uncertain'
    assert out['provider_only']['verdict']=='fail' and out['provider_only']['failure_type']=='accuracy'
    assert not out['human_truth_evaluated'] and not out['live_runner_authorized']


def test_missing_provider_and_unclassified_failure_are_not_guessed():
    out=adapt_taxonomy(result(False,'accuracy','unclassified'),None,['f1'])
    assert out['provider_only']['verdict']=='error'
    assert out['hybrid']['verdict']=='fail' and out['hybrid']['failure_type'] is None


def test_bad_provider_category_or_evidence_is_rejected():
    with pytest.raises(ValueError,match='category'):
        adapt_taxonomy(result(),provider(True,'accuracy'),['f1'])
    p=provider();p['evidence_memory_ids']=['other']
    with pytest.raises(ValueError,match='evidence'):
        adapt_taxonomy(result(),p,['f1'])
