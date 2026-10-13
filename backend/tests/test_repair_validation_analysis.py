import importlib.util
from pathlib import Path


def test_bootstrap_uses_source_histories_instead_of_repeated_audits():
    source = Path(__file__).resolve().parents[2] / 'scripts/analyse_repair_validation.py'
    spec = importlib.util.spec_from_file_location('repair_analysis', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runs, comparisons = [], []
    for group, delta in [('source-a', 25), ('source-b', -25)]:
        for repeat in range(3):
            run_id = f'{group}-{repeat}'
            runs.append({'group': group, 'run': {'run_id': run_id, 'model': 'fixed', 'memory_strategy': 'original'},
                         'result': {'overall_score': 75}, 'trace': {'records': []}, 'evaluations': []})
            comparisons.append({'comparison_name': 'primary', 'before': run_id,
                'paired_delta_percentage_points': delta,
                'counts': {'fixed': int(delta > 0), 'regressed': int(delta < 0), 'still_failed': 0, 'still_passed': 3}})
    study = {'protocol_id': 'test', 'strategies': ['original'], 'scenarios': [{'gold_tests': []}, {'gold_tests': []}], 'notice': 'test'}
    payload, _ = module.analyse(study, {'runs': runs, 'before_after_comparisons': comparisons})
    comparison = payload['comparisons'][0]
    assert comparison['source_histories'] == 2
    assert comparison['paired_audits'] == 6
    assert comparison['source_mean_deltas_pp'] == [25, -25]
    assert comparison['mean_delta_pp'] == 0
    assert comparison['descriptive_source_cluster_bootstrap_95_interval_pp'] == [-25, 25]


def test_uncertain_results_and_unobserved_external_memory_are_not_zeroes():
    source = Path(__file__).resolve().parents[2] / 'scripts/analyse_repair_validation.py'
    spec = importlib.util.spec_from_file_location('repair_analysis', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    evaluation = {'test': {'dimension': 'accuracy', 'test_id': 'q', 'prompt': 'Q', 'expected_behavior': 'R'}, 'response': {'execution_metadata': {}, 'response_text': 'A'}, 'automated': {'passed': None, 'reason': 'Unavailable'}}
    study = {'protocol_id': 'test', 'strategies': ['original'], 'scenarios': [{'gold_tests': []}], 'notice': 'test'}
    result, _ = module.analyse(study, {'runs': [{'group': 'g', 'run': {'run_id': 'r', 'model': 'external', 'memory_strategy': 'original'}, 'result': {'overall_score': None}, 'trace': {'records': []}, 'evaluations': [evaluation]}], 'before_after_comparisons': []})
    summary = result['condition_summary'][0]
    assert summary['total'] == 0
    assert summary['uncertain'] == 1
    assert summary['percentage'] is None
    assert summary['mean_supplied_records'] is None
    assert summary['mean_latency_ms'] is None
