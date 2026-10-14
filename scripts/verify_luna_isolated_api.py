"""Verify real isolated smoke receipts and exports; performs no inference."""
import argparse
import csv
import hashlib
import json
from math import sqrt
from pathlib import Path

MODEL = 'openai/gpt-6-luna'
DIMENSIONS = {'accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'}


def verify(report, bundle, csv_rows, source, approval, *, require_reported_models=False):
    from app.services.runtime_freeze import audit_runtime_signature
    if report.get('runtime_signature') != audit_runtime_signature():
        raise ValueError('Restore the frozen application runtime before reconstructing historical instruction receipts.')
    assert report.get('core_api_status', report['status']) == 'completed'
    if require_reported_models:
        assert report['status'] == 'completed'
    assert report['research_evidence'] is False and report['production_database_writes'] == 0
    repetitions = report.get('planned_repetitions_per_strategy', 1)
    assert type(repetitions) is int and 1 <= repetitions <= 3
    assert len(report['runs']) == len(bundle['runs']) == repetitions * 2
    assert len(bundle['condition_summaries']) == 2
    assert all(len(c['run_ids']) == repetitions for c in bundle['condition_summaries'])
    assert len({r['run_id'] for r in report['runs']}) == repetitions * 2
    for strategy in ('weak_first_hit', 'strong_rule_based'):
        members = [r for r in report['runs'] if r['strategy'] == strategy]
        assert len(members) == repetitions
        if repetitions > 1:
            assert {r['repetition'] for r in members} == set(range(1, repetitions + 1))
    inventory = report['confirmation']['inventory']
    approved = {m['message_id']: m for m in source['messages']}
    assert len(inventory) == len(approved) == 8
    memory_by_source = {}
    for memory in inventory:
        assert len(memory['source_message_ids']) == 1
        source_id = memory['source_message_ids'][0]
        assert source_id not in memory_by_source
        assert memory['canonical_value'] == approved[source_id]['content']
        memory_by_source[source_id] = memory['memory_id']
    actual_edges = {(m['memory_id'], e['type'], e['target_memory_id']) for m in inventory for e in m['relationships']}
    assert actual_edges == {(memory_by_source[e['source_message_id']], e['type'], memory_by_source[e['target_message_id']]) for e in approval['relationships']}
    roles = []
    summaries = []
    suites = []
    reader_policy_hashes = set()
    from app.schemas import TestCase
    from app.target_ai.rule_based import private_context_instruction
    for agent in report['extraction_agents']:
        assert agent['status'] == 'completed'
        assert agent['model'] == agent['reported_model'] == MODEL and agent['provider'] == 'openrouter'
        assert agent['attempt_count'] > 0
        roles.append({k: agent[k] for k in ('role', 'model', 'reported_model', 'attempt_count', 'status')})
    for run in report['runs']:
        rid = run['run_id']
        configuration = run['configuration']
        assert configuration['target_configuration'] == 'strong'
        assert configuration['model'] == MODEL and configuration['provider'] == 'openrouter'
        assert len(run['tests']) == len(run['responses']) == len(run['evaluations']) == 4
        assert {test['dimension'] for test in run['tests']} == DIMENSIONS
        suites.append(sorted((t['dimension'], t['prompt'], t['expected_behavior'], sorted(t['supporting_memory_ids'])) for t in run['tests']))
        responses = {r['response_id']: r for r in run['responses']}
        for response in responses.values():
            assert response['model'] == MODEL and response['execution_metadata']['reported_model'] == MODEL
            assert response['execution_metadata']['request_attempts'] > 0
        for evaluation in run['evaluations']:
            response = responses[evaluation['response_id']]
            assert response['test_id'] == evaluation['test_id']
            meter = evaluation['judge_execution']
            assert meter['provider'] == 'openrouter' and meter['model'] == MODEL
            assert meter['reported_model'] in (None, MODEL)
            if require_reported_models:
                assert meter['reported_model'] == MODEL
            assert meter['request_attempts'] > 0
        for agent in run['agents']:
            if agent['status'] == 'skipped':
                continue
            assert agent['model'] == MODEL and agent['provider'] == 'openrouter'
            if agent['status'] == 'completed':
                # Judge meter is the authoritative provider receipt; the separate
                # ledger currently does not copy reported_model for this role.
                assert agent['reported_model'] == MODEL or (agent['role'] == 'blind_evaluation' and agent['reported_model'] is None)
                if require_reported_models:
                    assert agent['reported_model'] == MODEL
            roles.append({k: agent[k] for k in ('role', 'model', 'reported_model', 'attempt_count', 'status')})
        trace = run['memory_trace']
        assert trace['target_system_adapter'] == 'controlled-memory'
        assert len(trace['records']) > 0 and len(trace['retrievals']) == 4
        target_ids = {m['memory_id'] for m in trace['records']}
        target_by_id = {m['memory_id']: m for m in trace['records']}
        tests_by_id = {t['test_id']: t for t in run['tests']}
        assert not target_ids.intersection(memory_by_source.values())
        assert all(set(m['source_message_ids']) <= set(approved) for m in trace['records'])
        for retrieval in trace['retrievals']:
            assert set(retrieval['selected_memory_ids']) <= target_ids
            assert retrieval['final_response_id'] in responses
            assert retrieval['memory_input']['record_count'] == len(retrieval['selected_memory_ids'])
            private_test = TestCase.model_validate(tests_by_id[retrieval['test_id']]).model_copy(update={'target_memory_context': [target_by_id[mid]['canonical_value'] for mid in retrieval['selected_memory_ids']]})
            instructions = private_context_instruction(private_test, 'strong')
            assert hashlib.sha256(instructions.encode()).hexdigest() == retrieval['memory_input']['instruction_sha256']
            # Recorded instruction includes varying evidence JSON; compare the
            # policy only after verifying the complete recorded instruction hash.
            policy = instructions.split('\n\nMEMORY POLICY\n', 1)[1]
            reader_policy_hashes.add(hashlib.sha256(policy.encode()).hexdigest())
        exported = next(r for r in bundle['runs'] if r['configuration']['run_id'] == rid)
        assert exported['result'] == run['result']
        answers = {a['evaluation_id']: a for a in exported['answers']}
        csv_answers = {r['evaluation_id']: r for r in csv_rows if r['record_type'] == 'answer' and r['run_id'] == rid}
        assert len(answers) == len(csv_answers) == 4
        for e in run['evaluations']:
            a = answers[e['evaluation_id']]
            c = csv_answers[e['evaluation_id']]
            for key in ('test_id', 'response_id', 'evaluation_id'):
                assert a[key] == c[key] == e[key]
            assert a['answer'] == c['answer'] == responses[e['response_id']]['response_text']
        metrics = {r['metric']: r['value'] for r in csv_rows if r['record_type'] == 'run' and r['run_id'] == rid}
        result = run['result']
        for metric, field in (('overall_score', 'overall_score'), ('answers_passed', 'tests_passed'), ('answers_decided', 'tests_total'), ('pending_judgments', 'uncertain_count')):
            expected = result[field]
            assert metrics[metric] == '' if expected is None else float(metrics[metric]) == expected
        summaries.append({'run_id': rid, 'strategy': run['strategy'], 'overall_score': result['overall_score'],
            'formal_overall_score': result['formal_overall_score'], 'tests_passed': result['tests_passed'],
            'tests_total': result['tests_total'], 'uncertain_count': result['uncertain_count'],
            'excluded_evidence_count': result['excluded_evidence_count'], 'dimensions': result['dimensions'],
            'target_actual_model_verified': True,
            'judge_actual_model_verified': all(e['judge_execution']['reported_model'] == MODEL for e in run['evaluations']),
            'judge_reported_models': [e['judge_execution']['reported_model'] for e in run['evaluations']],
            'target_store_ids_disjoint_from_approved_auditor_ids': True})
    assert all(suite == suites[0] for suite in suites)
    verify_condition_exports(report['runs'], bundle['condition_summaries'], csv_rows)
    assert len(reader_policy_hashes) == 1
    return {'passed': True, 'shared_suite_verified': True, 'exact_approved_inventory_verified': True, 'same_strong_reader_policy_hash_verified': True, 'complete_instruction_receipt_hashes_reconstructed': True,
            'json_csv_identity_answer_score_reconciliation_verified': True, 'repetitions_per_strategy': repetitions,
            'condition_aggregate_and_variation_verified': True, 'roles': roles, 'runs': summaries,
            'source_isolation_limit': 'Trace proves separate record IDs and original source refs; source code inspection is also required to prove no ground-truth reads.'}


def verify_condition_exports(runs, conditions, csv_rows):
    """Recompute aggregate scores/variation from every saved repeat, no inference."""
    def average(values):
        return round(sum(values) / len(values), 3) if values else None
    def deviation(values):
        if len(values) < 2:
            return None
        mean = sum(values) / len(values)
        return round(sqrt(sum((v - mean) ** 2 for v in values) / len(values)), 3)
    def csv_equal(metrics, metric, expected):
        assert metrics[metric] == '' if expected is None else float(metrics[metric]) == expected
    assert len({r for c in conditions for r in c['run_ids']}) == len(runs)
    assert sum(len(c['run_ids']) for c in conditions) == len(runs)
    for condition in conditions:
        members = [r for r in runs if r['run_id'] in condition['run_ids']]
        assert len(members) == len(condition['run_ids'])
        assert len({r['strategy'] for r in members}) == 1
        assert condition['planned_runs'] == condition['completed_runs'] == len(members)
        assert condition['failed_runs'] == 0
        scores = [r['result']['overall_score'] for r in members if r['result']['overall_score'] is not None]
        assert condition['overall_mean'] == average(scores)
        assert condition['overall_standard_deviation'] == deviation(scores)
        metrics = {r['metric']: r['value'] for r in csv_rows if r['record_type'] == 'condition' and r['condition_id'] == condition['condition_id']}
        for metric in ('planned_runs', 'completed_runs', 'failed_runs', 'overall_mean', 'overall_standard_deviation'):
            csv_equal(metrics, metric, condition[metric])
        for score in condition['dimensions']:
            rows = [next(s for s in r['result']['dimensions'] if s['dimension'] == score['dimension']) for r in members]
            measured = [r for r in rows if r['percentage'] is not None]
            assert score['mean_percentage'] == average([r['percentage'] for r in measured])
            assert score['standard_deviation'] == deviation([r['percentage'] for r in measured])
            assert score['measured_runs'] == len(measured)
            for field in ('passed', 'total'):
                assert score[field] == sum(r[field] for r in measured)
            for field in ('uncertain_count', 'excluded_evidence_count', 'expected_tests'):
                assert score[field] == sum(r[field] for r in rows)
            metrics = {r['metric']: r['value'] for r in csv_rows if r['record_type'] == 'dimension' and r['condition_id'] == condition['condition_id'] and r['dimension'] == score['dimension']}
            for metric, field in (('mean_percentage', 'mean_percentage'), ('answers_passed', 'passed'), ('answers_decided', 'total'), ('pending_judgments', 'uncertain_count'), ('excluded_evidence', 'excluded_evidence_count'), ('expected_questions', 'expected_tests')):
                csv_equal(metrics, metric, score[field])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-reported-models', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source_path = root / 'datasets/smoke/qwen-four-dimension-source-v1.json'
    approval_path = root / 'datasets/smoke/qwen-four-dimension-approval-v1.json'
    report = json.loads(args.report.read_text())
    assert report['source_sha256'] == hashlib.sha256(source_path.read_bytes()).hexdigest()
    assert report['approval_sha256'] == hashlib.sha256(approval_path.read_bytes()).hexdigest()
    result = verify(report, json.loads(args.report.with_suffix('.bundle.json').read_text()),
        list(csv.DictReader(args.report.with_suffix('.csv').open())), json.loads(source_path.read_text()), json.loads(approval_path.read_text()), require_reported_models=args.require_reported_models)
    result['report_sha256'] = hashlib.sha256(args.report.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'passed': True, 'output': str(args.output)}))

if __name__ == '__main__':
    main()
