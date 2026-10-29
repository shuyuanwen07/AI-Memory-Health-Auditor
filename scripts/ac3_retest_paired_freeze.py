"""Independent offline freeze/compile gates for the new AC3 paired retest.

This is a new format, not accepted by the legacy product runner. It creates no
human evidence, calls no model and performs no database writes. The product
requires a separately implemented, tested format dispatch and paired runner.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from scripts.prepare_ac3_retest_review_intake import inspect
from scripts.ac3_retest_snapshot_verify import verify_snapshot

SHA = re.compile(r'^[a-f0-9]{64}$')
THRESHOLDS = {'failure_detection_recall_min': .8, 'failure_classification_accuracy_min': .8,
              'test_validity_min': .9, 'false_positive_rate_max': .1}
COMPONENTS = ('target_runtime', 'old_evaluator', 'new_evaluator')
PRIOR_RUNTIME_SHA256 = '5e3663c4acac06949bac645bfed91fb0007719f56295a50397f506a12fd55104'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def validate_protocol(config, components):
    """Validate only explicit, predeclared settings, not the truth of attestation."""
    if not isinstance(config, dict) or config.get('format') != 'ac3-retest-paired-protocol-v1':
        raise ValueError('Expected new paired protocol configuration.')
    if config.get('thresholds') != THRESHOLDS:
        raise ValueError('Thresholds differ from the recorded user-delegated AC3 choice.')
    if config.get('minimum_consensus_pass') != 30 or config.get('minimum_consensus_fail') != 30:
        raise ValueError('Both human-consensus outcome classes must contain at least 30.')
    if config.get('minimum_auto_coverage') != .8:
        raise ValueError('The established minimum automatic coverage is 80%.')
    if config.get('policy') != {'single_target_answer_per_item': True,
                                'both_graders_use_identical_answer': True,
                                'retain_target_errors': True,
                                'retain_scoring_errors': True,
                                'retain_uncertain_and_unclassified': True,
                                'exclude_after_outcome_inspection': False,
                                'uncertainty_unit': 'history'}:
        raise ValueError('All preregistered paired outcome safeguards must be explicit.')
    target = config.get('target')
    required = ('provider','model','strategy','prompt_template_version','memory_configuration_sha256',
                'temperature','random_seed','output_token_limit','retry_limit')
    if not isinstance(target, dict) or set(target) != set(required):
        raise ValueError('Complete target model and execution configuration is required.')
    for k in ('provider','model','strategy','prompt_template_version'):
        if not isinstance(target[k], str) or not target[k].strip():
            raise ValueError('Provider, model, strategy and prompt version cannot be blank.')
    if not SHA.fullmatch(str(target['memory_configuration_sha256'])):
        raise ValueError('Memory configuration must be bound by SHA-256.')
    temp = target['temperature']
    # These fields describe parameters actually sent, not local UI defaults.
    # The GPT-6 Luna connector omits both controls; freezing numeric values
    # would misrepresent the request and falsely imply deterministic sampling.
    if target['provider'] == 'openrouter' and target['model'] == 'openai/gpt-6-luna':
        if temp is not None or target['random_seed'] is not None:
            raise ValueError('GPT-6 Luna requests omit temperature and seed; record both as null.')
    else:
        if isinstance(temp, bool) or not isinstance(temp, (int, float)) or not math.isfinite(temp) or not 0 <= temp <= 2:
            raise ValueError('Temperature must be numeric between 0 and 2.')
        if type(target['random_seed']) is not int or target['random_seed'] < 0:
            raise ValueError('Seed must be an explicit nonnegative integer.')
    for name, minimum in (('output_token_limit', 1), ('retry_limit', 0)):
        if type(target[name]) is not int or target[name] < minimum:
            raise ValueError('Seed, output limit and retry limit must be explicit integers.')
    budget = config.get('budget')
    if config.get('budget_mode', 'capped') not in ('capped', 'tracking_only'):
        raise ValueError('Unknown budget mode.')
    if not isinstance(budget, dict) or set(budget) != {'max_usd', 'per_request_reservation_usd'}:
        raise ValueError('A total cap and per-request reservation are required.')
    for amount in budget.values():
        if isinstance(amount, bool) or not isinstance(amount, (float, int)) or not math.isfinite(amount) or amount <= 0:
            raise ValueError('Budget values must be finite positive USD amounts.')
    if budget['per_request_reservation_usd'] > budget['max_usd']:
        raise ValueError('Reservation must not exceed the budget cap.')
    scorer=config.get('scorer')
    if (not isinstance(scorer,dict) or set(scorer)!={'provider','model','output_token_limit','prompt_version','retry_limit','variant'}
            or scorer['provider']!='openrouter' or scorer['model']!='openai/gpt-6-luna'
            or type(scorer['output_token_limit']) is not int or scorer['output_token_limit']<=0
            or not isinstance(scorer['prompt_version'],str) or not scorer['prompt_version'].strip()
            or scorer['retry_limit']!=0 or scorer['variant'] not in ('hybrid','provider_only')):
        raise ValueError('Fix the scorer model, output limit, prompt, variant and zero-retry policy before target generation.')
    signatures = config.get('component_sha256')
    if not isinstance(signatures, dict) or set(signatures) != set(COMPONENTS) or set(components) != set(COMPONENTS):
        raise ValueError('Target runtime and both evaluator snapshots are required.')
    if any(not isinstance(components[k], bytes) or digest(components[k]) != signatures[k] for k in COMPONENTS):
        raise ValueError('The saved component snapshot differs from its frozen digest.')
    if signatures['old_evaluator'] == signatures['new_evaluator']:
        raise ValueError('The old and new evaluator snapshots must differ.')
    snapshots = config.get('evaluator_snapshots')
    if not isinstance(snapshots, dict) or set(snapshots) != {'old_evaluator', 'new_evaluator'}:
        raise ValueError('Both evaluator source and environment snapshots must be explicitly bound.')
    for name in ('old_evaluator', 'new_evaluator'):
        snapshot = snapshots[name]
        if not isinstance(snapshot, dict) or set(snapshot) != {'app_source_sha256', 'dependencies_lock_sha256'}:
            raise ValueError('Evaluator snapshots require exact app and environment-lock digests.')
        verify_snapshot(components[name], snapshot['app_source_sha256'], signatures[name], snapshot['dependencies_lock_sha256'])
    if snapshots['old_evaluator']['dependencies_lock_sha256'] != snapshots['new_evaluator']['dependencies_lock_sha256']:
        raise ValueError('Both evaluators must bind the same shared dependency environment.')
    if snapshots['old_evaluator']['app_source_sha256'] != PRIOR_RUNTIME_SHA256:
        raise ValueError('The baseline snapshot does not match the prior formal study runtime source.')
    if snapshots['old_evaluator']['app_source_sha256'] == snapshots['new_evaluator']['app_source_sha256']:
        raise ValueError('The new evaluator must use a distinct app source snapshot.')
    attestation = config.get('operator_declaration')
    if (not isinstance(attestation, dict) or attestation.get('new_target_results_observed') is not False or
        attestation.get('fixed_before_target_generation') is not True or
        not isinstance(attestation.get('operator_label'), str) or not attestation['operator_label'].strip()):
        raise ValueError('A named pre-run operator declaration is required; it is not independently authenticated.')


def prepare(source_raw, plan_raw, review_raws, config, components):
    intake = inspect(source_raw, plan_raw, review_raws)
    if not intake['all_items_valid_in_both_reviews']:
        raise ValueError('All source, fact, relation and question items must be resolved before this strict freeze.')
    validate_protocol(config, components)
    source, plan = json.loads(source_raw), json.loads(plan_raw)
    return {'format': 'ac3-retest-paired-frozen-v1', 'source_sha256': digest(source_raw),
            'plan_sha256': digest(plan_raw), 'review_sha256': [digest(x) for x in review_raws],
            'protocol_sha256': digest(canonical(config)), 'protocol': config,
            'suite': source, 'reviewed_fact_plan': plan,
            'fact_reviews': intake['existing_fact_validator_projection']['fact_reviews'],
            'human_identity_independently_authenticated': False,
            'execution_supported': False, 'model_called': False, 'results_observed': False,
            'limitation': 'Offline paired-study format; real product dispatch and scorer isolation are not yet implemented.'}


def compile_isolated(frozen, source_raw, plan_raw, review_raws, components):
    """Revalidate all evidence and compile items without invoking a model."""
    expected = prepare(source_raw, plan_raw, review_raws, frozen['protocol'], components)
    if canonical(expected) != canonical(frozen):
        raise ValueError('Frozen study or its evidence changed.')
    items = [{'history_id': c['history_id'], **q} for c in frozen['suite']['cases'] for q in c['tests']]
    if len(items) != 120 or len({x['test_id'] for x in items}) != 120:
        raise ValueError('Expected exactly 120 distinct predeclared tests.')
    return {'format': 'ac3-retest-paired-offline-stage-v1', 'test_ids': [x['test_id'] for x in items],
            'items': items, 'protocol_sha256': frozen['protocol_sha256'],
            'responses_generated': 0, 'model_called': False, 'database_written': False,
            'product_execution_supported': False}


def main():
    import argparse
    import os
    from pathlib import Path
    from scripts.prepare_ac3_retest_review_intake import PACKET
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=PACKET / 'candidate-inputs.json')
    parser.add_argument('--plan', type=Path, default=PACKET / 'proposed-fact-plan.json')
    parser.add_argument('--review-1', type=Path, required=True)
    parser.add_argument('--review-2', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--target-runtime', type=Path, required=True)
    parser.add_argument('--old-evaluator', type=Path, required=True)
    parser.add_argument('--new-evaluator', type=Path, required=True)
    parser.add_argument('--frozen-input', type=Path, help='If provided, revalidate and compile the existing frozen file offline.')
    parser.add_argument('--output', type=Path, required=True, help='New output file; existing files are never overwritten.')
    args = parser.parse_args()
    def read(path):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Input must be an existing regular non-symlink file: {path}')
        return path.read_bytes()
    source, plan = read(args.source), read(args.plan)
    reviews = [read(args.review_1), read(args.review_2)]
    protocol = json.loads(read(args.protocol))
    components = {'target_runtime': read(args.target_runtime), 'old_evaluator': read(args.old_evaluator),
                  'new_evaluator': read(args.new_evaluator)}
    if args.frozen_input:
        frozen = json.loads(read(args.frozen_input))
        if canonical(frozen.get('protocol')) != canonical(protocol):
            raise ValueError('Provided protocol differs from the frozen protocol.')
        output = compile_isolated(frozen, source, plan, reviews, components)
    else:
        output = prepare(source, plan, reviews, protocol, components)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(args.output, flags, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'format': output['format'], 'model_called': False,
                      'database_written': False, 'product_execution_supported': False}))


if __name__ == '__main__':
    main()
