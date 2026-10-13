from app.metrics.service import MetricsService
from app.schemas import Dimension, EvaluationResult
def item(test_id, passed): return EvaluationResult(evaluation_id='E'+test_id,response_id='R'+test_id,test_id=test_id,passed=passed,reason='',evidence_memory_ids=[],evaluator='test')
def test_macro_average_ignores_zero_test_dimensions():
    score, dimensions=MetricsService().calculate([item('T1',True),item('T2',False)],{'T1':Dimension.ACCURACY,'T2':Dimension.FRESHNESS})
    assert score == 50.0
    assert next(x for x in dimensions if x.dimension==Dimension.CONFLICT_RESOLUTION).percentage is None


def test_metrics_ignore_unknown_and_duplicate_evaluations():
    score, dimensions = MetricsService().calculate(
        [item('T1', True), item('T1', False), item('UNKNOWN', False)],
        {'T1': Dimension.ACCURACY},
    )
    accuracy = next(x for x in dimensions if x.dimension == Dimension.ACCURACY)
    assert score is None
    assert (accuracy.passed, accuracy.total) == (0, 0)
    reversed_score, _ = MetricsService().calculate([item('T1', False), item('T1', True)], {'T1':Dimension.ACCURACY})
    assert reversed_score is None


def test_no_valid_evaluations_has_no_overall_score():
    score, dimensions = MetricsService().calculate([item('UNKNOWN', True)], {})
    assert score is None
    assert all(dimension.percentage is None and dimension.total == 0 for dimension in dimensions)


def test_uncertain_dimension_is_not_reported_as_never_tested():
    score, dimensions = MetricsService().calculate(
        [item('T1', None), item('T2', True), item('UNKNOWN', None)],
        {'T1': Dimension.APPROPRIATE_USE, 'T2': Dimension.ACCURACY},
    )
    pending = next(d for d in dimensions if d.dimension == Dimension.APPROPRIATE_USE)
    assert pending.percentage is None and pending.total == 0
    assert pending.uncertain_count == 1
    assert score == 100
    assert next(d for d in dimensions if d.dimension == Dimension.FRESHNESS).uncertain_count == 0


def test_four_measured_dimensions_do_not_certify_an_overall_score_with_excluded_evidence():
    from app.schemas import AuditResult, DimensionScores
    result=AuditResult(run_id='fixture',overall_score=100,tests_passed=4,tests_total=4,expected_tests=5,excluded_evidence_count=1,failures=[],dimensions=[DimensionScores(dimension=dimension,percentage=100,passed=1,total=1) for dimension in Dimension])
    assert result.formal_overall_score is None
    result.excluded_evidence_count=0
    assert result.formal_overall_score==100
