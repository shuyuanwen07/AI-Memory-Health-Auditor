"""Aggregate immutable Phase 3 evidence without changing any verdict."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];p=ROOT/'artifacts/local/phase3-20261027'
freeze=json.loads((p/'validation-code-freeze.json').read_text())
assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in freeze['source'].items())
result={'scope':'synthetic_engineering_validation_not_independent_research','code_unchanged_after_validation_freeze':True,'splits':{}}
for split in ['development','validation']:
 before=json.loads((p/(split+'-before.json')).read_text());after=json.loads((p/(split+'-after.json')).read_text())
 weak=lambda x:{r['id']:r['context'] for r in x['retrieval'] if r['policy']=='weak_first_hit'}
 assert weak(before)==weak(after)
 assert [r['id'] for r in before['evaluations']]==[r['id'] for r in after['evaluations']]
 result['splits'][split]={'before':before['summary'],'after':after['summary'],'weak_contexts_unchanged':True,'changed_evaluation_ids':[a['id'] for b,a in zip(before['evaluations'],after['evaluations']) if b['actual']['passed']!=a['actual']['passed']]}
live=json.loads((p/'live-validation.json').read_text());original=json.loads((p/'live-script-failure-original.json').read_text());plan=json.loads((p/'live-plan.json').read_text());assert live['status']=='completed' and len(live['trials'])==9
assert live['plan_sha256']==hashlib.sha256((p/'live-plan.json').read_bytes()).hexdigest()
assert live['trials'][0]['response']==original['trials'][0]['response'],'Paid response must not be regenerated on script resume'
counts={};usage={k:0 for k in ['input_tokens','output_tokens','total_tokens']}
for row in live['trials']:
 condition=row['condition'];counts.setdefault(condition,{'trials':0,'frozen_automatic_check_passed':0,'source_options_named':0})
 counts[condition]['trials']+=1;counts[condition]['frozen_automatic_check_passed']+=bool(row['task_criterion_passed'])
 trial=next(t for t in plan['trials'] if t['id']==row['id']);text=row['response']['response_text'].lower()
 counts[condition]['source_options_named']+=all(option in text for option in trial['expected_options'])
 meta=row['response']['execution_metadata'];assert meta['completion_status']=='complete'
 assert meta['request_contract']['payload_sha256']
 assert 'expected_behavior' not in json.dumps(row['verified_request_payload'])
 assert meta['reported_model']=='openai/gpt-6-luna'
 for k in usage:usage[k]+=meta.get(k) or 0
result['live']={'conditions':counts,'usage':usage,'actual_successful_responses':9,'resumed_without_repeating_saved_call':True,'estimated_standard_rate_usd':usage['input_tokens']*0.10/1e6+usage['output_tokens']*0.50/1e6,'limitation':'Automatic check misses the model clarification question “Which database requirement should be followed?”; all original false flags retained. Source-option presence is only a text check, not independent semantic grading.'}
result['historical_release20_raw_available']=False
result['historical_release20_original_score_unchanged']='26/36=72.22%, below frozen75%; original two critical owner/actor errors not reverified because raw responses are missing'
result['files']={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.glob('*.json') if f.name!='summary.json'}
(p/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='files'},indent=2))
