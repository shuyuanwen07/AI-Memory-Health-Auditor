"""Freeze the user-authorized AC3 retest without invoking a model.

Run in the project backend environment. Output is a new private research
directory; original studies and human review documents are never modified.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import AuditRun
from app.services.ac3_controlled_runner import _SETTINGS_FIELDS
from scripts.ac3_retest_paired_freeze import COMPONENTS, THRESHOLDS, canonical, prepare
from scripts.ac3_retest_snapshot_verify import formal_signature


def main():
    base = Path('/output/proposal-delivery')
    candidate = base/'ac3-retest-diverse-candidate-2026-10-28-v6'
    returned = base/'human-return-2026-10-29-ff607492'
    out = Path('/ac3-results/paired-authorized-retest-20261029-v1')
    out.mkdir(mode=0o700, parents=False, exist_ok=False)
    source = (candidate/'candidate-inputs.json').read_bytes()
    plan = (candidate/'proposed-fact-plan.json').read_bytes()
    reviews = [(returned/f'ac3-reviewer-{i}.json').read_bytes() for i in (1, 2)]
    paths = {'target_runtime': returned/'ac3-current-candidate-v4.zip',
             'old_evaluator': candidate/'paired-baseline-shared-environment-candidate.zip',
             'new_evaluator': returned/'ac3-current-candidate-v4.zip'}
    components = {name: paths[name].read_bytes() for name in COMPONENTS}
    old = json.loads((base/'ac3-expanded-primary-frozen-2026-10-28.json').read_text())
    previous_setup = old['protocol']['model_configuration']['audit_setup']
    audit = AuditRun(run_id='pre-registration', conversation_id='pre-registration', status='CREATED',
                     created_at=datetime.now(timezone.utc), **previous_setup)
    setup = audit.model_dump(mode='json', include=_SETTINGS_FIELDS)
    signatures = {name: formal_signature(components[name]) for name in ('old_evaluator', 'new_evaluator')}
    cfg = {'format':'ac3-retest-paired-protocol-v1', 'thresholds':THRESHOLDS.copy(),
        'minimum_consensus_pass':30, 'minimum_consensus_fail':30, 'minimum_auto_coverage':.8,
        'policy': {'single_target_answer_per_item':True, 'both_graders_use_identical_answer':True,
            'retain_target_errors':True, 'retain_scoring_errors':True,
            'retain_uncertain_and_unclassified':True, 'exclude_after_outcome_inspection':False,
            'uncertainty_unit':'history'},
        'target': {'provider':'openrouter', 'model':'openai/gpt-6-luna',
            'strategy':setup['memory_strategy'], 'prompt_template_version':setup['prompt_template_version'],
            'memory_configuration_sha256':hashlib.sha256(canonical(setup)).hexdigest(),
            'temperature':None, 'random_seed':None,
            'output_token_limit':setup['target_memory_profile']['output_token_limit'], 'retry_limit':0},
        'budget_mode':'tracking_only',
        # This number is a required legacy schema field, not a spending cap in tracking-only mode.
        'budget':{'max_usd':1, 'per_request_reservation_usd':.001},
        'scorer':{'provider':'openrouter', 'model':'openai/gpt-6-luna', 'output_token_limit':2048,
            'prompt_version':'isolated-taxonomy-candidate-structured-v2', 'retry_limit':0,
            'variant':'provider_only'},
        'component_sha256': {name:hashlib.sha256(components[name]).hexdigest() for name in COMPONENTS},
        'evaluator_snapshots':{name:{'app_source_sha256':info['app_source_sha256'],
              'dependencies_lock_sha256':info['dependencies_lock_sha256']} for name, info in signatures.items()},
        'operator_declaration': {'new_target_results_observed':False, 'fixed_before_target_generation':True,
              'operator_label':'Codex study preparation; user authorized the study'},
        'selection_note':'Provider-only candidate selected before new answers: development recall 82.5%, classification 75.8%; independent performance unknown.',
        'budget_note':'User explicitly removed the prior $0.40 limit; track new charges, preserve unreconciled historical costs, and do not assume prior cost was zero.'}
    frozen = prepare(source, plan, reviews, cfg, components)
    def write(name, data):
        with (out/name).open('x', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2); f.write('\n')
    write('audit-setup.json', setup)
    write('protocol.json', cfg)
    # Runtime ledger and source bindings use the same canonical bytes.
    with (out/'frozen.json').open('xb') as f:
        f.write(canonical(frozen))
    write('sources.json', {'source':str(candidate/'candidate-inputs.json'), 'plan':str(candidate/'proposed-fact-plan.json'),
        'reviews':[str(returned/f'ac3-reviewer-{i}.json') for i in (1,2)],
        'components':{k:str(v) for k,v in paths.items()}, 'model_called':False})
    print(json.dumps({'output':str(out), 'question_count':120, 'model_called':False}))


if __name__=='__main__':
    main()
