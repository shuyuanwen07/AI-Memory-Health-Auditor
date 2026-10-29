"""Validate user decisions and a local observation without asserting human signatures."""

def validate_protocol_evidence(cfg, coverage, expanded, observation, source_sha):
    if coverage.get('format') != 'ac3-coverage-user-decision-v1' or coverage.get('user_response') != '接受，按此固定':
        raise ValueError('Original coverage decision is missing or changed.')
    if expanded.get('format') != 'ac3-expanded-coverage-user-decision-v1' or expanded.get('user_response') != '各至少 30 条（推荐）':
        raise ValueError('Expanded coverage decision is missing or changed.')
    if (cfg.get('minimum_decided_coverage') != 0.8 or cfg.get('minimum_human_failure_count') != 30 or
            cfg.get('minimum_human_pass_count') != 30 or cfg.get('minimum_independent_histories') != 30):
        raise ValueError('Configuration differs from recorded coverage decisions.')
    if any(not isinstance(cfg.get(k), str) or not cfg[k].strip() for k in ('abstention_policy','exclusion_policy','reference_blinding_plan')):
        raise ValueError('Protocol must state abstention, exclusion and blinding policies.')
    if (observation.get('format') != 'ac3-local-heldout-observation-v1' or observation.get('source_sha256') != source_sha or
            observation.get('question_count') != 120 or observation.get('human_attestation_created') is not False or
            observation.get('local_matching_responses_found') is not False or
            not observation.get('scope_limitations')):
        raise ValueError('The local observation does not cover the exact source or is not clear.')
    counts = observation.get('database_counts', {})
    if counts.get('matching_prompt_responses') != 0 or counts.get('ac3_generated_responses') != 0:
        raise ValueError('Local AC3 answer records already exist.')
