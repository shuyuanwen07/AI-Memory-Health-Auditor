"""Strict auxiliary refusal bindings and descriptive, non-pooled study counts."""
from collections import defaultdict
from fractions import Fraction
import hashlib
import json


def canonical_sha256(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def agent_identity_matches(execution, model, role, cap):
    return (isinstance(execution, dict) and execution.get('provider') == 'openrouter'
            and execution.get('model') == model and execution.get('reported_model') == model
            and execution.get('agent_role') == role
            and type(execution.get('requested_output_token_limit')) is int
            and execution.get('requested_output_token_limit') == cap
            and execution.get('declared_output_token_limit') == cap)


def validate_final_identity_binding(*, test, audit, memory_input, protocol, evidence_calls, observation):
    """Return a failure label; a refused advisory must bind the actual observation."""
    advisory = memory_input.get('identity_advisory_sha256')
    failure_hash = memory_input.get('identity_failure_receipt_sha256')
    failure = getattr(test, 'target_identity_failure_receipt', None)
    offered = getattr(test, 'target_identity_evidence', None)
    if not evidence_calls:
        return 'unobserved_identity_binding' if advisory or failure_hash or failure or offered else None
    if bool(advisory) == bool(failure_hash):
        return 'missing_or_conflicting_identity_stage_binding'
    if advisory:
        if failure is not None or not isinstance(offered, dict) or canonical_sha256(offered) != advisory:
            return 'invalid_identity_advisory_binding'
        if not isinstance(observation, dict) or observation.get('status') != 'completed' or observation.get('output_data') != offered:
            return 'identity_advisory_not_validated_by_actual_stage'
        return None
    if (protocol.get('target_memory_profile', {}).get('identity_analysis_failure_policy', 'fail_closed') != 'continue_without_advisory'
            or offered is not None or not isinstance(failure, dict)):
        return 'unregistered_identity_degradation'
    from app.memory_agent.identity_failure import build_identity_failure_receipt, identity_failure_receipt_sha256
    from app.target_ai.rule_based import selected_memory_context
    rebuilt = build_identity_failure_receipt(observation=observation, provider=protocol['provider'], model=protocol['model'],
        max_output_tokens=protocol['target_memory_profile'].get('identity_analysis_output_token_limit', 4096),
        question=test.prompt, context=selected_memory_context(test, audit.target_configuration),
        **({'reasoning_effort':protocol['target_memory_profile']['identity_analysis_reasoning_effort']} if protocol.get('target_memory_profile',{}).get('identity_analysis_reasoning_effort') is not None else {}))
    if rebuilt is None or rebuilt != failure or identity_failure_receipt_sha256(rebuilt) != failure_hash:
        return 'unbound_identity_failure_receipt'
    return None


def failure_receipt_matches_observation(receipt, observation, execution, profile, model):
    if not isinstance(receipt, dict) or not isinstance(observation, dict):
        return False
    raw = observation.get('raw_input_payload') or {}
    diagnostics = observation.get('error_diagnostics') or {}
    checks = {'provider': 'provider', 'model': 'model', 'reported_model': 'reported_model', 'agent_role': 'agent_role',
              'prompt_fingerprint': 'prompt_fingerprint', 'input_fingerprint': 'input_fingerprint',
              'requested_output_token_limit': 'requested_output_token_limit', 'declared_output_token_limit': 'declared_output_token_limit',
              'configured_output_token_cap': 'configured_output_token_cap', 'http_status': 'last_http_status',
              'finish_reason': 'reported_finish_reason', 'execution_status': 'status', 'response_choice_count':'response_choice_count',
              'request_attempts': 'request_attempts', 'failed_http_attempts': 'failed_http_attempts', 'output_fingerprint': 'output_fingerprint'}
    if (receipt.get('version') not in {'target-identity-failure-receipt-v1','target-identity-failure-receipt-v2'}
            or receipt.get('analysis_version') != observation.get('prompt_template_version')
            or receipt.get('phase') != diagnostics.get('phase')
            or any(receipt.get(key) != execution.get(value) for key, value in checks.items())
            or not agent_identity_matches(execution, model, 'target_identity_evidence', profile.get('identity_analysis_output_token_limit', 4096))
            or raw.get('question') is None or not isinstance(raw.get('selected_context'), list)
            or receipt.get('question_sha256') != canonical_sha256(raw['question'])
            or receipt.get('source_context_sha256') != canonical_sha256(raw['selected_context'])
            or execution.get('provider')!='openrouter' or type(execution.get('response_choice_count')) is not int or execution.get('response_choice_count')!=1
            or execution.get('last_http_status') != 200 or execution.get('request_attempts') != 1
            or execution.get('failed_http_attempts') != 0):
        return False
    if receipt.get('version')=='target-identity-failure-receipt-v2':
        if (receipt.get('request_contract_sha256')!=execution.get('request_contract_sha256')
                or not execution.get('request_contract_sha256')):return False
    if receipt.get('reason') == 'invalid_identity_contract':
        return (observation.get('error_code') == 'invalid_identity_contract' and diagnostics.get('phase') == 'output_validation'
                and execution.get('status') == 'parsed' and execution.get('reported_finish_reason') == 'stop'
                and execution.get('output_fingerprint') == canonical_sha256(observation.get('raw_model_draft')))
    return (receipt.get('reason') == 'provider_output_truncated' and observation.get('error_code') == 'PipelineRequestError'
            and diagnostics.get('phase') == 'provider_request' and execution.get('status') == 'failed'
            and execution.get('reported_finish_reason') == 'length' and execution.get('output_fingerprint') is None)


def describe_auxiliary(*, metadata, observations, events, trial_protocol, arm, target_status, expected_profile=None):
    """A cell's category is distinct from actual HTTP/analysis success."""
    profile = trial_protocol.get('target_memory_profile', {})
    planned_profile=expected_profile if expected_profile else profile
    eligible = arm == 'strong_rule_based' and planned_profile.get('identity_analysis', 'off') == 'evidence_links'
    profile_matches=all(profile.get(key,default)==planned_profile.get(key,default) for key,default in [('identity_analysis','off'),('identity_analysis_failure_policy','fail_closed'),('identity_analysis_output_token_limit',4096),('identity_analysis_reasoning_effort',None)])
    identity_events = [event for event in events if event.get('agent_role') == 'target_identity_evidence']
    if trial_protocol.get('request_contract_required') is True and identity_events:
        from stability_request_contracts import validate_contract
        for event in identity_events:
            try:validate_contract(trial_protocol,'target_identity_evidence',(event.get('execution') or {}).get('request_contract'))
            except ValueError:profile_matches=False
    observations = [row for row in observations if isinstance(row, dict)]
    attempts = max(len(identity_events), len(observations))
    identity = metadata.get('identity_analysis') if isinstance(metadata, dict) else None
    identity = identity if isinstance(identity, dict) else {}
    memory_input = metadata.get('memory_input') or {} if isinstance(metadata, dict) else {}
    latest = observations[-1].get('last_observation') if observations else None
    latest = latest if isinstance(latest, dict) else {}
    status = 'unknown' if eligible or attempts else 'not_enabled'
    if not eligible and attempts:
        status = 'blocked'
    elif eligible and profile_matches and identity.get('status') == 'skipped_not_applicable' and not attempts:
        status = 'skipped'
    elif (profile_matches and attempts == 1 and len(observations) == 1 and len(identity_events) == 1
            and latest.get('execution') == identity_events[0].get('execution')):
        if (latest.get('status') == 'completed' and identity.get('status') == 'analyzed'
                and isinstance(latest.get('output_data'),dict)
                and canonical_sha256(latest['output_data'])==memory_input.get('identity_advisory_sha256')
                and not memory_input.get('identity_failure_receipt_sha256')
                and agent_identity_matches(identity_events[0].get('execution'),trial_protocol.get('model'),'target_identity_evidence',profile.get('identity_analysis_output_token_limit',4096))):
            status = 'validated'
        elif latest.get('status') == 'failed':
            failure = identity.get('failure_receipt')
            failure_hash = identity.get('failure_receipt_sha256')
            if (eligible and identity.get('status') == 'degraded_without_advisory' and identity.get('advisory_applied') is False
                    and isinstance(failure, dict) and canonical_sha256(failure) == failure_hash
                    and memory_input.get('identity_failure_receipt_sha256') == failure_hash
                    and not memory_input.get('identity_advisory_sha256') and target_status == 'completed'
                    and profile.get('identity_analysis_failure_policy','fail_closed')=='continue_without_advisory'
                    and failure_receipt_matches_observation(failure,latest,identity_events[0].get('execution') or {},profile,trial_protocol.get('model'))):
                status = 'degraded'
            elif target_status != 'completed':
                status = 'blocked'
    execution = identity_events[-1].get('execution') if identity_events else latest.get('execution')
    execution = execution if isinstance(execution, dict) else {}
    return {'planned_eligible': eligible, 'attempted_calls': attempts, 'status': status,
            'validated': status == 'validated', 'degraded': status == 'degraded', 'blocked': status == 'blocked',
            'skipped': status == 'skipped', 'unknown': status == 'unknown', 'unexpected_calls': bool(attempts and not eligible),
            'runtime_status':identity.get('status'),'profile_matches_study':profile_matches,'http_execution_status': execution.get('status'), 'analyzer_status': latest.get('status'),
            'advisory_applied': status == 'validated', 'failure_receipt': identity.get('failure_receipt') if status == 'degraded' else None,
            'failure_receipt_sha256': identity.get('failure_receipt_sha256') if status == 'degraded' else None}


def summarize_auxiliary(runs):
    grouped = defaultdict(lambda: dict(planned_eligible=0, attempted=0, validated=0, degraded=0, blocked=0, skipped=0, unknown=0, unexpected_calls=0, degraded_unreviewed=0))
    total = dict(planned_eligible=0, attempted=0, validated=0, degraded=0, blocked=0, skipped=0, unknown=0, unexpected_calls=0, degraded_unreviewed=0)
    for run in runs:
        evidence = run.get('auxiliary_analysis') or {}
        key = (run['split'], run['arm'], run['round'])
        counts = grouped[key]
        values = {'planned_eligible': int(evidence.get('planned_eligible') is True), 'attempted': evidence.get('attempted_calls', 0),
                  **{name: int(evidence.get(name) is True and (evidence.get('planned_eligible') is True or name=='unexpected_calls')) for name in ('validated', 'degraded', 'blocked', 'skipped', 'unknown', 'unexpected_calls')}}
        review = run.get('source_review')
        values['degraded_unreviewed'] = int(evidence.get('degraded') is True and run['split'] != 'safety_guards'
            and not (run.get('source_review_status') == 'pass' and isinstance(review, dict) and review.get('critical_errors') == []))
        for name, value in values.items():
            counts[name] += value
            total[name] += value
    total['eligible_accounting_complete']=sum(total[key] for key in ('validated','degraded','blocked','skipped','unknown'))==total['planned_eligible']
    total['validation_coverage'] = total['validated'] / total['attempted'] if total['attempted'] else None
    total['degraded_rate'] = total['degraded'] / total['attempted'] if total['attempted'] else None
    return {'total': total, 'by_split_arm_round': [{'split': split, 'arm': arm, 'round': round_, **counts}
             for (split, arm, round_), counts in grouped.items()],
            'denominator_note': 'Attempted logical auxiliary calls; degraded is never validated. Planned eligible cells retain skipped/blocked/unknown outcomes.'}


def auxiliary_acceptance_gate(protocol, stage, stage_summaries, terminal):
    requirements = protocol.get('additional_acceptance_requirements')
    if not isinstance(requirements, dict) or stage not in requirements.get('applies_to_stages', []):
        return None
    threshold = Fraction(str(requirements['auxiliary_validation_coverage_minimum']))
    minimum = requirements.get('auxiliary_minimum_attempted_calls', 1)
    review_required = requirements.get('degraded_final_source_review_required', False)
    critical_max = requirements.get('degraded_final_source_critical_errors_max', 0)
    review_stages=requirements.get('degraded_source_review_stages',['final','development-pilot'] if protocol.get('request_contract_required') is True else ['final'])
    if type(review_required) is not bool or type(critical_max) is not int or critical_max != 0:
        raise ValueError('Unsupported degraded source review requirements.')
    if not 0 <= threshold <= 1 or type(minimum) is not int or minimum < 1:
        raise ValueError('Invalid preregistered auxiliary acceptance requirements.')
    required = ['final', 'safety-guards'] if stage == 'final' else [stage]
    observations = []
    passed = True
    for name in required:
        counts = stage_summaries.get(name, {}).get('total', {})
        attempted = counts.get('attempted', 0); validated = counts.get('validated', 0)
        okay = (attempted >= minimum and threshold.denominator * validated >= threshold.numerator * attempted
                and counts.get('unknown', 0) == 0 and counts.get('unexpected_calls', 0) == 0
                and counts.get('eligible_accounting_complete') is True
                and (name not in review_stages or not review_required or counts.get('degraded_unreviewed', 0) == 0))
        observations.append({'stage': name, **counts, 'meets_threshold': okay})
        passed = passed and okay
    return {'status': ('pass' if passed else 'fail') if terminal else 'pending', 'observed': observations,
            'threshold': {'validation_coverage_minimum': float(threshold), 'minimum_attempted_calls_per_stage': minimum,
                          'unknown_allowed': 0, 'unexpected_calls_allowed': 0, 'degraded_final_source_review_required': review_required, 'degraded_final_source_critical_errors_max': critical_max},
            'interpretation': 'Each required stage independently passes; degraded final answers are reviewed separately and are never auxiliary successes.'}


def frozen_protocol_binding(root, stages):
    """Bind acceptance to each stage's frozen protocol bytes, without source comparisons."""
    protocol_path = root / 'study-protocol.json'
    actual = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    observations = []
    for name in stages:
        path = root / name / 'FROZEN.json'
        try:
            frozen = json.loads(path.read_text())
            expected = frozen.get('protocol_sha256')
        except (OSError, ValueError, TypeError, AttributeError):
            expected = None
        selection_ok=True
        protocol=json.loads(protocol_path.read_text())
        if protocol.get('request_contract_required') is True or (isinstance(protocol.get('selection'),dict) and 'helper_path' in protocol['selection']):
            try:
                from stability_configuration import selection_binding
                selected=json.loads((root/'selected-metadata.json').read_text())
                bound=selection_binding(protocol,selected,root,root.parents[1])
                selection_ok=bound=={'helper_path':frozen.get('selection_helper_path'),'helper_sha256':frozen.get('selection_script_sha256'),'fixture_manifest':frozen.get('selection_fixture_manifest')}
            except (OSError,ValueError,TypeError,KeyError,AttributeError):selection_ok=False
        observations.append({'stage': name, 'protocol_sha256': actual,'selection_binding_matches':selection_ok,
            'frozen_protocol_sha256': expected, 'matches': isinstance(expected, str) and expected == actual and selection_ok})
    return {'status': 'pass' if all(row['matches'] for row in observations) else 'fail',
        'observed': observations, 'threshold': 'Exact current protocol bytes equal every required stage FROZEN.protocol_sha256.'}
