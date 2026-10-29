from types import SimpleNamespace
from unittest.mock import patch
from app.services.ac3_retest_rule_adapter import score_rule


def result(passed,category,status):
    return SimpleNamespace(passed=passed,failure_type=SimpleNamespace(value=category) if category else None,
        failure_classification=SimpleNamespace(status=status),reason='fixture',evidence_memory_ids=['f1'],evaluator='fixture')


def test_unclassified_and_legacy_dimensions_never_become_diagnoses():
    for status in ('unclassified','legacy_test_dimension'):
        with patch('app.services.ac3_retest_rule_adapter.RuleBasedBehaviourEvaluator.evaluate',return_value=result(False,'accuracy',status)):
            row=score_rule(None,None,[])
        assert row['verdict']=='fail' and row['failure_type'] is None and row['classification_status']==status


def test_only_explicit_classified_failures_keep_category():
    with patch('app.services.ac3_retest_rule_adapter.RuleBasedBehaviourEvaluator.evaluate',return_value=result(False,'freshness','classified')):
        assert score_rule(None,None,[])['failure_type']=='freshness'
    for passed in (True,None):
        with patch('app.services.ac3_retest_rule_adapter.RuleBasedBehaviourEvaluator.evaluate',return_value=result(passed,'freshness','classified')):
            row=score_rule(None,None,[])
        assert row['failure_type'] is None
        assert row['verdict']==('pass' if passed else 'uncertain')
