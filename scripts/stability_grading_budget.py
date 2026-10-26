"""Explicit stability grader budgets; 1024 is retained only for legacy protocols."""
import os

LEGACY_GRADER_CAP = 1024


def valid_cap(value):
    if type(value) is not int or not 256 <= value <= 12000:
        raise ValueError('Grader output token cap must be an integer from 256 to 12000.')
    return value


def study_grader_cap(protocol):
    return valid_cap(protocol.get('grading', {}).get('output_token_limit', LEGACY_GRADER_CAP))


def trial_grader_cap(protocol):
    return valid_cap(protocol.get('grading_output_token_limit', LEGACY_GRADER_CAP))


def study_trial_grader_budget_matches(study_protocol, trial_protocol):
    return study_grader_cap(study_protocol) == trial_grader_cap(trial_protocol)


def budget_source(protocol):
    return 'trial_protocol' if 'grading_output_token_limit' in protocol else 'legacy_1024'


def preflight_grader_budget(cap, environ=None):
    cap = valid_cap(cap)
    env = os.environ if environ is None else environ
    raw = env.get('PIPELINE_MAX_OUTPUT_TOKENS', '').strip()
    if raw and (not raw.isascii() or not raw.isdigit()):
        raise ValueError('Invalid PIPELINE_MAX_OUTPUT_TOKENS.')
    configured = valid_cap(int(raw)) if raw else None
    effective = min(cap, configured) if configured is not None else cap
    return {'planned_grader_output_token_limit': cap, 'configured_pipeline_output_token_cap': configured,
            'expected_effective_grader_output_token_limit': effective, 'passed': effective == cap}


def grader_budget_matches(protocol, execution):
    expected = trial_grader_cap(protocol)
    if not isinstance(execution, dict):
        return False
    # Older meters may lack declared_output_token_limit; the effective field is
    # still the historical actual request budget, never rewritten to the new cap.
    effective = execution.get('requested_output_token_limit')
    declared = execution.get('declared_output_token_limit', effective)
    return type(declared) is int and type(effective) is int and declared == expected and effective == expected


def output_budget_ledger(protocol):
    target_cap = valid_cap(protocol['target']['output_token_limit'])
    grade_cap = study_grader_cap(protocol)
    evidence_cap = valid_cap(protocol['target']['final_target_profile_flags'].get('identity_analysis_output_token_limit', 4096))
    execution = protocol['execution']; pilot = protocol['development_pilot']; guards = protocol['critical_guards']
    counts = {'final_targets': execution['planned_total_target_calls'], 'final_graders': execution['planned_maximum_grader_calls'],
              'final_evidence': execution['extra_model_stage_calls'], 'pilot_targets': pilot['target_calls'],
              'pilot_graders': pilot['grader_calls_max'], 'pilot_evidence': pilot['evidence_stage_calls_max'],
              'guard_targets': guards['target_calls'], 'guard_graders': guards['grader_calls_max'],
              'guard_evidence': guards['identity_evidence_calls_max']}
    from stability_configuration import answer_validation_enabled
    enabled = answer_validation_enabled(protocol['target']['final_target_profile_flags'])
    validation_cap = valid_cap(protocol['target']['final_target_profile_flags'].get('answer_validation_output_token_limit',8192))
    if enabled:
        for label, section, expected in [('final', execution, counts['final_targets']),('pilot',pilot,counts['pilot_targets']),('guard',guards,counts['guard_targets'])]:
            if section.get('answer_validation_calls_max') != expected:
                raise ValueError('Answer validation call budget must cover every common-arm target.')
            counts[label+'_answer_validation'] = expected
    if 'cohorts' in pilot or 'repetitions' in pilot or 'arms' in pilot:
        from stability_configuration import pilot_call_counts
        actual = pilot_call_counts(protocol)
        if any(pilot.get(key) != value for key, value in actual.items()):
            raise ValueError('Pilot role budget differs from predeclared cohort matrix.')
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise ValueError('Every predeclared role call count must be a nonnegative integer.')
    targets = sum(counts[key] for key in ('final_targets', 'pilot_targets', 'guard_targets')) * target_cap
    graders = sum(counts[key] for key in ('final_graders', 'pilot_graders', 'guard_graders')) * grade_cap
    evidence = sum(counts[key] for key in ('final_evidence', 'pilot_evidence', 'guard_evidence')) * evidence_cap
    result = {'target_output_token_max': counts['final_targets'] * target_cap,
            'grader_output_token_max': counts['final_graders'] * grade_cap,
            'combined_output_token_max': counts['final_targets'] * target_cap + counts['final_graders'] * grade_cap,
            'extra_identity_evidence_output_tokens_max_final': counts['final_evidence'] * evidence_cap,
            'extra_identity_evidence_output_tokens_max_pilot': counts['pilot_evidence'] * evidence_cap,
            'development_pilot_target_and_grade_output_tokens_max': counts['pilot_targets'] * target_cap + counts['pilot_graders'] * grade_cap,
            'all_planned_output_tokens_max_including_evidence_and_pilot':
                counts['final_targets'] * target_cap + counts['final_graders'] * grade_cap + counts['final_evidence'] * evidence_cap
                + counts['pilot_targets'] * target_cap + counts['pilot_graders'] * grade_cap + counts['pilot_evidence'] * evidence_cap,
            'all_roles_call_upper_bound_including_pilot_final_and_guards': sum(counts.values()),
            'all_output_token_upper_bound_including_pilot_final_and_guards': targets + graders + evidence,
            'all_target_output_tokens_max': targets, 'all_grader_output_tokens_max': graders,
            'all_identity_evidence_output_tokens_max': evidence}
    if enabled:
        validation = sum(counts[k] for k in ('final_answer_validation','pilot_answer_validation','guard_answer_validation')) * validation_cap
        result['all_answer_validation_output_tokens_max'] = validation
        result['all_output_token_upper_bound_including_pilot_final_and_guards'] += validation
        result['all_planned_output_tokens_max_including_evidence_and_pilot'] += (counts['final_answer_validation']+counts['pilot_answer_validation'])*validation_cap
    return result


def validate_budget_ledger(protocol):
    derived = output_budget_ledger(protocol)
    mismatches = {key: {'declared': protocol.get('budget', {}).get(key), 'derived': value}
                  for key, value in derived.items() if (key in protocol.get('budget', {}) or key not in {'all_target_output_tokens_max', 'all_grader_output_tokens_max', 'all_identity_evidence_output_tokens_max'}) and protocol.get('budget', {}).get(key) != value}
    if mismatches:
        raise ValueError('Predeclared output budget ledger differs from role counts/caps: ' + repr(mismatches))
    return derived
