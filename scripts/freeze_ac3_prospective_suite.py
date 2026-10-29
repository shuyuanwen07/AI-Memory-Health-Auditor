"""Freeze a source-bound AC3 suite only after human review and pilot approval.

Offline preparation only: no model calls, database writes, budget mutation or
claim that the app can yet import/execute the suite. Missing prerequisites are
hard failures. The returned bundle is inputs for a future guarded adapter.
"""
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.ac3_evidence_paths import resolve_evidence_path, resolve_frozen_source, pilot_audits_equivalent
PACKET = ROOT / 'output/proposal-delivery/ac3-prospective-inputs-2026-10-28-v3'
PILOT = ROOT / 'output/proposal-delivery/ac3-pilot-threshold-draft-2026-10-28-v2.json'
V7 = ROOT / 'frontend/public/reports/phase4-c-four-strategy-v7.json'
BUDGET_UPDATE = ROOT / 'output/proposal-delivery/ac3-budget-user-update-2026-10-28.json'
CHECK = ROOT / 'scripts/check_ac3_prospective_readiness.py'
REQUIRED_THRESHOLDS = {'failure_detection_recall_min', 'failure_classification_accuracy_min', 'test_validity_min', 'false_positive_rate_max'}
AUDIT_SETUP_FIELDS = {'target_configuration','provider','model','temperature','random_seed','test_budget',
    'prompt_template_version','pipeline_provider','pipeline_model','evaluator_provider','evaluator_model',
    'retrieval_mode','retrieval_provider','retrieval_model','memory_strategy','memory_maintenance_policy',
    'target_memory_capacity','target_memory_writer','target_memory_writer_version','target_system_adapter',
    'target_system_adapter_version','target_memory_profile'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_threshold_selection(cfg, pilot, pilot_sha, approval=None):
    """Bind either the pilot proposal or an explicitly recorded user adjustment.

    A local approval record preserves a user statement; it does not independently
    authenticate the user or prove the provenance of the statement.
    """
    values = cfg.get('thresholds')
    if (not isinstance(values, dict) or set(values) != REQUIRED_THRESHOLDS or
            any(not isinstance(v, (int, float)) or isinstance(v, bool) or
                not math.isfinite(v) or not 0 <= v <= 1 for v in values.values())):
        raise ValueError('All four threshold values must be numeric fractions from 0 to 1.')
    if cfg.get('pilot_draft_sha256') != pilot_sha:
        raise ValueError('The pilot provenance must match the reviewed pilot draft.')
    if approval is None:
        if values != pilot.get('proposed_thresholds'):
            raise ValueError('Changed thresholds require a separately recorded user selection.')
        return 'pilot_proposal'
    if (not isinstance(approval, dict) or approval.get('format') != 'ac3-user-selected-thresholds-v1' or
            approval.get('held_out_results_seen') is not False or
            approval.get('pilot_draft_sha256') != pilot_sha or approval.get('thresholds') != values):
        raise ValueError('User selection must bind the exact pilot and all four configured threshold values.')
    for field in ('user_response', 'selection_basis', 'provenance_limitations', 'recorded_at_utc'):
        if not isinstance(approval.get(field), str) or not approval[field].strip():
            raise ValueError(f'User threshold selection must include {field}.')
    try:
        stamp = datetime.fromisoformat(approval['recorded_at_utc'].replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('User threshold selection timestamp is invalid.') from exc
    if stamp.tzinfo is None:
        raise ValueError('User threshold selection timestamp must include a timezone.')
    return 'user_adjusted'


def validate_expanded_audit_setup(model, suite):
    """Check the explicit configuration that the live runner will revalidate."""
    setup = model.get('audit_setup')
    if not isinstance(setup, dict) or set(setup) != AUDIT_SETUP_FIELDS:
        raise ValueError('Expanded hosted protocol must bind the complete target audit setup.')
    mappings = {'provider':'target_provider','model':'target_model','memory_strategy':'target_strategy',
                'pipeline_provider':'pipeline_provider','pipeline_model':'pipeline_model',
                'evaluator_provider':'evaluator_provider','evaluator_model':'evaluator_model'}
    if any(setup.get(left) != model.get(right) for left,right in mappings.items()):
        raise ValueError('Target audit setup differs from declared provider, model or strategy.')
    lengths = {len(case.get('tests', [])) for case in suite['cases']}
    if len(lengths) != 1 or type(setup.get('test_budget')) is not int or setup['test_budget'] not in lengths:
        raise ValueError('Target audit test budget must match every source history.')
    limit = model.get('target_output_token_limit')
    profile = setup.get('target_memory_profile')
    if type(limit) is not int or limit < 1 or not isinstance(profile, dict) or profile.get('output_token_limit') != limit:
        raise ValueError('Target output limit must be explicit and match the full memory profile.')
    if model.get('synthetic_source_timestamp_utc') != '2000-01-01T00:00:00Z':
        raise ValueError('Synthetic per-history ordering must use the declared artificial baseline.')
    for field in ('runtime_source_sha256','ledger_schema_sha256'):
        if not isinstance(model.get(field), str) or not re.fullmatch(r'[0-9a-f]{64}', model[field]):
            raise ValueError(f'Expanded hosted protocol must bind {field}.')
    digest = sha(json.dumps(setup, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
    expected = model.get('target_settings_sha256')
    if isinstance(expected, dict):
        ids = {case['history_id'] for case in suite['cases']}
        if set(expected) != ids or any(value != digest for value in expected.values()):
            raise ValueError('Per-history target settings hashes do not match the audit setup.')
    elif expected != digest:
        raise ValueError('Target settings hash does not match the complete audit setup.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-1', type=Path, required=True)
    parser.add_argument('--review-2', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True, help='Completed prospective protocol and explicit human attestations.')
    parser.add_argument('--fact-plan', type=Path, help='Reviewed source fact and relationship plan.')
    parser.add_argument('--fact-review-1', type=Path)
    parser.add_argument('--fact-review-2', type=Path)
    parser.add_argument('--source', type=Path, default=PACKET / 'candidate-inputs.json')
    parser.add_argument('--composite-manifest', type=Path)
    parser.add_argument('--expanded-manifest', type=Path, help='Prior eight plus independently reviewed new histories.')
    parser.add_argument('--threshold-approval', type=Path, help='Recorded user selection for thresholds that differ from the pilot proposal.')
    parser.add_argument('--pilot-provenance-audit', type=Path, help='Automated, source-bound pilot audit; does not assert human provenance review.')
    parser.add_argument('--coverage-decision', type=Path)
    parser.add_argument('--expanded-coverage-decision', type=Path)
    parser.add_argument('--local-heldout-observation', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='New file, written exclusively; never overwrites.')
    args = parser.parse_args()
    if args.composite_manifest and args.expanded_manifest:
        raise ValueError('Use one review manifest format, not both.')
    if args.expanded_manifest and not args.threshold_approval:
        raise ValueError('Expanded study must bind the explicit user threshold selection.')
    files = [args.review_1, args.review_2, args.config, PILOT, V7, BUDGET_UPDATE, CHECK, args.source,
             ROOT / 'scripts/ac3_evidence_paths.py']
    evidence_files = [args.coverage_decision, args.expanded_coverage_decision, args.local_heldout_observation]
    if any(evidence_files) and not all(evidence_files):
        raise ValueError('All user decision and local observation evidence files are required together.')
    if all(evidence_files):
        files.extend(evidence_files + [ROOT / 'scripts/ac3_protocol_evidence.py', ROOT / 'scripts/observe_ac3_local_run_status.py'])
    if args.threshold_approval:
        files.append(args.threshold_approval)
    if args.pilot_provenance_audit:
        if args.pilot_provenance_audit.is_symlink() or not args.pilot_provenance_audit.is_file():
            raise ValueError('Pilot provenance audit must be a regular file.')
        if not args.threshold_approval:
            raise ValueError('Automated pilot audit requires the user threshold selection it reviews.')
        audit = json.loads(args.pilot_provenance_audit.read_text())
        source_entries = audit.get('sources')
        if not isinstance(source_entries, dict) or any(not isinstance(v, dict) or not isinstance(v.get('path'), str) for v in source_entries.values()):
            raise ValueError('Pilot audit evidence paths are invalid.')
        files.extend([args.pilot_provenance_audit, ROOT / 'scripts/prepare_ac3_pilot_provenance_audit.py'] +
                     [resolve_frozen_source(v['path'],ROOT) for v in source_entries.values()])
    fact_files = [args.fact_plan, args.fact_review_1, args.fact_review_2]
    if any(fact_files) and not all(fact_files):
        raise ValueError('The fact plan and both independent reviews must be supplied together.')
    if all(fact_files):
        files.extend(fact_files)
    if args.composite_manifest:
        if not all(fact_files):
            raise ValueError('Composite evidence requires the reviewed fact plan and both declarations.')
        if args.composite_manifest.is_symlink() or not args.composite_manifest.is_file():
            raise ValueError('Composite manifest must be a regular file.')
        manifest = json.loads(args.composite_manifest.read_bytes())
        entries = manifest.get('inputs')
        if not isinstance(entries, list) or len(entries) != 14:
            raise ValueError('Invalid composite evidence manifest.')
        files.extend([args.composite_manifest] + [resolve_evidence_path(entry['path']) for entry in entries] +
                     [args.composite_manifest.parent / f'fact-reviewer-{i}.json' for i in (1, 2)] +
                     [ROOT / 'scripts' / name for name in ('import_ac3_conflict_delta_reviews.py',
                      'prepare_ac3_conflict_revision.py', 'prepare_ac3_conflict_revision_explicit.py', 'prepare_ac3_fact_review.py', 'import_ac3_fact_reviews.py',
                      'ac3_reviewed_fact_map.py')])
    if args.expanded_manifest:
        if not all(fact_files) or args.expanded_manifest.is_symlink() or not args.expanded_manifest.is_file():
            raise ValueError('Expanded evidence requires a regular manifest and both reviewed fact declarations.')
        expanded_manifest = json.loads(args.expanded_manifest.read_bytes())
        expanded_entries = expanded_manifest.get('inputs')
        expanded_lengths = {'ac3-expanded-composite-review-v1':11, 'ac3-expanded-revised-composite-review-v1':16,
                            'ac3-expanded-rebased-composite-review-v1':18,
                            'ac3-expanded-user-confirmed-rebased-composite-review-v1':21,
                            'ac3-expanded-both-rounds-confirmed-composite-review-v1':24,
                            'ac3-expanded-restored-composite-review-v1':11,
                            'ac3-expanded-restored-user-confirmed-composite-review-v1':14,
                            'ac3-expanded-h19-unresolved-composite-review-v1':12,
                            'ac3-expanded-h19-unresolved-user-confirmed-composite-review-v1':15}
        if (expanded_manifest.get('format') not in expanded_lengths or not isinstance(expanded_entries, list) or
                len(expanded_entries) != expanded_lengths[expanded_manifest['format']]):
            raise ValueError('Invalid expanded evidence manifest.')
        prior_manifest_path = resolve_evidence_path(expanded_entries[2]['path'])
        if prior_manifest_path.is_symlink() or not prior_manifest_path.is_file():
            raise ValueError('Prior review manifest must be a regular file.')
        restoration_entries=expanded_entries
        if expanded_manifest['format'] in ('ac3-expanded-h19-unresolved-composite-review-v1',
                                            'ac3-expanded-h19-unresolved-user-confirmed-composite-review-v1'):
            v7_entries=json.loads(prior_manifest_path.read_bytes()).get('inputs')
            if not isinstance(v7_entries,list) or len(v7_entries)!=14:
                raise ValueError('V8 requires the user-confirmed v7 composite evidence.')
            v8_draft=json.loads(resolve_evidence_path(expanded_entries[9]['path']).read_bytes())
            v8_evidence=v8_draft.get('evidence')
            if not isinstance(v8_evidence,dict) or any(not isinstance(v,dict) or not isinstance(v.get('path'),str) for v in v8_evidence.values()):
                raise ValueError('V8 unresolved-edge evidence is incomplete.')
            files.extend([resolve_evidence_path(entry['path']) for entry in v7_entries]+
                         [resolve_evidence_path(value['path']) for value in v8_evidence.values()]+
                         [ROOT/'scripts/import_ac3_h19_unresolved_reviews.py',ROOT/'scripts/prepare_ac3_h19_unresolved.py'])
            restoration_entries=v7_entries
            prior_manifest_path=resolve_evidence_path(v7_entries[2]['path'])
        if expanded_manifest['format'] in ('ac3-expanded-restored-composite-review-v1',
                                            'ac3-expanded-restored-user-confirmed-composite-review-v1',
                                            'ac3-expanded-h19-unresolved-composite-review-v1',
                                            'ac3-expanded-h19-unresolved-user-confirmed-composite-review-v1'):
            v6_entries = json.loads(prior_manifest_path.read_bytes()).get('inputs')
            if not isinstance(v6_entries,list) or len(v6_entries)!=24:
                raise ValueError('Restored source requires the full v6 review manifest.')
            restoration_path=resolve_evidence_path(restoration_entries[8]['path'])
            restoration=json.loads(restoration_path.read_bytes())
            evidence=restoration.get('evidence')
            if not isinstance(evidence,dict) or any(not isinstance(v,dict) or not isinstance(v.get('path'),str) for v in evidence.values()):
                raise ValueError('Restoration evidence is incomplete.')
            files.extend([resolve_evidence_path(entry['path']) for entry in v6_entries]+[resolve_evidence_path(value['path']) for value in evidence.values()]+
                         [ROOT/'scripts/import_ac3_h19_restoration_reviews.py',ROOT/'scripts/prepare_ac3_h19_restoration.py'])
            prior_manifest_path=resolve_evidence_path(v6_entries[2]['path'])
            if prior_manifest_path.is_symlink() or not prior_manifest_path.is_file():
                raise ValueError('Original v3 review manifest must be a regular file.')
        prior_entries = json.loads(prior_manifest_path.read_bytes()).get('inputs')
        if not isinstance(prior_entries, list) or len(prior_entries) != 14:
            raise ValueError('Invalid prior composite evidence manifest.')
        files.extend([args.expanded_manifest] + [resolve_evidence_path(entry['path']) for entry in expanded_entries] +
                     [resolve_evidence_path(entry['path']) for entry in prior_entries] +
                     [prior_manifest_path.parent / f'fact-reviewer-{i}.json' for i in (1, 2)] +
                     [ROOT / 'scripts' / name for name in ('import_ac3_expanded_reviews.py', 'ac3_stability.py',
                      'prepare_ac3_stability_child.py', 'ac3_fixed_suite_adapter.py',
                      'import_ac3_conflict_delta_reviews.py', 'prepare_ac3_conflict_revision.py',
                      'prepare_ac3_conflict_revision_explicit.py', 'prepare_ac3_fact_review.py',
                      'import_ac3_fact_reviews.py', 'ac3_reviewed_fact_map.py')])
    if any(not path.is_file() or path.is_symlink() for path in files):
        raise ValueError('Every input must be a regular, non-symlink file.')
    raw = {str(path): path.read_bytes() for path in files}
    cfg = json.loads(raw[str(args.config)])
    pilot, v7 = json.loads(raw[str(PILOT)]), json.loads(raw[str(V7)])
    budget_update = json.loads(raw[str(BUDGET_UPDATE)])
    if budget_update.get('user_statement') != '就用吧 如果这不是实验条件变量有预算要求的话就直接用  没钱了我会续上':
        raise ValueError('The later user budget clarification is missing or changed.')
    check_args = [sys.executable, str(CHECK), '--review-1', str(args.review_1), '--review-2', str(args.review_2), '--source', str(args.source)]
    if args.composite_manifest:
        check_args += ['--composite-manifest', str(args.composite_manifest)]
        sys.path.insert(0, str(ROOT))
        from scripts.import_ac3_conflict_delta_reviews import verify_manifest
        composite = verify_manifest(args.composite_manifest, raw[str(args.source)],
                                    [raw[str(args.review_1)], raw[str(args.review_2)]],
                                    [raw[str(args.fact_review_1)], raw[str(args.fact_review_2)]])
        if composite['fact_plan_sha256'] != sha(json.dumps(json.loads(raw[str(args.fact_plan)]), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()):
            raise ValueError('Composite evidence refers to a different fact plan.')
    if args.expanded_manifest:
        check_args += ['--expanded-manifest', str(args.expanded_manifest)]
        sys.path.insert(0, str(ROOT))
        from scripts.import_ac3_expanded_reviews import verify_expanded_manifest
        expanded = verify_expanded_manifest(args.expanded_manifest, raw[str(args.source)],
                    [raw[str(args.review_1)], raw[str(args.review_2)]],
                    [raw[str(args.fact_review_1)], raw[str(args.fact_review_2)]])
        if expanded['fact_plan_sha256'] != sha(json.dumps(json.loads(raw[str(args.fact_plan)]), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()):
            raise ValueError('Expanded evidence refers to a different fact plan.')
    check = subprocess.run(check_args, check=True, capture_output=True, text=True)
    readiness = json.loads(check.stdout)
    if not readiness['grounding_ready_for_adjudication']:
        raise ValueError('Two complete independent source reviews and resolved uncertainties/disagreements are required.')
    if cfg.get('format') != 'ac3-prospective-freeze-config-v1':
        raise ValueError('Expected a completed ac3-prospective-freeze-config-v1 configuration.')
    threshold_approval = json.loads(raw[str(args.threshold_approval)]) if args.threshold_approval else None
    threshold_selection = validate_threshold_selection(cfg, pilot, sha(raw[str(PILOT)]), threshold_approval)
    if args.pilot_provenance_audit:
        sys.path.insert(0, str(ROOT))
        from scripts.prepare_ac3_pilot_provenance_audit import build_audit
        audit = json.loads(raw[str(args.pilot_provenance_audit)])
        if not pilot_audits_equivalent(audit,build_audit()) or audit.get('user_threshold_selection_sha256') != sha(raw[str(args.threshold_approval)]):
            raise ValueError('Automated pilot source audit or bound user selection does not match current evidence.')
    if readiness['both_valid'] / readiness['questions'] < cfg['thresholds']['test_validity_min']:
        raise ValueError('The source-reviewed candidate questions do not meet the proposed validity threshold.')
    declarations = cfg.get('human_attestations', {})
    # A source-bound automated audit is an explicit alternative to the legacy
    # human provenance attestation, not a statement that a human signed it.
    required_attestations = ['pilot_thresholds_accepted'] if all(evidence_files) else ['pilot_thresholds_accepted', 'held_out_outputs_not_generated_or_inspected', 'exclusions_and_abstention_policy_frozen']
    if not args.pilot_provenance_audit:
        required_attestations.insert(0, 'pilot_provenance_reviewed')
    for name in required_attestations:
        if declarations.get(name) is not True:
            raise ValueError(f'Explicit human attestation required: {name}.')
    if not all(evidence_files) and (not isinstance(declarations.get('responsible_reviewer'), str) or not declarations['responsible_reviewer'].strip()):
        raise ValueError('The responsible reviewer must identify the protocol attestation.')
    if not isinstance(declarations.get('provenance_note'), str) or not declarations['provenance_note'].strip():
        raise ValueError('Document how contradictory pilot provenance was reviewed; retain original statements.')
    local_observation_at_freeze = None
    if all(evidence_files):
        sys.path.insert(0, str(ROOT))
        from scripts.ac3_protocol_evidence import validate_protocol_evidence
        from scripts.observe_ac3_local_run_status import observe
        decisions = [json.loads(raw[str(path)]) for path in evidence_files]
        validate_protocol_evidence(cfg, *decisions, sha(raw[str(args.source)]))
        local_observation_at_freeze = observe(args.source)
        validate_protocol_evidence(cfg, decisions[0], decisions[1], local_observation_at_freeze, sha(raw[str(args.source)]))
    model = cfg.get('model_configuration', {})
    if any(not isinstance(model.get(k), str) or not model[k].strip() for k in ('target_provider', 'target_model', 'evaluator_provider', 'evaluator_model', 'evaluator_implementation_version', 'pipeline_provider', 'pipeline_model', 'pipeline_version', 'pipeline_implementation_version', 'target_strategy')):
        raise ValueError('Target, evaluator and pipeline configuration labels and implementation versions, and strategy must all be explicit.')
    budget = cfg.get('budget', {})
    cap, spent, maximum = budget.get('cumulative_cap_usd'), budget.get('existing_estimated_usd'), budget.get('max_new_estimated_usd')
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in (cap, spent, maximum)) or cap < 0.40 or spent < v7['estimated_cost_usd'] or maximum < 0 or spent + maximum > cap + 1e-9:
        raise ValueError('Declare a finite prospective budget and account for prior v7 usage; the old v7 cap remains preserved.')
    providers = [model[f'{role}_provider'] for role in ('target', 'evaluator', 'pipeline')]
    if any(p not in {'ollama', 'rule_based', 'openrouter'} for p in providers):
        raise ValueError('Only explicitly named local, rule-based, or OpenRouter providers are supported by this planning format.')
    if 'openrouter' not in providers and maximum != 0:
        raise ValueError('Local-only configuration must have zero hosted API budget; do not relabel local results as hosted.')
    if 'openrouter' in providers and maximum <= 0:
        raise ValueError('Hosted configuration requires a positive budget within the cumulative ceiling.')
    if args.expanded_manifest and 'openrouter' in providers:
        reservation = budget.get('per_request_reservation_usd')
        if (not isinstance(reservation, (int, float)) or isinstance(reservation, bool) or
                not math.isfinite(reservation) or reservation <= 0):
            raise ValueError('Expanded hosted study requires a positive per-request estimated reservation.')
        per_test_remote = sum(model[f'{role}_provider'] == 'openrouter' for role in ('target', 'evaluator'))
        # A hosted setup-only pipeline has no fixed per-test calls in this suite.
        if per_test_remote and reservation * readiness['questions'] * per_test_remote > maximum + 1e-9:
            raise ValueError('Per-request planning reservations exceed the new-spend estimate.')
    coverage = cfg.get('minimum_decided_coverage')
    if not isinstance(coverage, (int, float)) or isinstance(coverage, bool) or not 0 < coverage <= 1:
        raise ValueError('Declare the minimum decided coverage before collecting outcomes.')
    for field in ('abstention_policy', 'exclusion_policy', 'budget_enforcement_plan', 'reference_blinding_plan'):
        if not isinstance(cfg.get(field), str) or not cfg[field].strip():
            raise ValueError(f'The full pre-outcome protocol must document {field}.')
    for field in ('minimum_human_failure_count', 'minimum_human_pass_count', 'minimum_independent_histories'):
        if not isinstance(cfg.get(field), int) or isinstance(cfg[field], bool) or cfg[field] < 1:
            raise ValueError(f'The full pre-outcome protocol must declare {field}.')
    if cfg['minimum_independent_histories'] > readiness['histories'] or cfg['minimum_human_failure_count'] + cfg['minimum_human_pass_count'] > readiness['questions']:
        raise ValueError('Minimum case counts cannot exceed the candidate suite size.')
    candidate_bytes = raw[str(args.source)]
    suite = json.loads(candidate_bytes)
    if sha(candidate_bytes) != readiness['input_sha256'] or len(suite['cases']) != readiness['histories']:
        raise ValueError('Source is not the exact reviewed suite.')
    if args.expanded_manifest and model['target_provider'] == 'openrouter':
        validate_expanded_audit_setup(model, suite)
        sys.path.insert(0, str(ROOT))
        from scripts.ac3_stability import validate_plan
        repeat_plan = cfg.get('stability_plan')
        validate_plan(repeat_plan, suite)
        repeat_budget = repeat_plan.get('budget', {})
        repeat_max, repeat_reserve = repeat_budget.get('max_new_estimated_usd'), repeat_budget.get('per_request_reservation_usd')
        if (any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0
                for value in (repeat_max, repeat_reserve)) or
                repeat_reserve * 40 > repeat_max + 1e-9 or spent + maximum + repeat_max > cap + 1e-9):
            raise ValueError('Primary and repeat estimated reservations must fit their separately allocated planning budgets.')
    suite_bytes = json.dumps(suite, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    fact_plan = None
    if all(fact_files):
        from ac3_reviewed_fact_map import validate_fact_plan
        fact_plan = json.loads(raw[str(args.fact_plan)])
        fact_reviews = [json.loads(raw[str(path)]) for path in fact_files[1:]]
        validate_fact_plan(suite, fact_plan, fact_reviews)
    output = {
        'format': 'ac3-prospective-frozen-suite-v1', 'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'FROZEN INPUTS ONLY; execution adapter and budget enforcement not verified',
        'input_sha256': readiness['input_sha256'], 'canonical_suite_sha256': sha(suite_bytes),
        'source_hashes': {str(path): sha(data) for path, data in raw.items()},
        'review_sources': [str(args.review_1), str(args.review_2)],
        'config_source': str(args.config), 'candidate_source': str(args.source),
        'grounding': readiness, 'protocol': cfg, 'suite': suite,
        'execution_supported': False, 'model_called': False, 'results_observed': False,
        'warning': 'This file alone does not grant paid calls or establish AC3. Human attestations are not identity-authenticated. Implement and validate an app adapter, external budget guard, answer blinding, and result recording before execution.',
    }
    if local_observation_at_freeze is not None:
        output['protocol_evidence_method'] = 'recorded_user_decisions_and_local_observation_not_human_attestation'
        output['protocol_evidence_sources'] = [str(path) for path in evidence_files]
        output['local_observation_at_freeze'] = local_observation_at_freeze
    output['threshold_selection'] = threshold_selection
    if args.threshold_approval:
        output['threshold_approval_source'] = str(args.threshold_approval)
    if args.pilot_provenance_audit:
        output['pilot_provenance_audit_source'] = str(args.pilot_provenance_audit)
        output['pilot_provenance_review_method'] = 'automated_source_check_not_human_attestation'
    if fact_plan is not None:
        output.update({'fact_plan_source': str(args.fact_plan),
                       'fact_review_sources': [str(args.fact_review_1), str(args.fact_review_2)],
                       'reviewed_fact_plan': fact_plan})
    if args.composite_manifest:
        output['composite_manifest_source'] = str(args.composite_manifest)
    if args.expanded_manifest:
        output['expanded_manifest_source'] = str(args.expanded_manifest)
        output['study_role'] = 'primary_validation'
        if cfg.get('stability_plan') is not None:
            output['stability_plan_sha256'] = sha(json.dumps(cfg['stability_plan'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
    if any(sha(path.read_bytes()) != sha(raw[str(path)]) for path in files):
        raise ValueError('Inputs changed during preparation; nothing was frozen.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(args.output, flags, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'sha256': sha(args.output.read_bytes()), 'status': output['status'], 'execution_supported': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
