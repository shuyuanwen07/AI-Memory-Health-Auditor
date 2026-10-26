"""Export a read-only integrity-hashed results package; never dispatch model calls.

No full conversation source or credentials are exported. Missing/error planned
cells remain in all denominators. Source calibration never changes official grades.
"""
from stability_grading_budget import study_grader_cap, trial_grader_cap, grader_budget_matches, budget_source, study_trial_grader_budget_matches
from stability_configuration import pilot_cohorts, source_reuse_scope, pilot_quality_gates, study_trial_controls_match

from stability_answer_validation import read_observation as read_validation_observation, validate_binding as validate_answer_binding, summarize as summarize_answer_validation, DRAFT as PRIMARY_DRAFT, OBSERVATIONS as VALIDATION_OBSERVATIONS
from stability_configuration import answer_validation_enabled
from stability_auxiliary import describe_auxiliary, summarize_auxiliary, auxiliary_acceptance_gate, frozen_protocol_binding

import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import random


def read(path):return json.loads(path.read_text())
def public_metadata(value):
    # Preserve identity/usage/fingerprints; exclude private request bodies/secrets.
    forbidden={'input_payload','raw_input_payload','raw_selected_context','target_memory_context','haystack_sessions','request_headers','authorization','api_key','credential','instructions','prompt','raw_model_review','draft_answer','selected_context'}
    if isinstance(value,dict):return {k:public_metadata(v) for k,v in value.items() if k.lower() not in forbidden}
    if isinstance(value,list):return [public_metadata(v) for v in value]
    return value
def wilson(success,n):
    if not n:return None
    z=1.959963984540054;p=success/n;d=1+z*z/n;mid=(p+z*z/(2*n))/d;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0,mid-half),min(1,mid+half)]
def trial_key(value):
    if not isinstance(value, dict) or not isinstance(value.get('case_id'), str) or not isinstance(value.get('arm'), str) or type(value.get('round')) not in {str, int}:
        return (None, None, None)
    return (value.get('case_id'), value.get('round'), value.get('arm'))


def usable_target(target):
    response = target.get('response') or {}
    metadata = response.get('execution_metadata') or {}
    text = response.get('response_text')
    return (target.get('status') == 'completed' and metadata.get('completion_status') == 'complete'
            and metadata.get('finish_reason') == 'stop' and isinstance(text, str) and bool(text.strip()))


def valid_semantic_grade(status, grade):
    verdict = grade.get('verdict') or {}
    if status != 'completed':
        return None
    return {'correct': verdict.get('correct'), 'reason': verdict.get('reason'),
            'execution_metadata': public_metadata(grade.get('execution')), 'status': grade.get('status')}


def failure_diagnostics(report, directory):
    """Export only fixed safe failure fields, never private observation bodies."""
    receipts = report.get('target_call_receipts', [])
    grades = report.get('semantic_assessments', [])
    target = receipts[0] if receipts else {}
    safe_code = lambda value: value[:200] if isinstance(value, str) else None
    diagnostics = {'report_status': safe_code(report.get('status')), 'report_error_code': safe_code(report.get('error_code')),
                   'target_error_code': safe_code(target.get('error_code')), 'target_receipt_count': len(receipts),
                   'grading_attempt_count': len(grades)}
    observation_path = directory / 'identity-observation-receipts.json'
    if not observation_path.exists():
        return diagnostics
    try:
        private = read(observation_path)
        rows = private.get('observations', []) if isinstance(private, dict) else []
        failures = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            observation = row.get('last_observation')
            observation = observation if isinstance(observation, dict) else {}
            if row.get('analyzer_call_status') != 'failed' and observation.get('status') != 'failed':
                continue
            failure = {}
            if type(row.get('attempt')) is int and row['attempt'] > 0:
                failure['attempt'] = row['attempt']
            if isinstance(row.get('exception_type'), str):
                failure['exception_type'] = row['exception_type'][:200]
            public_observation = {}
            for key in ('error_code', 'error_summary'):
                if isinstance(observation.get(key), str):
                    public_observation[key] = observation[key][:2000]
            raw_details = observation.get('error_diagnostics')
            if isinstance(raw_details, dict):
                details = {key: raw_details[key][:200] for key in ('phase', 'validation_type', 'reason_code')
                           if isinstance(raw_details.get(key), str)}
                if details:
                    public_observation['error_diagnostics'] = details
            failure['last_observation'] = public_observation
            failures.append(failure)
        if failures:
            diagnostics['identity_observations'] = failures
    except (OSError, ValueError, TypeError) as exc:
        diagnostics['identity_observation_receipt_error'] = type(exc).__name__
    return diagnostics


def enrich_controlled_identity(receipt_metadata, controlled_metadata):
    """Join post-answer identity outcome without replacing actual input evidence."""
    if not isinstance(receipt_metadata, dict) or not isinstance(controlled_metadata, dict):
        return receipt_metadata, False
    actual = receipt_metadata.get('memory_input')
    controlled = controlled_metadata.get('memory_input')
    if not isinstance(actual, dict) or not isinstance(controlled, dict):
        return receipt_metadata, False
    actual = {key: value for key, value in actual.items() if key != 'sent_memory_ids'}
    controlled = {key: value for key, value in controlled.items() if key != 'sent_memory_ids'}
    fields = ('reported_model', 'response_source', 'requested_output_token_limit', 'completion_status', 'finish_reason')
    if actual != controlled or any(receipt_metadata.get(key) != controlled_metadata.get(key) for key in fields):
        return receipt_metadata, False
    return {**receipt_metadata, 'identity_analysis': controlled_metadata.get('identity_analysis'),
            **({'answer_validation':controlled_metadata['answer_validation']} if 'answer_validation' in controlled_metadata else {})}, True


def actual_role_mismatches(runs):
    mismatches = []
    for run in runs:
        grade = run.get('grading_attempt') or {}
        roles = []
        # Every valid completed target requires one original grader with actual identity.
        if run.get('target_usable') or grade:
            roles.append(('stability_guard_assessment' if run.get('split') == 'safety_guards' else 'benchmark_pilot_assessment', grade.get('execution')))
        roles += [(event.get('agent_role'), event.get('execution')) for event in run.get('agent_execution_attempts', run.get('extra_agent_executions', []))]
        for role, execution in roles:
            if (role not in {'benchmark_pilot_assessment', 'stability_guard_assessment', 'target_identity_evidence', 'target_answer_validation'} or not isinstance(execution, dict) or execution.get('reported_model') != 'openai/gpt-6-luna'
                    or execution.get('model') != 'openai/gpt-6-luna' or execution.get('provider') != 'openrouter'
                    or execution.get('agent_role') != role):
                mismatches.append({'role': role, 'case_id': run.get('case_id'), 'round': run['round'], 'arm': run['arm']})
    return mismatches


def saved_replay_path(stage):
    original = stage / 'replay-proof.json'
    diagnostic = stage / 'replay-proof-frozen-diagnostic.json'
    return original if original.exists() or not diagnostic.exists() else diagnostic


def replay_is_complete(proof, stage, expected):
    matrix_path = stage / 'trial-matrix.json'
    if not matrix_path.exists():
        return False
    matrix = read(matrix_path)
    keys = [trial_key(trial) for trial in matrix.get('trials', [])]
    rows = proof.get('rows', [])
    row_keys = [trial_key(row) for row in rows]
    return (len(keys) == expected and len(set(keys)) == expected and len(rows) == expected
            and len(set(row_keys)) == expected and set(row_keys) == set(keys)
            and proof.get('status') == 'passed' and proof.get('model_calls') == 0 and proof.get('network_attempts') == 0
            and proof.get('trial_matrix_sha256') == hashlib.sha256(matrix_path.read_bytes()).hexdigest()
            and proof.get('compared_trials') == expected
            and proof.get('grader_input_comparisons', sum(row.get('grade_input_compared') is True for row in rows)) == expected
            and proof.get('planned_grader_input_comparisons', len(rows)) == expected
            and all(row.get('inputs_equal') is True and row.get('grade_input_compared') is True for row in rows))


def original_review_sources(directory):
    """Return this trial's saved source texts with the loader's runtime message ids."""
    guard = directory / 'guard-case.json'
    if guard.exists():
        case = read(guard)
        sources = {message.get('message_id'): message.get('content') for message in case.get('conversation', {}).get('messages', [])}
        for mapping in case.get('runtime_source_id_map', []):
            original = mapping.get('original_source_id')
            if original in sources:
                sources[mapping.get('runtime_source_id')] = sources[original]
        return sources
    subset = directory / 'pilot-subset.json'
    if not subset.exists():return {}
    payload = read(subset)
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):return {}
    record = payload[0]
    sessions = next((record[key] for key in ('haystack_sessions','sessions','conversation','messages') if isinstance(record.get(key),list)), [])
    flattened = []
    for session in sessions:
        turns = session if isinstance(session,list) else session.get('messages', [session]) if isinstance(session,dict) else []
        if isinstance(turns,list):flattened.extend(turn for turn in turns if isinstance(turn,dict))
    sources = {}
    for index,message in enumerate(flattened,1):
        content = message.get('content') or message.get('text')
        if isinstance(content,str) and content.strip():
            key = str(message.get('message_id') or message.get('id') or f'MSG-{index:03d}')
            if key in sources:return {} # Ambiguous ids cannot bind a review.
            sources[key] = content.strip()
    return sources


def validate_source_reviews(review, stage, required_fields, expected_count=None):
    """Bind each review to one terminal saved first attempt; derive all counts."""
    matrix_path = stage / 'trial-matrix.json'
    matrix = read(matrix_path) if matrix_path.exists() else {'trials': []}
    trials = matrix.get('trials', [])
    keys = [trial_key(trial) for trial in trials]
    expected = dict(zip(keys, trials))
    failures = []
    if expected_count is not None and not required_fields:
        failures.append('required source-review schema is unavailable')
    if len(expected) != len(trials) or (expected_count is not None and len(trials) != expected_count):
        failures.append('planned trial matrix does not have the required unique denominator')
    execution_path = stage / 'study-execution.json'
    execution = read(execution_path) if execution_path.exists() else {}
    terminal = (execution.get('status') in {'completed', 'partial_failure'}
                and len(execution.get('trials', [])) == len(trials)
                and {trial_key(trial) for trial in execution.get('trials', [])} == set(keys)
                and all(trial.get('status') in {'completed', 'error'} for trial in execution.get('trials', [])))
    entries = review.get('trials', []) if isinstance(review, dict) else []
    if not isinstance(entries, list):
        failures.append('review trials must be a list')
        entries = []
    counts = Counter(trial_key(row) for row in entries if isinstance(row, dict))
    verified = {}
    claim_fields = {'claim', 'source_support', 'source_quote', 'source_message_id', 'supplied_quote_verified', 'explanation'}
    for index, row in enumerate(entries):
        if not isinstance(row, dict):
            failures.append(f'review {index}: not an object')
            continue
        key = trial_key(row)
        errors = []
        if key not in expected or counts[key] != 1:
            errors.append('unknown or duplicate trial key')
        if any(field not in row for field in [*required_fields, 'case_id', 'round', 'arm', 'target_response_sha256', 'target_status']):
            errors.append('required review field missing')
        if required_fields and (not isinstance(row.get('run_id'), str) or not row['run_id'].strip()):
            errors.append('run_id must be nonempty')
        if 'automatic_grade_unchanged' in required_fields and row.get('automatic_grade_unchanged') is not True:
            errors.append('automatic grade must remain unchanged')
        if not isinstance(row.get('critical_errors'), list):
            errors.append('critical_errors must be an explicit list')
        claims = row.get('claims')
        if not isinstance(claims, list) or not claims or any(not isinstance(claim, dict) or not claim_fields <= set(claim) for claim in claims):
            errors.append('claims must retain all source-review fields')
        if key in expected:
            directory = stage / expected[key]['directory']
            report_path = directory / 'pilot-report.json'
            report = read(report_path) if report_path.exists() else {}
            receipts = report.get('target_call_receipts', [])
            target = receipts[0] if len(receipts) == 1 else {}
            text = (target.get('response') or {}).get('response_text')
            if required_fields and row.get('run_id') != (report.get('benchmark_result') or {}).get('run_id'):
                errors.append('run_id differs from original benchmark run')
            source_messages = original_review_sources(directory)
            for claim in claims if isinstance(claims, list) else []:
                if not isinstance(claim, dict) or not claim_fields <= set(claim):
                    continue
                quote = claim['claim']
                support = claim['source_support']
                source_quote = claim['source_quote']
                source_id = claim['source_message_id']
                if (not isinstance(quote, str) or not quote or not isinstance(text, str) or quote not in text
                        or not isinstance(support, str) or support not in {'supported', 'qualified', 'unsupported', 'not_assessable'}
                        or not isinstance(claim['explanation'], str) or not claim['explanation'].strip()
                        or not (claim['supplied_quote_verified'] is None or type(claim['supplied_quote_verified']) is bool)
                        or not (source_quote is None or isinstance(source_quote, str) and bool(source_quote))
                        or not (source_id is None or isinstance(source_id, str) and bool(source_id))):
                    errors.append('invalid claim types, enum, explanation, or exact target quotation')
                    continue
                if support == 'supported' and (source_quote is None or source_id is None):
                    errors.append('supported claim requires an original source quote and source id')
                if source_quote is not None:
                    source_text = source_messages.get(source_id)
                    if not isinstance(source_text, str) or source_quote not in source_text:
                        errors.append('source quotation does not match this trial original mapped source message')
            if (report.get('status') not in {'completed', 'failed', 'partial_assessment_failure'}
                    or len(report.get('semantic_assessments', [])) != 1
                    or any(grade.get('status') not in {'completed', 'failed', 'uncertain'} for grade in report.get('semantic_assessments', []))
                    or not usable_target(target) or row.get('target_status') != target.get('status')):
                errors.append('saved target/grade attempt is not terminal and reviewable')
            if not isinstance(text, str) or row.get('target_response_sha256') != hashlib.sha256(text.encode('utf-8')).hexdigest():
                errors.append('target response UTF-8 hash does not match saved first attempt')
        if errors:
            failures.append({'index': index, 'trial_key': key, 'errors': errors})
        else:
            verified[key] = row
    missing = set(keys) - set(verified)
    if expected_count is not None and missing:
        failures.append({'missing_verified_trials': len(missing)})
    critical_count = sum(len(row['critical_errors']) for row in verified.values())
    ready = isinstance(review, dict) and review.get('status') == 'completed' and terminal
    review_failed = isinstance(review, dict) and review.get('status') in {'failed', 'error'}
    status = 'fail' if review_failed else (('fail' if failures or critical_count else 'pass') if ready else 'pending')
    return ({'status': status, 'observed': {'critical_error_count': critical_count,
             'reviewed_trials': len(verified), 'planned_trials': len(trials), 'validation_errors': failures},
             'threshold': ('All planned terminal first attempts uniquely source-reviewed; zero source-reviewed critical errors.' if expected_count is not None else 'Provided case reviews must uniquely bind to saved replies and sources, with zero reviewed critical errors. Unreviewed replies have no safety finding; completed degraded replies require their own review.')}, verified)



def final_case_source_review_gate(protocol, stage, review, required_fields):
    """Prospective full-final source safety; absent/false flag preserves legacy scope.

    Hashes bind the review snapshot, not the truth of its source judgments.
    Safety guards remain an independent stage and denominator.
    """
    requirements = protocol.get('additional_acceptance_requirements') or {}
    if not isinstance(requirements, dict) or 'final_source_review_required' not in requirements:
        return None
    declared = requirements['final_source_review_required']
    if declared is False:
        return None
    threshold = 'Every planned final-stage first attempt source-reviewed; zero critical source errors across all arms; four original input/wire files hash-bound.'
    critical_arms = None
    per_arm_critical = {}
    required_arm_count = None
    def result(status, state, errors, expected=None, reviewed=0, critical=0, verified=None):
        return ({'status': status, 'observed': {'review_state': state, 'planned_trials': expected,
            'reviewed_trials': reviewed, 'critical_error_count': critical,
            'critical_error_count_by_arm': per_arm_critical,
            'critical_error_required_arms': critical_arms if critical_arms is not None else 'all',
            'critical_error_required_arm_trial_count': required_arm_count,
            'required_arm_critical_error_count': sum(per_arm_critical.get(arm, 0) for arm in critical_arms) if critical_arms is not None else critical,
            'validation_errors': errors},
            'threshold': threshold, 'interpretation': 'Source review judgments are separate from automatic accuracy; hashes bind bytes only.'}, verified or {})
    if declared is not True:
        return result('fail', 'invalid_configuration', ['final_source_review_required must be a boolean'])
    if 'final_source_critical_error_arms' in requirements:
        scope = requirements['final_source_critical_error_arms']
        if (not isinstance(scope, list) or not scope
                or any(not isinstance(arm, str) or arm not in {'weak_first_hit', 'strong_rule_based'} for arm in scope)
                or len(scope) != len(set(scope))):
            return result('fail', 'invalid_configuration', ['final_source_critical_error_arms must be a nonempty unique list of allowed arms'])
        critical_arms = list(scope)
        threshold = ('Every planned final-stage first attempt source-reviewed and four original input/wire files hash-bound; '
                     'zero critical source errors only for declared arms: ' + ', '.join(critical_arms)
                     + '. Findings in other arms remain descriptive and fully reported.')
    execution = protocol.get('execution')
    expected_count = execution.get('planned_total_target_calls') if isinstance(execution, dict) else None
    if type(expected_count) is not int or expected_count <= 0:
        return result('fail', 'invalid_configuration', ['Final source-review denominator must come from declared planned_total_target_calls'])
    if not required_fields:
        return result('fail', 'invalid_configuration', ['Required source-review schema is unavailable'], expected_count)
    declared_cells = None
    if 'final_source_review_required_cells' in requirements:
        cells = requirements['final_source_review_required_cells']
        def cell_key(row, *, declaration=False):
            fields = {'split', 'case_id', 'round', 'arm'}
            if (not isinstance(row, dict) or declaration and set(row) != fields
                    or row.get('split') not in ('development', 'evaluation')
                    or row.get('arm') not in ('weak_first_hit', 'strong_rule_based')
                    or not isinstance(row.get('case_id'), str) or not row['case_id'].strip()
                    or type(row.get('round')) is not int or row['round'] < 1):
                raise ValueError('Invalid declared final source-review grid cell')
            return (row['split'], row['case_id'], row['round'], row['arm'])
        try:
            if not isinstance(cells, list) or not cells or len(cells) != expected_count:
                raise ValueError('Final source-review grid length differs from declared target count')
            declared_cells = {cell_key(row, declaration=True) for row in cells}
            if len(declared_cells) != expected_count:
                raise ValueError('Duplicate declared final source-review grid cell')
        except (ValueError, TypeError):
            return result('fail', 'invalid_configuration', ['Final source-review required cells must be a complete unique valid four-field grid'], expected_count)
    criteria_sha = None
    criteria_fields = ('final_source_review_criteria_file', 'final_source_review_criteria_sha256')
    if any(field in requirements for field in criteria_fields):
        relative, criteria_sha = (requirements.get(field) for field in criteria_fields)
        if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
                or not (stage.parent / relative).resolve().is_relative_to(stage.parent.resolve())
                or not isinstance(criteria_sha, str) or len(criteria_sha) != 64
                or any(char not in '0123456789abcdef' for char in criteria_sha)):
            return result('fail', 'invalid_configuration', ['Source-review criteria path/hash declaration is invalid'], expected_count)
        criteria_path = stage.parent / relative
        if not criteria_path.is_file() or hashlib.sha256(criteria_path.read_bytes()).hexdigest() != criteria_sha:
            return result('fail', 'invalid_configuration', ['Source-review criteria file is missing or changed'], expected_count)
    matrix_path = stage / 'trial-matrix.json'
    if not matrix_path.exists():
        return result('pending', 'missing_matrix', [], expected_count)
    try:
        matrix = read(matrix_path)
    except (ValueError, OSError):
        return result('fail', 'invalid_matrix', ['Final trial matrix cannot be read'], expected_count)
    trials = matrix.get('trials', []) if isinstance(matrix, dict) else []
    if (not isinstance(matrix, dict) or matrix.get('stage') != 'final'
            or not isinstance(trials, list)
            or any(not isinstance(row, dict) or row.get('split') not in ('development', 'evaluation') for row in trials)):
        return result('fail', 'invalid_matrix', ['Only the declared final development/evaluation matrix can satisfy final source safety'], expected_count)
    if declared_cells is not None:
        try:
            actual_cells = {cell_key(row) for row in trials}
            if len(trials) != len(actual_cells) or actual_cells != declared_cells:
                raise ValueError('Final source-review matrix differs from the declared grid')
        except (ValueError, TypeError):
            return result('fail', 'invalid_matrix', ['Final matrix must exactly match every declared split/case/round/arm cell'], expected_count)
    if any(None in trial_key(row) or not isinstance(row.get('directory'), str)
            or not (stage / row['directory']).resolve().is_relative_to(stage.resolve()) for row in trials):
        return result('fail', 'invalid_matrix', ['Final trial key or directory is invalid'], expected_count)
    if len(trials) != expected_count or len({trial_key(row) for row in trials}) != expected_count:
        return result('fail', 'invalid_matrix', ['Final planned unique denominator differs from protocol'], expected_count)
    matrix_arms = {row.get('arm') for row in trials}
    if critical_arms is not None and not set(critical_arms) <= matrix_arms:
        return result('fail', 'invalid_configuration', ['Declared critical-error arm is absent from the final matrix'], expected_count)
    required_arm_count = sum(critical_arms is None or row.get('arm') in critical_arms for row in trials)
    base_gate, source_verified = validate_source_reviews(review, stage, required_fields, expected_count)
    errors = list(base_gate['observed']['validation_errors'])
    expected = {trial_key(row): row for row in trials}
    bound = {}
    for key, row in source_verified.items():
        directory = stage / expected[key]['directory']
        row_errors = []
        if criteria_sha is not None and row.get('source_review_criteria_sha256') != criteria_sha:
            row_errors.append('Review criteria hash differs from the preregistered source criteria')
        if row.get('split') != expected[key].get('split'):
            row_errors.append('Review split differs from final trial matrix')
        if not directory.resolve().is_relative_to(stage.resolve()):
            row_errors.append('Review directory is outside the final stage')
        else:
            bindings = row.get('reviewed_file_sha256', {})
            if not isinstance(bindings, dict):
                bindings = {}
            for name in ('pilot-report.json', 'actual-input-receipt.json',
                         'actual-wire-attempt-receipts.json', 'actual-wire-validation.json'):
                path = directory / name
                if not path.is_file() or bindings.get(name) != hashlib.sha256(path.read_bytes()).hexdigest():
                    row_errors.append('Missing or changed source-review file binding: ' + name)
        if row_errors:
            errors.append({'trial_key': key, 'errors': row_errors})
        else:
            bound[key] = row
    critical = sum(len(row['critical_errors']) for row in source_verified.values())
    per_arm_critical = {arm: sum(len(row['critical_errors']) for row in source_verified.values() if row['arm'] == arm)
                        for arm in sorted(matrix_arms)}
    required_critical = critical if critical_arms is None else sum(per_arm_critical[arm] for arm in critical_arms)
    # Explicitly invalid review snapshots or known critical findings fail even
    # while other reviews are pending. Missing reviews never become safe.
    invalid_bindings = len(bound) != len(source_verified)
    # The base validator's only non-structural failure can be its all-arm
    # critical count. Override that one cause only for an explicit scoped
    # protocol, with a completed, terminal, fully bound review snapshot.
    scoped_complete = (critical_arms is not None and critical > 0 and required_critical == 0
                       and not errors and len(bound) == expected_count
                       and isinstance(review, dict) and review.get('status') == 'completed'
                       and base_gate['status'] == 'fail')
    if required_critical or invalid_bindings or (base_gate['status'] == 'fail' and not scoped_complete):
        return result('fail', 'failed', errors, expected_count, len(bound), critical, bound)
    if base_gate['status'] == 'pass' or scoped_complete:
        return result('pass', 'completed', errors, expected_count, len(bound), critical, bound)
    state = 'missing' if review is None else 'pending'
    return result('pending', state, errors, expected_count, len(bound), critical, bound)

def memory_preparation_receipt_gate(protocol, stage, replay):
    """Bind actual pre-answer store snapshots to semantic offline replay.

    The public gate contains counts/hashes only. Complete private records and
    decisions stay in the local sidecar; byte integrity is not source truth.
    """
    required=protocol.get('memory_preparation_receipt_required')
    if required is None or required is False:return None
    threshold='Every planned first attempt has an actual complete private memory-preparation receipt, frozen controls, and matching semantic replay bound to its raw file hash.'
    observed={'planned_trials':0,'validated_actual_receipts':0,'replay_bound_receipts':0,'missing_receipts':0,'errors':[]}
    if required is not True:return {'status':'fail','observed':observed,'threshold':threshold}
    matrix_path=stage/'trial-matrix.json'
    if not matrix_path.exists():return {'status':'pending','observed':observed,'threshold':threshold}
    from stability_memory_preparation import validate_private_memory_preparation_receipt
    matrix=read(matrix_path);trials=matrix.get('trials',[]);observed['planned_trials']=len(trials)
    planned_keys=[trial_key(row) for row in trials]
    if not trials or len(planned_keys)!=len(set(planned_keys)):
        observed['errors'].append('Invalid or duplicate planned memory-preparation denominator.')
    replay_rows=replay.get('rows',[]) if isinstance(replay,dict) else []
    replay_counts=Counter(trial_key(row) for row in replay_rows)
    by_key={trial_key(row):row for row in replay_rows}
    for trial in trials:
        directory=stage/trial['directory'];path=directory/'private-memory-preparation-receipts.json'
        if not path.exists():observed['missing_receipts']+=1;continue
        try:
            trial_protocol=read(directory/'pilot-protocol.json')
            if not study_trial_controls_match(protocol,trial_protocol):raise ValueError('Frozen control mismatch')
            validate_private_memory_preparation_receipt(read(path),
                expected_profile=trial_protocol.get('target_memory_profile',{}),
                expected_capacity=trial_protocol['target_memory_capacity'],expected_observation_count=1)
            observed['validated_actual_receipts']+=1
            row=by_key.get(trial_key(trial),{})
            wire_path=directory/'actual-wire-validation.json'
            wire=read(wire_path) if wire_path.exists() else {}
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if (replay_counts[trial_key(trial)]==1 and row.get('status')=='compared'
                    and row.get('memory_preparation_compared') is True
                    and row.get('memory_preparation_receipt_sha256')==digest
                    and (wire.get('evidence_sha256') or {}).get(path.name)==digest):
                observed['replay_bound_receipts']+=1
        except (ValueError,KeyError,TypeError,OSError):
            observed['errors'].append({key:trial.get(key) for key in ('split','case_id','round','arm')})
    complete=(not observed['errors'] and observed['planned_trials']>0
        and observed['validated_actual_receipts']==observed['replay_bound_receipts']==observed['planned_trials']
        and replay.get('status')=='passed' and replay.get('memory_preparation_receipt_required') is True
        and replay.get('memory_preparation_comparisons')==observed['planned_trials'])
    execution_path=stage/'study-execution.json';execution=read(execution_path) if execution_path.exists() else {}
    terminal=execution.get('status') in {'completed','partial_failure'}
    status='pass' if complete else 'fail' if observed['errors'] or terminal and replay.get('status')!='pending' else 'pending'
    return {'status':status,'observed':observed,'threshold':threshold}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--stage',choices=['development-pilot','final','safety-guards'],default='final');ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();root=a.root.resolve();stage=root/a.stage;protocol=read(root/'study-protocol.json');selected=read(root/'selected-metadata.json');rounds=[1] if a.stage=='development-pilot' else [1,2,3];arms=['weak_first_hit','strong_rule_based']
    reference=root.parent/'longmemeval-identity-conservative-final-20261021';suite=read(reference/'regression-4096/run-01/suite-manifest.json');types={'multi-session':'multi-session','temporal-reasoning':'temporal-reasoning'}
    dev=[{'question_id':m['case_id'],'question_type':types.get(m['category'],m['category'])} for m in suite['cases']]
    cohort_layout={}
    if a.stage=='development-pilot':
        cohorts=[]
        for cohort in pilot_cohorts(protocol):
            split=cohort['split']
            if split in cohort_layout:raise ValueError('Each pilot cohort needs a distinct complete-grid split.')
            cohort_layout[split]={'rounds':list(range(1,cohort['repetitions']+1)),'arms':cohort['arms']}
            cohorts.append((split,[{'question_id':qid,'question_type':(read(stage/'inputs'/split/(qid+'.json'))[0].get('question_type','not_recorded') if (stage/'inputs'/split/(qid+'.json')).exists() else 'not_materialized')} for qid in cohort['selected_ids']]))
    else:cohorts=[('development',dev)]
    if a.stage=='final':cohorts.append(('evaluation',selected['selected_metadata']))
    guardmeta=read(root/'guards/conversation-cases.json')['cases'] if (root/'guards/conversation-cases.json').exists() else []
    if a.stage=='safety-guards':cohorts=[]
    if a.stage in {'final','safety-guards'} and guardmeta:cohorts.append(('safety_guards',[{'question_id':c['case_id'],'question_type':'synthetic-safety-control','question':c['question']} for c in guardmeta]))
    guardreview=read(root/'safety-guards/source-grounded-review.json') if (root/'safety-guards/source-grounded-review.json').exists() else None
    review_fields=read(root/'guards/source-review-schema.json').get('required_trial_fields', []) if (root/'guards/source-review-schema.json').exists() else []
    guard_gate,guard_reviews=validate_source_reviews(guardreview,root/'safety-guards',review_fields,36)
    sidecar_path=stage/'case-source-reviews.json'
    sidecar=read(sidecar_path) if sidecar_path.exists() else None
    case_review_gate,case_reviews=validate_source_reviews(sidecar,stage,[],None)
    final_case_gate=None
    if a.stage=='final':
        full_final_review=final_case_source_review_gate(protocol,stage,sidecar,review_fields)
        if full_final_review is not None:
            final_case_gate,case_reviews=full_final_review
            case_review_gate=final_case_gate
    splits=[];allruns=[]
    for split,members in cohorts:
        cases=[];case_stage=root/'safety-guards' if split=='safety_guards' else stage;case_arms=['strong_rule_based'] if split=='safety_guards' else arms;case_rounds=[1,2,3] if split=='safety_guards' else cohort_layout.get(split,{}).get('rounds',rounds)
        case_arms=cohort_layout.get(split,{}).get('arms',case_arms)
        for member in members:
            qid=member['question_id'];source=case_stage/'inputs'/split/(qid+'.json');row=read(source)[0] if source.exists() else None;runs=[]
            for repetition in case_rounds:
                for arm in case_arms:
                    directory=case_stage/'trials'/split/('round-'+str(repetition))/qid/arm;file=directory/'pilot-report.json';report=read(file) if file.exists() else {};receipts=report.get('target_call_receipts',[]);target=receipts[0] if receipts else {};response=target.get('response') or {};meta=response.get('execution_metadata');grades=report.get('semantic_assessments',[]);grade=grades[0] if grades else {};verdict=grade.get('verdict') or {};identity=(directory/'identity-mismatch-receipt.json').exists()
                    trial_protocol_path=directory/'pilot-protocol.json'
                    trial_protocol=read(trial_protocol_path) if trial_protocol_path.exists() else {'grading_output_token_limit':study_grader_cap(protocol)}
                    grade_budget_ok=study_trial_grader_budget_matches(protocol,trial_protocol) and grader_budget_matches(trial_protocol,grade.get('execution'))
                    metadata_source='target_call_receipt'
                    conditions=(report.get('benchmark_result') or {}).get('conditions',[])
                    if conditions and conditions[0].get('cases'):
                        controlled_meta=conditions[0]['cases'][0].get('execution_metadata')
                        meta,enriched=enrich_controlled_identity(meta,controlled_meta)
                        if enriched:metadata_source='target_receipt_with_input_matched_controlled_identity'
                    target_usable=(target.get('status')=='completed' and (meta or {}).get('completion_status')=='complete' and (meta or {}).get('finish_reason')=='stop' and bool((response.get('response_text') or '').strip()))
                    if not report:status='missing';outcome='missing'
                    elif target_usable and grade_budget_ok and len(receipts)==1 and len(grades)==1 and grade.get('status')=='completed' and type(verdict.get('correct')) is bool and not identity:status='completed';outcome='correct' if verdict['correct'] else 'incorrect'
                    elif target_usable and grade_budget_ok and len(receipts)==1 and len(grades)==1 and not identity and grade.get('status')=='uncertain' and verdict.get('correct') is None:status='completed';outcome='uncertain'
                    else:status='error';outcome='error'
                    semantic=valid_semantic_grade(status,grade)
                    extras=read(directory/'agent-execution-receipts.json') if (directory/'agent-execution-receipts.json').exists() else []
                    # Evidence payload and full prompts stay in the private result
                    # artifact for replay; the read-only UI receives execution only.
                    run={'grading_budget':{'study_cap':study_grader_cap(protocol),'protocol_cap':trial_grader_cap(trial_protocol),'protocol_source':budget_source(trial_protocol),'execution_declared_cap':(grade.get('execution') or {}).get('declared_output_token_limit'),'execution_effective_cap':(grade.get('execution') or {}).get('requested_output_token_limit'),'matches':grade_budget_ok},'case_id':qid,'split':split,'target_usable':target_usable,'grading_attempt':public_metadata(grade) if grade else None,'grading_attempts':public_metadata(grades),'round':repetition,'arm':arm,'status':status,'grade_outcome':outcome,'target_status':target.get('status','not_attempted'),'response_text':response.get('response_text'),'semantic_grade':semantic,'execution_metadata':public_metadata(meta or target.get('execution')),'execution_metadata_source':metadata_source,'input_receipt':read(directory/'actual-input-receipt.json') if (directory/'actual-input-receipt.json').exists() else (meta or {}).get('memory_input'),'source_review':({'automatic_guard_findings':{k:verdict.get(k) for k in ['unsupported_hard_merge','unsupported_exact_date','wrong_event_binding','source_contradiction']},'agent_review':guard_reviews.get((qid,repetition,arm)),'rubric_kind':'custom_synthetic_source_safety_not_official_LongMemEval'}) if split=='safety_guards' else case_reviews.get((qid,repetition,arm)),'agent_execution_attempts':[{'agent_role':x.get('agent_role'),'execution':public_metadata(x.get('execution')),'status':x.get('status','completed')} for x in extras],'extra_agent_executions':[{'agent_role':x.get('agent_role'),'execution':public_metadata(x.get('execution')),'status':x.get('status','completed')} for x in extras if x.get('agent_role') not in {'benchmark_pilot_assessment','stability_guard_assessment'}],'identity_mismatch':identity,'failure_diagnostics':failure_diagnostics(report,directory) if status=='error' else None}
                    observation_path=directory/'identity-observation-receipts.json'
                    try:observations=read(observation_path).get('observations',[]) if observation_path.exists() else []
                    except (OSError,ValueError,TypeError):observations=[]
                    try:
                        draft=read(directory/PRIMARY_DRAFT) if (directory/PRIMARY_DRAFT).exists() else None
                        run['answer_validation']=validate_answer_binding(trial_protocol,observation=read_validation_observation(directory),draft=draft,final=response,events=extras)
                    except (OSError,ValueError,TypeError,KeyError):
                        run['answer_validation']={'enabled':answer_validation_enabled(trial_protocol.get('target_memory_profile',{})),'status':'failed','attempted_calls':sum(e.get('agent_role')=='target_answer_validation' for e in extras)}
                    run['source_review_status']=guard_gate['status'] if split=='safety_guards' else case_review_gate['status']
                    run['auxiliary_analysis']=describe_auxiliary(metadata=meta or {},observations=observations,events=extras,trial_protocol=trial_protocol,arm=arm,target_status=target.get('status'),expected_profile=protocol.get('target',{}).get('final_target_profile_flags'))
                    if run['auxiliary_analysis']['degraded'] or run['auxiliary_analysis']['blocked']:
                        run['auxiliary_analysis']['failure_diagnostics']=failure_diagnostics(report,directory)
                    runs.append(run);allruns.append(run)
            cases.append({'case_id':qid,'type':member['question_type'],'question':row.get('question') if row else (member.get('question') if split=='safety_guards' else None),'reference_answer':row.get('answer') if row else None,'runs':runs})
        splits.append({'name':split,'planned_case_ids':[m['question_id'] for m in members],'rounds':case_rounds,'arms':case_arms,'cases':cases})
    execution=read(stage/'study-execution.json') if (stage/'study-execution.json').exists() else {};terminal=execution.get('status') in {'completed','partial_failure'}
    if a.stage=='final' and guardmeta:
        gx=root/'safety-guards/study-execution.json';terminal=terminal and gx.exists() and read(gx).get('status') in {'completed','partial_failure'}
    def gate(observed,threshold,ok,ready=True):return {'status':('pass' if ok else 'fail') if ready and terminal else 'pending','observed':observed,'threshold':threshold}
    main_runs=[r for sp in splits if sp['name']!='safety_guards' for c in sp['cases'] for r in c['runs']]
    n=len(allruns);usable=sum(r['target_usable'] for r in allruns);graded=sum(r['semantic_grade'] is not None and type(r['semantic_grade'].get('correct')) is bool and r['semantic_grade'].get('status')=='completed' for r in allruns);identity=sum(r['target_status']=='completed' and (r['execution_metadata'] or {}).get('reported_model')=='openai/gpt-6-luna' and (r['execution_metadata'] or {}).get('response_source')=='openrouter' for r in allruns)
    role_mismatches=actual_role_mismatches(allruns)
    wire_failures=[]
    if protocol.get('request_contract_required') is True:
        for run in allruns:
            case_stage=root/'safety-guards' if run['split']=='safety_guards' else stage
            path=case_stage/'trials'/run['split']/('round-'+str(run['round']))/run['case_id']/run['arm']/'actual-wire-validation.json'
            proof=read(path) if path.exists() else {}
            directory=path.parent
            bindings=proof.get('evidence_sha256') or {}
            trial_protocol=read(directory/'pilot-protocol.json') if (directory/'pilot-protocol.json').exists() else {}
            required_roles=set(proof.get('required_roles',[]))
            minimum_roles={'target_answer',trial_protocol.get('assessment_role','benchmark_pilot_assessment')}
            if answer_validation_enabled(trial_protocol.get('target_memory_profile',{})):
                minimum_roles.add('target_answer_validation')
                if not {PRIMARY_DRAFT,VALIDATION_OBSERVATIONS}<=set(bindings):wire_failures.append({key:run[key] for key in ('split','case_id','round','arm')})
            wire_ok=(proof.get('status')=='passed' and bindings and study_trial_controls_match(protocol,trial_protocol)
                and minimum_roles<=required_roles and set(proof.get('actual_roles',[]))==required_roles and set(proof.get('roles',{}))==required_roles
                and proof.get('protocol_sha256')==hashlib.sha256((directory/'pilot-protocol.json').read_bytes()).hexdigest()
                and all((directory/name).exists() and hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest for name,digest in bindings.items())
                and {'actual-wire-attempt-receipts.json','pilot-report.json','agent-execution-receipts.json'}<=set(bindings))
            if not wire_ok:wire_failures.append({key:run[key] for key in ('split','case_id','round','arm')})
    replayfile=saved_replay_path(stage);replay=read(replayfile) if replayfile.exists() else {'status':'pending','model_calls':0,'note':'No replay proof yet; hash import is not proof of truth or model behavior.'}
    guard_replayfile=saved_replay_path(root/'safety-guards');guard_replay=read(guard_replayfile) if guard_replayfile.exists() else {'status':'pending','compared_trials':0}
    replay_compared=replay.get('compared_trials',0)+(guard_replay.get('compared_trials',0) if a.stage=='final' and guardmeta else 0)
    main_n=sum(len(c['runs']) for sp in splits if sp['name']!='safety_guards' for c in sp['cases']);guard_n=n-main_n
    replay_complete=replay_is_complete(replay,stage,n if a.stage=='safety-guards' else main_n) and (not (a.stage=='final' and guardmeta) or replay_is_complete(guard_replay,root/'safety-guards',guard_n))
    acceptance={'actual_Luna_identity':gate(identity/n if n else None,1.0,identity==n and not role_mismatches),'usable_targets':gate(usable/n if n else None,1.0,usable==n),'grade_coverage':gate(graded/n if n else None,1.0,graded==n),'input_replay':gate(replay_compared/n if n else None,1.0,replay_complete and replay_compared==n,ready=replayfile.exists() and (not(a.stage=='final' and guardmeta) or guard_replayfile.exists())),'critical_source_safety_guards':{'status':'pending','observed':None,'threshold':'No unsupported hard identity merge or unjustified exact date; separate source review required.'}}
    if guardmeta and a.stage in {'final','safety-guards'}:acceptance['critical_source_safety_guards']=guard_gate
    if final_case_gate is not None:acceptance['final_case_source_safety']=final_case_gate
    preparation_gates=[memory_preparation_receipt_gate(protocol,stage,replay)]
    if a.stage=='final' and guardmeta:preparation_gates.append(memory_preparation_receipt_gate(protocol,root/'safety-guards',guard_replay))
    preparation_gates=[item for item in preparation_gates if item is not None]
    if preparation_gates:
        acceptance['actual_memory_preparation']={
            'status':'fail' if any(item['status']=='fail' for item in preparation_gates) else 'pending' if any(item['status']=='pending' for item in preparation_gates) else 'pass',
            'observed':{'stages':[item['observed'] for item in preparation_gates]},
            'threshold':preparation_gates[0]['threshold']}
    if protocol.get('request_contract_required') is True:
        relevant_replays=[replay]+([guard_replay] if a.stage=='final' and guardmeta else [])
        wire_replay_ok=all(proof.get('wire_contract_required') is True and all(row.get('wire_contract_required') is True and row.get('wire_http_attempt_comparisons',0)>=len(row.get('wire_required_roles',[])) and {'target_answer','stability_guard_assessment' if row.get('split')=='safety_guards' else 'benchmark_pilot_assessment'}<=set(row.get('wire_required_roles',[])) and set(row.get('wire_required_roles',[]))==set(row.get('wire_compared_roles',[])) for row in proof.get('rows',[])) for proof in relevant_replays)
        acceptance['actual_wire_request_contracts']=gate({'failed_trial_bindings':len(wire_failures),'wire_replay_complete':wire_replay_ok},'All actual wire receipts bind to trial files and pure-builder replay',not wire_failures and wire_replay_ok,ready=replayfile.exists())
    evaluation=next((s for s in splits if s['name']=='evaluation'),None);statistics={}
    if evaluation:
        vectors={arm:[[next(r for r in c['runs'] if r['arm']==arm and r['round']==rep)['semantic_grade'] for rep in rounds] for c in evaluation['cases']] for arm in arms};complete=all(g is not None and g.get('status')=='completed' and type(g.get('correct')) is bool for rows in vectors.values() for row in rows for g in row)
        if complete:
            binary={arm:[[int(g['correct']) for g in row] for row in rows] for arm,rows in vectors.items()};counts={arm:[sum(row[i] for row in rows) for i in range(len(rounds))] for arm,rows in binary.items()};unanimous=sum(len(set(row))==1 for rows in binary.values() for row in rows)/(len(evaluation['cases'])*2);strong=sum(counts['strong_rule_based'])/(len(evaluation['cases'])*len(rounds));weak=sum(counts['weak_first_hit'])/(len(evaluation['cases'])*len(rounds));spread=max(counts['strong_rule_based'])-min(counts['strong_rule_based'])
            acceptance.update(three_grade_unanimity=gate(unanimous,0.8,unanimous>=0.8),Strong_round_correct_range=gate(spread,2,spread<=2),Strong_mean_accuracy=gate(strong,0.75,strong>=0.75),Strong_at_least_Weak=gate(strong-weak,0,strong>=weak))
            differences=[sum(s)/len(rounds)-sum(w)/len(rounds) for s,w in zip(binary['strong_rule_based'],binary['weak_first_hit'])];rng=random.Random(20261021);bootstrap=sorted(sum(rng.choice(differences) for _ in differences)/len(differences) for _ in range(10000))
            statistics={'per_arm_round_correct_counts':counts,'case_arm_grade_vectors':binary,'all_three_correct_unique_question_Wilson95':{arm:wilson(sum(all(row) for row in rows),len(rows)) for arm,rows in binary.items()},'paired_unique_question_cluster_bootstrap95_Strong_minus_Weak':[bootstrap[249],bootstrap[9749]],'interpretation':'Smallengineeringstudy; repeatedresponsesarenotindependentquestions, noformalsignificanceclaim.'}
        else:
            for name,threshold in [('three_grade_unanimity',0.8),('Strong_round_correct_range',2),('Strong_mean_accuracy',0.75),('Strong_at_least_Weak',0)]:acceptance[name]={'status':'pending','observed':None,'threshold':threshold}
    if a.stage=='development-pilot':
        acceptance.update({key:{**value,'status':value['status'] if terminal else 'pending'} for key,value in pilot_quality_gates(protocol,main_runs).items()})
    auxiliary_stages={a.stage:summarize_auxiliary(allruns if a.stage=='safety-guards' else main_runs)}
    if a.stage=='final':auxiliary_stages['safety-guards']=summarize_auxiliary([run for run in allruns if run['split']=='safety_guards'])
    auxiliary_gate=auxiliary_acceptance_gate(protocol,a.stage,auxiliary_stages,terminal)
    if auxiliary_gate is not None:acceptance['auxiliary_validation_coverage']=auxiliary_gate
    validation_summary=summarize_answer_validation(allruns)
    if answer_validation_enabled(protocol.get('target',{}).get('final_target_profile_flags',{})):
        validation_replays=[replay]+([guard_replay] if a.stage=='final' and guardmeta else [])
        validation_replay_complete=all(proof.get('answer_validation_input_comparisons')==proof.get('planned_trials') for proof in validation_replays)
        acceptance['answer_validation_contracts']=gate(validation_summary,'Every enabled common-arm target has one separately metered, bound answer review and strict replay; no semantic correctness claim',validation_summary['enabled']==n and validation_summary['validated']==n and validation_replay_complete,ready=terminal and replayfile.exists())
    acceptance['frozen_protocol_binding']=frozen_protocol_binding(root,[a.stage,'safety-guards'] if a.stage=='final' else [a.stage])
    states=[g['status'] for g in acceptance.values()];acceptance_results={'overall_status':'fail' if 'fail' in states else ('pending' if 'pending' in states else 'pass'),'gates':acceptance,'planned_denominator':n,'actual_model_role_mismatches':role_mismatches,'status_counts':dict(Counter(r['status'] for r in allruns)),'grade_outcome_counts':dict(Counter(r['grade_outcome'] for r in allruns))}
    payload={'study_id':root.name+':'+a.stage,'created_at':datetime.now(timezone.utc).isoformat(),'protocol':protocol,'provenance':{'dataset_sha256':selected['dataset_sha256'],'selection_commitment':read(root/'selection-commitment.json'),'source_disjoint_metadata_only_selection':source_reuse_scope(selected)['full_source_disjoint'],'source_reuse_scope':source_reuse_scope(selected),'integrity_note':'Hash verifies exact bytes only, not authenticity, scientific validity or truth.'},'acceptance_results':acceptance_results,'splits':splits,'statistics':statistics,'answer_validation':validation_summary,'auxiliary_analysis':{'stages':auxiliary_stages,'interpretation':'Strong is the entire preregistered adaptive condition with or without accepted identity suggestions; valid/degraded subgroup grades are descriptive, not causal comparisons or equal total call cost.'},'replay':{**replay,'independent_safety_guards':guard_replay if a.stage=='final' else None},'limitations':['Development and first evaluation remain separate.','Originalautomaticgrade andsource-safetyreviewarenotinterchangeable.','Missinggrader/invalidgraderiserror,notuncertainorincorrect.','Binaryofficialrubricnormallyhasuncertain=0; anabstainingresponsewithfalsegradeisincorrect,notrelabeleduncertain.','No fullconversation source or credentials are exported.','Evidence-stageextraexecutioncost isseparate fromsamefinal-answerbudget.','A refused auxiliary suggestion is not a provider/model fallback or an auxiliary success. The same planned final model answers from its existing private memories; degradation remains visible.','Valid/degraded subgroup outcomes are descriptive only; Strong is an adaptive whole condition, not an isolated retrieval or equal-total-cost comparison.']}
    payload_json=json.dumps(payload,ensure_ascii=False,separators=(',',':'));envelope={'schema_version':'memory-stability-study-package-v1','payload_json':payload_json,'payload_sha256':hashlib.sha256(payload_json.encode('utf-8')).hexdigest()};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(envelope,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'output':str(a.output),'planned_runs':n,'acceptance':acceptance_results['overall_status'],'payload_sha256':envelope['payload_sha256']}))

if __name__=='__main__':main()
