from app.services.ac3_metrics import history_bootstrap


def row(i, *, auto='fail'):
    return {'test_id': f't{i}', 'history_id': f'h{i}', 'grounding': 'valid',
            'human_1': {'verdict': 'fail', 'failure_dimension': 'accuracy'},
            'human_2': {'verdict': 'fail', 'failure_dimension': 'accuracy'},
            'automatic': {'verdict': auto, 'failure_dimension': 'accuracy' if auto == 'fail' else None}}


def test_bootstrap_is_reproducible_and_does_not_invent_false_positive_rate():
    rows = [row(i, auto='fail' if i < 3 else 'uncertain') for i in range(6)]
    first = history_bootstrap(rows, iterations=200, seed=7)
    assert first == history_bootstrap(rows, iterations=200, seed=7)
    recall = first['intervals']['failure_recall_conservative']
    assert 0 <= recall['lower'] <= recall['upper'] <= 1
    assert first['intervals']['false_positive_rate_decided']['lower'] is None


def test_bootstrap_refuses_interval_for_fewer_than_five_histories():
    result = history_bootstrap([row(1), row(2)], iterations=100)
    assert result['status'] == 'insufficient_histories' and result['intervals'] == {}
