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
    assert score == 100.0
    assert (accuracy.passed, accuracy.total) == (1, 1)


def test_no_valid_evaluations_has_no_overall_score():
    score, dimensions = MetricsService().calculate([item('UNKNOWN', True)], {})
    assert score is None
    assert all(dimension.percentage is None and dimension.total == 0 for dimension in dimensions)
