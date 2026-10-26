"""Materialize frozen synthetic controls; private criteria never enter target payload."""
from stability_grading_budget import study_grader_cap
from stability_configuration import role_settings, study_trial_memory_controls

import json
import os
from pathlib import Path
from run_stability_study import dump,read,sha


def materialize(root,stage,protocol):
    memory_controls=study_trial_memory_controls(protocol)
    source=root/'guards/conversation-cases.json';criteriafile=root/'guards/evaluator-private-criteria.json';cases=read(source)['cases'];criteria={c['case_id']:c for c in read(criteriafile)['cases']};assert len(cases)==12
    target_cap=role_settings(protocol,'target_answer',study=True)['output_token_limit']
    profile=protocol['target']['final_target_profile_flags'];assert profile['identity_analysis']=='evidence_links';trials=[]
    evaluator=(root.parent/'longmemeval-expanded-20261019/upstream-evaluator').resolve()
    for repetition in [1,2,3]:
        for case in cases:
            mapped=[{'original_source_id':m['message_id'],'runtime_source_id':f'MSG-{i:03}'} for i,m in enumerate(case['conversation']['messages'],1)];case={**case,'runtime_source_id_map':mapped}
            payload=[{'question_id':case['case_id'],'question_type':'synthetic-safety-control','question':case['question'],'question_date':case['question_date'],'answer':'Synthetic private evaluator placeholder; no official reference score.','haystack_sessions':[[{'role':m['role'],'content':m['content']}] for m in case['conversation']['messages']],'haystack_dates':[m['timestamp'] for m in case['conversation']['messages']],'haystack_session_ids':[m['message_id'] for m in case['conversation']['messages']]}]
            directory=stage/'trials/safety_guards'/('round-'+str(repetition))/case['case_id']/'strong_rule_based';directory.mkdir(parents=True,exist_ok=False);dump(directory/'pilot-subset.json',payload);dump(directory/'guard-case.json',case);dump(directory/'guard-private-criteria.json',criteria[case['case_id']]);sourcehash=sha(directory/'pilot-subset.json')
            memory=dict(memory_controls['target_memory_profile'])
            item={'scope':'synthetic_full_controlled_pipeline_safety_not_official_LongMemEval','assessment_kind':'synthetic_source_safety','assessment_role':'stability_guard_assessment','source_authorised':True,'selected_ids':[case['case_id']],'subset_sha256':sourcehash,'source_provenance':{'revision':'self-authored-synthetic-20261021-v1','license':'team_authored_synthetic_engineering_control','citation':'Self-authored synthetic engineering controls; not human gold or LongMemEval benchmark scores.'},'provider':'openrouter','model':'openai/gpt-6-luna','strategies':['strong_rule_based'],'target_memory_capacity':memory_controls['target_memory_capacity'],'target_memory_profile':memory,'context_character_budget':memory_controls['context_character_budget'],'output_token_limit':target_cap,'grading_output_token_limit':study_grader_cap(protocol),'request_contract_required':protocol.get('request_contract_required',False),'memory_preparation_receipt_required':protocol.get('memory_preparation_receipt_required',False),'grading_reasoning_effort':protocol.get('grading',{}).get('reasoning_effort'),'upstream_evaluator_directory':os.path.relpath(evaluator,directory),'maximum_extra_answer_validation_calls':int(memory.get('answer_validation','off')=='source_grounding'),'maximum_extra_identity_evidence_calls':1,'no_quality_retries':True,'guard_source_sha256':sha(source),'guard_private_criteria_sha256':sha(criteriafile)};dump(directory/'pilot-protocol.json',item)
            trials.append({'split':'safety_guards','case_id':case['case_id'],'type':'synthetic-safety-control','round':repetition,'arm':'strong_rule_based','directory':str(directory.relative_to(stage)),'source_sha256':sourcehash,'protocol_sha256':sha(directory/'pilot-protocol.json'),'private_criteria_sha256':sha(directory/'guard-private-criteria.json'),'guard_case_sha256':sha(directory/'guard-case.json')})
            public=stage/'inputs/safety_guards'/(case['case_id']+'.json')
            if not public.exists():dump(public,payload)
    assert len(trials)==36;dump(stage/'trial-matrix.json',{'stage':'safety-guards','scope':'controlled_pipeline_synthetic_not_official_benchmark','planned_trials':36,'trials':trials})
