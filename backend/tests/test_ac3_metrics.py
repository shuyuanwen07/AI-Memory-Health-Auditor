import pytest
from app.services.ac3_metrics import calculate


def review(verdict, dimension=None):
    return {'verdict': verdict, 'failure_dimension': dimension}


def row(number, reference, automatic, second=None, grounding='valid'):
    return {'test_id': f'test-{number}', 'history_id': f'history-{number // 3}',
            'grounding': grounding, 'human_1': reference, 'human_2': second or reference,
            'automatic': automatic}


def test_abstentions_and_disagreements_remain_visible():
    fail = review('fail', 'freshness')
    passed = review('pass')
    rows = [row(0, fail, review('fail', 'freshness')),
            row(1, fail, review('fail', 'accuracy')),
            row(2, fail, review('uncertain')),
            row(3, passed, review('pass')),
            row(4, passed, review('fail', 'accuracy')),
            row(5, passed, review('uncertain')),
            row(6, fail, review('pass'), second=review('uncertain')),
            row(7, passed, review('pass'), grounding='invalid'),
            row(8, passed, review('pass'), grounding='uncertain')]
    result = calculate(rows)
    assert result['grounding']['validity_conservative'] == {'numerator': 7, 'denominator': 9, 'value': 7 / 9}
    assert result['human_reference']['unresolved'] == 1
    assert result['metrics']['decided_coverage']['value'] == 4 / 6
    assert result['metrics']['failure_recall_conservative']['value'] == 2 / 3
    assert result['metrics']['failure_recall_decided']['value'] == 1
    assert result['metrics']['false_positive_rate_decided']['value'] == 1 / 2
    assert result['metrics']['false_positive_rate_lower_bound']['value'] == 1 / 3
    assert result['metrics']['classification_accuracy_conservative']['value'] == 1 / 2
    assert result['status'] == 'descriptive_not_acceptance'


def test_missing_categories_and_zero_denominators_are_not_imputed():
    result = calculate([row(0, review('fail', 'freshness'), review('fail'))])
    assert result['automatic']['category_missing'] == 1
    assert result['metrics']['classification_accuracy_conservative']['value'] == 0
    assert result['metrics']['classification_accuracy_decided']['value'] is None
    assert result['metrics']['false_positive_rate_decided']['value'] is None


def test_duplicate_or_invalid_reference_rejected():
    r = row(0, review('pass'), review('pass'))
    with pytest.raises(ValueError): calculate([r, r])
    with pytest.raises(ValueError): calculate([row(0, review('fail'), review('pass'))])
    with pytest.raises(ValueError): calculate([row(0, review('pass', 'accuracy'), review('pass'))])
