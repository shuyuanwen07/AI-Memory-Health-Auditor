"""Study controls cannot silently lose the prospective retention opt-in."""
import copy
from pathlib import Path
import sys

scripts = Path('/scripts') if Path('/scripts/stability_configuration.py').exists() else Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(scripts))
from stability_configuration import study_trial_controls_match, study_trial_memory_controls


def controls():
    profile = {'identity_analysis':'evidence_links','identity_analysis_output_token_limit':8192,
               'identity_analysis_failure_policy':'continue_without_advisory','reasoning_effort':'medium',
               'identity_analysis_reasoning_effort':'low','retention_policy':'source_coverage'}
    study = {'request_contract_required':True,'target':{'final_target_profile_flags':profile,'output_token_limit':8192},
             'grading':{'output_token_limit':4096}}
    trial = {**study_trial_memory_controls(study),'request_contract_required':True,
             'output_token_limit':8192,'grading_output_token_limit':4096}
    return study, trial


def test_coverage_optin_must_match_for_every_trial():
    study, trial = controls()
    assert study_trial_controls_match(study, trial)
    for change in ({}, {'retention_policy':'scope_recency'}):
        changed = copy.deepcopy(trial)
        changed['target_memory_profile'].pop('retention_policy')
        changed['target_memory_profile'].update(change)
        assert not study_trial_controls_match(study, changed)


def test_legacy_absence_equals_original_scope_recency_default():
    study, trial = controls()
    study['target']['final_target_profile_flags'].pop('retention_policy')
    trial['target_memory_profile']['retention_policy'] = 'scope_recency'
    assert study_trial_controls_match(study, trial)
    trial['target_memory_profile'].pop('retention_policy')
    assert study_trial_controls_match(study, trial)


def test_required_ingestion_receipt_cannot_drop_to_legacy_trial():
    study, trial = controls()
    study['memory_preparation_receipt_required'] = True
    assert not study_trial_controls_match(study, trial)
    trial['memory_preparation_receipt_required'] = True
    assert study_trial_controls_match(study, trial)


def test_reproducibility_snapshot_uses_actual_adapter_version_and_saves_coverage():
    from app.api.routes import reproducibility_snapshot
    from app.schemas.target_profile import TargetMemoryProfile
    from app.target_systems.controlled import ControlledTargetSystemAdapter
    snapshot = reproducibility_snapshot(provider='rule_based', model='rules', temperature=0, random_seed=42,
        test_budget=1,prompt_template_version='synthetic',pipeline_provider='rule_based',pipeline_model='rules',
        evaluator_provider='rule_based',evaluator_model='rules',memory_strategy='strong_rule_based',
        memory_maintenance_policy='update_aware_consolidation',target_memory_writer='rule_based',
        target_memory_capacity=500,target_system_adapter='controlled-memory',
        target_memory_profile=TargetMemoryProfile(retention_policy='source_coverage'))
    assert snapshot['target_system_adapter_version'] == ControlledTargetSystemAdapter.version
    assert snapshot['target_memory_profile']['retention_policy'] == 'source_coverage'
