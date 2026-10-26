"""Versioned study controls; absent historical fields keep their original meaning."""
from stability_grading_budget import valid_cap, study_grader_cap, trial_grader_cap, preflight_grader_budget

ARMS = ('weak_first_hit', 'strong_rule_based')


def answer_validation_enabled(profile):
    mode = profile.get('answer_validation', 'off')
    if mode not in {'off', 'source_grounding'}:
        raise ValueError('Unknown answer validation mode.')
    return mode == 'source_grounding'


def study_memory_limits(protocol):
    """Resolve declared limits once; historical omission retains old bounds."""
    target = protocol.get('target', {})
    if not isinstance(target, dict):
        raise ValueError('Study target memory controls must be an object.')
    limits = {}
    for key, default, minimum, maximum in (
            ('memory_capacity', 500, 1, 500),
            ('max_retrieved_records', 50, 1, 500),
            ('context_character_budget', 16000, 100, 100000)):
        value = target.get(key, default)
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError('Invalid declared study memory limit: ' + key)
        limits[key] = value
    profile = target.get('final_target_profile_flags', {})
    if not isinstance(profile, dict):
        raise ValueError('Study target memory profile must be an object.')
    for key in ('max_retrieved_records', 'context_character_budget'):
        if key in profile and (type(profile[key]) is not int or profile[key] != limits[key]):
            raise ValueError('Nested profile contradicts study memory limit: ' + key)
    return limits


def study_trial_memory_controls(protocol):
    """Common materialization for benchmark arms and synthetic guard trials."""
    limits = study_memory_limits(protocol)
    profile = protocol.get('target', {}).get('final_target_profile_flags', {})
    cap = role_settings(protocol, 'target_answer', study=True)['output_token_limit']
    if 'output_token_limit' in profile and (type(profile['output_token_limit']) is not int
                                           or profile['output_token_limit'] != cap):
        raise ValueError('Nested profile contradicts study target output limit.')
    memory = {'retain_assistant_history': True, 'retrieve_message_context': True,
              'max_retrieved_records': limits['max_retrieved_records'],
              'context_character_budget': limits['context_character_budget'],
              'output_token_limit': cap, **profile}
    return {'target_memory_capacity': limits['memory_capacity'],
            'target_memory_profile': memory,
            'context_character_budget': limits['context_character_budget']}


def pilot_cohorts(protocol):
    pilot = protocol.get('development_pilot', {})
    cohorts = pilot.get('cohorts')
    if cohorts is None:
        cohorts = [{'name': 'known-development', 'selected_ids': pilot.get('selected_ids', []),
                    'arms': pilot.get('arms', list(ARMS)), 'repetitions': pilot.get('repetitions', 1)}]
    if not isinstance(cohorts, list) or not cohorts:
        raise ValueError('Predeclare nonempty pilot cohorts.')
    result = []
    keys = set()
    for index, cohort in enumerate(cohorts):
        if not isinstance(cohort, dict): raise ValueError('Invalid pilot cohort.')
        ids = cohort.get('selected_ids'); arms = cohort.get('arms', list(ARMS)); repetitions = cohort.get('repetitions', 1)
        if (not isinstance(ids, list) or not ids or any(not isinstance(q, str) or not q for q in ids)
                or len(ids) != len(set(ids)) or not isinstance(arms, list) or not arms
                or len(arms) != len(set(arms)) or any(arm not in ARMS for arm in arms)
                or type(repetitions) is not int or not 1 <= repetitions <= 10):
            raise ValueError('Invalid pilot IDs/arms/repetitions.')
        for qid in ids:
            for rep in range(1, repetitions + 1):
                for arm in arms:
                    key=(qid,rep,arm)
                    if key in keys: raise ValueError('Pilot cohorts have duplicate trial cells.')
                    keys.add(key)
        split=cohort.get('split','development' if index==0 else 'development_regression')
        if split not in {'development','development_regression','development_repair'}:raise ValueError('Invalid development cohort split.')
        result.append({**cohort, 'selected_ids': ids, 'arms': arms, 'repetitions': repetitions, 'split':split})
    return result


def pilot_cells(protocol):
    return [{'case_id': qid, 'round': rep, 'arm': arm, 'cohort': cohort.get('name', 'known-development'),'split':cohort['split']}
            for cohort in pilot_cohorts(protocol) for qid in cohort['selected_ids']
            for rep in range(1,cohort['repetitions']+1) for arm in cohort['arms']]


def pilot_call_counts(protocol):
    cells=pilot_cells(protocol)
    result = {'target_calls':len(cells), 'grader_calls_max':len(cells),
            'evidence_stage_calls_max':sum(cell['arm']=='strong_rule_based' for cell in cells)
                if protocol['target']['final_target_profile_flags'].get('identity_analysis')=='evidence_links' else 0}
    if answer_validation_enabled(protocol['target']['final_target_profile_flags']):
        result['answer_validation_calls_max'] = len(cells)
    return result


def role_settings(protocol, role, *, study=False):
    profile = (protocol.get('target', {}).get('final_target_profile_flags', {}) if study
               else protocol.get('target_memory_profile', {}))
    if role == 'target_answer':
        cap = protocol['target'].get('output_token_limit',4096) if study else protocol['output_token_limit']
        effort = profile.get('reasoning_effort')
    elif role == 'target_answer_validation':
        cap = profile.get('answer_validation_output_token_limit', 8192)
        effort = profile.get('answer_validation_reasoning_effort')
        if type(cap) is not int or not 512 <= cap <= 8192:
            raise ValueError('Invalid answer validation output cap.')
    elif role == 'target_identity_evidence':
        cap = profile.get('identity_analysis_output_token_limit', 4096)
        effort = profile.get('identity_analysis_reasoning_effort')
    elif role in {'benchmark_pilot_assessment','stability_guard_assessment'}:
        cap = study_grader_cap(protocol) if study else trial_grader_cap(protocol)
        effort = protocol.get('grading', {}).get('reasoning_effort') if study else protocol.get('grading_reasoning_effort')
    else: raise ValueError('Unbudgeted request role.')
    valid_cap(cap)
    if effort not in ({None,'low','medium'} if role in {'target_answer','target_answer_validation'} else {None,'low'}):
        raise ValueError('Unsupported reasoning effort; never drop unknown settings.')
    return {'output_token_limit':cap,'reasoning_effort':effort}


def preflight_all_roles(protocol, *, study=False, environ=None):
    roles={}
    profile=protocol.get('target',{}).get('final_target_profile_flags',{}) if study else protocol.get('target_memory_profile',{})
    role_names = ['target_answer','target_identity_evidence','benchmark_pilot_assessment','stability_guard_assessment']
    if answer_validation_enabled(profile):role_names.append('target_answer_validation')
    for role in role_names:
        settings=role_settings(protocol,role,study=study)
        if role=='target_answer': effective=settings['output_token_limit'];configured=None
        else:
            budget=preflight_grader_budget(settings['output_token_limit'],environ)
            effective=budget['expected_effective_grader_output_token_limit'];configured=budget['configured_pipeline_output_token_cap']
        active=role!='target_identity_evidence' or profile.get('identity_analysis','off')=='evidence_links'
        roles[role]={**settings,'active':active,'effective_output_token_limit':effective,'configured_pipeline_output_token_cap':configured,
                     'passed':not active or effective==settings['output_token_limit']}
    return {'roles':roles,'passed':all(row['passed'] for row in roles.values()),
            'scope':'Configuration resolution only; not proof of provider/route support.'}


def source_reuse_scope(selected):
    if selected.get('version')=='catalog09b-evidence-disjoint-metadata-v1':
        return {'policy_id':'question-and-answer-evidence-disjoint-mutual-filler-reuse-v1',
                'question_disjoint':True,'answer_evidence_disjoint':True,
                'public_distractor_conversations_may_repeat':True,'full_source_disjoint':False,
                'metadata_checks_status':'passed','scope_disclosure':selected['scope_disclosure']}
    return {'policy_id':'legacy-full-source-disjoint','full_source_disjoint':True,
            'public_distractor_conversations_may_repeat':False,'metadata_checks_status':'legacy_declared'}


def pilot_quality_gates(protocol, rows):
    """Extra prospective development checks; never replace final acceptance."""
    gates={}
    for index,rule in enumerate(protocol.get('development_pilot',{}).get('quality_requirements',[]),1):
        split=rule['split'];arm=rule['arm'];minimum=rule['minimum_correct']
        if split not in {'development','development_regression','development_repair'} or arm not in ARMS or type(minimum) is not int or minimum<0:
            raise ValueError('Invalid prospective pilot quality rule.')
        selected=[row for row in rows if row.get('split')==split and row.get('arm')==arm]
        valid=sum(isinstance(row.get('semantic_grade'),dict) and row['semantic_grade'].get('status')=='completed'
                  and type(row['semantic_grade'].get('correct')) is bool for row in selected)
        correct=sum(row.get('semantic_grade',{}).get('correct') is True for row in selected if isinstance(row.get('semantic_grade'),dict))
        gates[f'development_quality_{index}']={'status':'pass' if selected and valid==len(selected) and correct>=minimum else 'fail',
            'observed':{'split':split,'arm':arm,'planned':len(selected),'graded':valid,'correct':correct},'threshold':minimum}
    return gates


def study_trial_controls_match(study,trial):
    """A required study cannot silently enter a legacy trial configuration."""
    try:
        limits = study_memory_limits(study)
        legacy = study_memory_limits({})
        actual = trial.get('target_memory_profile', {})
        if not isinstance(actual, dict):return False
        if study.get('request_contract_required') is True or study.get('memory_preparation_receipt_required') is True:
            if (any(key not in trial for key in ('target_memory_capacity', 'context_character_budget', 'output_token_limit'))
                    or any(key not in actual for key in ('max_retrieved_records', 'context_character_budget'))):
                return False
        for value, expected in (
                (trial.get('target_memory_capacity', legacy['memory_capacity']), limits['memory_capacity']),
                (actual.get('max_retrieved_records', legacy['max_retrieved_records']), limits['max_retrieved_records']),
                (actual.get('context_character_budget', legacy['context_character_budget']), limits['context_character_budget']),
                (trial.get('context_character_budget', legacy['context_character_budget']), limits['context_character_budget'])):
            if type(value) is not int or value != expected:return False
    except (ValueError, TypeError):
        return False
    expected_profile = study.get('target', {}).get('final_target_profile_flags', {})
    if answer_validation_enabled(expected_profile) != answer_validation_enabled(actual):return False
    if answer_validation_enabled(expected_profile):
        if role_settings(study,'target_answer_validation',study=True) != role_settings(trial,'target_answer_validation'):return False
        if trial.get('maximum_extra_answer_validation_calls') != 1:return False
    if study.get('memory_preparation_receipt_required') is True and trial.get('memory_preparation_receipt_required') is not True:
        return False
    if study.get('request_contract_required') is True:
        if trial.get('request_contract_required') is not True:return False
        for role in ('target_answer','target_identity_evidence','benchmark_pilot_assessment','stability_guard_assessment'):
            if role_settings(study,role,study=True)!=role_settings(trial,role):return False
        profile=study['target']['final_target_profile_flags'];actual=trial.get('target_memory_profile',{})
        for key,default in [('identity_analysis','off'),('identity_analysis_failure_policy','fail_closed'),
                            ('retention_policy','scope_recency')]:
            if profile.get(key,default)!=actual.get(key,default):return False
        if actual.get('output_token_limit',trial.get('output_token_limit'))!=study['target']['output_token_limit']:return False
    return True


def selection_binding(protocol,selected,root,workspace):
    """Bind the actual metadata selector and its unchanged catalog fixtures."""
    import hashlib
    import json
    from pathlib import Path
    root=Path(root).resolve();workspace=Path(workspace)
    config=protocol.get('selection')
    required=selected.get('version')=='catalog09b-evidence-disjoint-metadata-v1'
    if not required and (not isinstance(config,dict) or not any(key in config for key in ('helper_path','helper_sha256','fixture_manifest'))):
        path=workspace/'scripts/prepare_stability_study.py'
        return {'helper_path':'scripts/prepare_stability_study.py','helper_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'fixture_manifest':{}}
    if not isinstance(config,dict):raise ValueError('New selection requires its actual helper and fixture provenance.')
    name=config.get('helper_path');digest=config.get('helper_sha256');fixtures=config.get('fixture_manifest')
    if not isinstance(name,str) or Path(name).is_absolute() or not isinstance(fixtures,dict) or not fixtures:raise ValueError('Incomplete selection binding.')
    helper=(root/name).resolve()
    if not helper.is_relative_to(root) or not helper.is_file():raise ValueError('Selector must be an existing root-relative file.')
    if hashlib.sha256(helper.read_bytes()).hexdigest()!=digest or fixtures.get(name)!=digest:raise ValueError('Actual selector helper hash differs.')
    for relative,expected in fixtures.items():
        file=(root/relative).resolve()
        if Path(relative).is_absolute() or not file.is_relative_to(root) or not file.is_file():raise ValueError('Invalid selection fixture path.')
        if hashlib.sha256(file.read_bytes()).hexdigest()!=expected:raise ValueError('Selection fixture changed.')
    actual={str(path.relative_to(root)) for path in helper.parent.rglob('*') if path.is_file() and '__pycache__' not in path.parts}
    if actual!=set(fixtures):raise ValueError('Selection fixture membership changed.')
    if required:
        required_names={'select_metadata09b.py','prospective-rule-authorization.json','selected-metadata.json',
                        'provenance-proof.json','postselection-invariants.json','exclusion-audit.json','shared-filler-ledger.json'}
        if not required_names<={Path(key).name for key in fixtures}:raise ValueError('Catalog09b selection fixtures incomplete.')
        catalog=helper.parent/'selected-metadata.json'
        if catalog.read_bytes()!=(root/'selected-metadata.json').read_bytes():raise ValueError('Root metadata differs from original catalog bytes.')
    return {'helper_path':name,'helper_sha256':digest,'fixture_manifest':dict(fixtures)}
