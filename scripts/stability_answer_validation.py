"""Independent answer-review provenance; never pooled with identity analysis."""
import hashlib
import json
import math
from pathlib import Path
from stability_configuration import answer_validation_enabled, role_settings
from stability_auxiliary import agent_identity_matches

ROLE = 'target_answer_validation'
OBSERVATIONS = 'answer-validation-observation-receipts.json'
DRAFT = 'primary-draft-response.json'


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',', ':')).encode()).hexdigest()


def text_digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def read_observation(directory):
    path=Path(directory)/OBSERVATIONS
    if not path.exists():return None
    receipt=json.loads(path.read_text())
    if (receipt.get('version')!='private-answer-validation-observation-receipts-v1'
            or receipt.get('provenance')!='actual_runtime_observation' or receipt.get('reconstructed') is not False
            or not isinstance(receipt.get('observations'),list) or len(receipt['observations'])!=1):
        raise ValueError('Invalid actual answer validation observation receipt.')
    row=receipt['observations'][0]
    if not isinstance(row,dict) or not isinstance(row.get('last_observation'),dict):raise ValueError('Missing actual validator observation.')
    return row['last_observation']


def validate_binding(protocol, *, observation, draft, final, events):
    """Local exact bindings only, not semantic correctness of a model review."""
    profile=protocol.get('target_memory_profile',{})
    enabled=answer_validation_enabled(profile)
    calls=[row for row in events if row.get('agent_role')==ROLE]
    metadata=(final.get('execution_metadata') or {}).get('answer_validation')
    if not enabled:
        if calls or observation is not None or metadata is not None:raise ValueError('Unexpected disabled answer validation.')
        return {'enabled':False,'status':'not_enabled','attempted_calls':0}
    if not isinstance(draft,dict) or not isinstance(final,dict) or not isinstance(observation,dict):
        raise ValueError('Missing draft/final/validation observation.')
    if len(calls)!=1 or observation.get('status')!='completed':raise ValueError('Missing or failed answer validation.')
    execution=observation.get('execution');settings=role_settings(protocol,ROLE)
    if (not agent_identity_matches(execution,protocol['model'],ROLE,settings['output_token_limit'])
            or execution!=calls[0].get('execution')
            or execution.get('requested_reasoning_effort')!=settings['reasoning_effort']):
        raise ValueError('Answer validation execution differs from declared controls.')
    if not all(isinstance(response.get('response_text'),str) and response['response_text'].strip() for response in (draft,final)):
        raise ValueError('Missing actual primary or final text.')
    raw=observation.get('raw_input_payload');result=observation.get('output_data')
    if not isinstance(raw,dict) or not isinstance(result,dict) or not isinstance(metadata,dict):raise ValueError('Missing bound answer review.')
    if (not isinstance(raw.get('question'),str) or not isinstance(raw.get('selected_context'),list)
            or not all(isinstance(value,str) for value in raw['selected_context'])
            or not isinstance(raw.get('source_roles'),list) or len(raw['source_roles'])!=len(raw['selected_context'])
            or any(role not in {'user','assistant','unknown'} for role in raw['source_roles'])):
        raise ValueError('Invalid actual review source input.')
    primary=(draft.get('execution_metadata') or {}).get('memory_input') or {}
    if (primary.get('context_sha256')!=digest(raw.get('selected_context'))
            or primary.get('prompt_sha256')!=text_digest(raw.get('question',''))):
        raise ValueError('Validator context/question differs from actual primary input.')
    from app.target_systems.controlled import ControlledTargetSystemAdapter
    if metadata.get('execution')!=ControlledTargetSystemAdapter._answer_validation_meter(execution):raise ValueError('Final validation meter differs from actual observation.')
    if (not all(isinstance(metadata.get(k),str) and metadata[k] for k in ('draft_execution_id','execution_id'))
            or metadata['draft_execution_id']==metadata['execution_id']):raise ValueError('Missing distinct draft/review stage references.')
    expected={'question_sha256':text_digest(raw['question']),
              'source_context_sha256':digest(raw.get('selected_context')),
              'source_roles_sha256':digest(raw.get('source_roles')),
              'draft_answer_sha256':text_digest(draft['response_text']),
              'final_answer_sha256':text_digest(final['response_text'])}
    if raw.get('draft_answer')!=draft['response_text']:raise ValueError('Review did not use the actual primary draft.')
    if any(result.get(k)!=v or metadata.get(k)!=v for k,v in expected.items()):raise ValueError('Answer review source/draft/final hash mismatch.')
    for key in ('version','decision','validation_scope'):
        if metadata.get(key)!=result.get(key):raise ValueError('Answer review public metadata mismatch.')
    decision=result.get('decision')
    if decision not in {'supported','corrected','uncertain'}:raise ValueError('Unknown answer validation decision.')
    if metadata.get('final_text_source')!={'supported':'original_draft','corrected':'validator_corrected','uncertain':'fixed_abstention'}[decision]:raise ValueError('Wrong final answer provenance label.')
    if result.get('final_answer')!=final['response_text']:raise ValueError('Delivered final differs from validated answer.')
    if result.get('decision')=='supported' and final['response_text']!=draft['response_text']:raise ValueError('Supported verdict changed draft.')
    return {'enabled':True,'status':'validated','attempted_calls':1,'decision':result['decision'],
            **expected,'semantic_correctness_proven':False}


def compare_observation(actual,reconstructed):
    if not isinstance(actual,dict) or not isinstance(reconstructed,dict):raise ValueError('Missing answer review replay observation.')
    # Elapsed time is runtime-only. All source, role, prompt/schema, raw review,
    # bound result, request budget and actual execution fields remain exact.
    left={k:v for k,v in actual.items() if k!='elapsed_ms'}
    right={k:v for k,v in reconstructed.items() if k!='elapsed_ms'}
    if left!=right:raise ValueError('Answer validation observation differs from strict replay.')


def summarize(runs):
    rows=[run.get('answer_validation') or {} for run in runs]
    executions=[e.get('execution') or {} for run in runs for e in run.get('extra_agent_executions',[]) if e.get('agent_role')==ROLE]
    usage={}
    for key in ('request_attempts','reported_input_tokens','reported_output_tokens','reported_total_tokens','reported_cost_credits'):
        values=[e.get(key) for e in executions]
        known=[v for v in values if type(v) in (int,float) and math.isfinite(v) and v>=0]
        usage[key]={'known_sum':sum(known),'known_executions':len(known),'total_executions':len(values),'complete_total':sum(known) if len(known)==len(values) else None}
    return {'separate_execution_usage':usage,'enabled':sum(x.get('enabled') is True for x in rows),
            'attempted_calls':sum(x.get('attempted_calls',0) for x in rows),
            'validated':sum(x.get('status')=='validated' for x in rows),
            'failed':sum(x.get('status')=='failed' for x in rows),
            'decisions':{key:sum(x.get('decision')==key for x in rows) for key in ('supported','corrected','uncertain')},
            'scope':'Exact local provenance/contract validation, not independent source review, human gold or semantic safety.'}
