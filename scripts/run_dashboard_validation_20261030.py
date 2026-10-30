"""New live exploratory run; preserve receipts and never silently retry target calls."""
import json, os, sys, time, urllib.request, urllib.error
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'/os.environ.get('AUDIT_VALIDATION_DIR','dashboard-live-validation-20261030')
OUT.mkdir(parents=True,exist_ok=True)
STATE=OUT/'state.json'
state=json.loads(STATE.read_text()) if STATE.exists() else {'status':'preparing','runs':[],'events':[]}
def save(): STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n')
def api(method,path,body=None,timeout=300):
    request=urllib.request.Request('http://127.0.0.1:8000/api/v1'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'},method=method)
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response: value=json.load(response)
    except urllib.error.HTTPError as exc:
        error=exc.read().decode();state['events'].append({'path':path,'status':exc.code,'error':error[:2000]});save();raise RuntimeError(f'{path}: {exc.code} {error[:1000]}') from exc
    state['events'].append({'path':path,'status':'ok'});save();print(method,path,'ok',flush=True);return value

strategies=['weak_first_hit','strong_rule_based','scope_aware','temporal_importance']
roles={'pipeline_provider':'rule_based','pipeline_model':'rule-based-v2','evaluator_provider':'rule_based','evaluator_model':'rule-based-v65','semantic_review_provider':'rule_based','semantic_review_model':'rule-based-v2'}
if sys.argv[1]=='prepare':
    if state['runs'] or 'experiment_id' in state: raise SystemExit('Already prepared; refusing to create duplicates')
    conversation='CA1B79085BC53479E93F820E58279B253'
    original=api('GET','/audits/RUN1EF9BA360EA44037A06B991D46A7C680')
    profile=original['reproducibility']['target_memory_profile'];profile['output_token_limit']=int(os.environ.get('AUDIT_OUTPUT_TOKEN_LIMIT','192'))
    group=api('POST','/experiments',{'conversation_id':conversation,'label':f"Dashboard live verification · four strategies · {profile['output_token_limit']} tokens · 30 Oct 2026",'test_suite_configuration':{**roles,'test_budget':4,'random_seed':42}})
    state.update(experiment_id=group['experiment_id'],conversation_id=conversation,profile=profile);save()
    for rep in range(1,4):
        for strategy in strategies:
            run=api('POST','/audits',{'conversation_id':conversation,'experiment_id':group['experiment_id'],'target_configuration':'strong','provider':'openrouter','model':'openai/gpt-6-luna',**roles,'test_budget':4,'random_seed':42,'temperature':0,'memory_strategy':strategy,'memory_maintenance_policy':'update_aware_consolidation','target_memory_capacity':50,'target_memory_writer':'rule_based','target_memory_profile':profile})
            state['runs'].append({'run_id':run['run_id'],'strategy':strategy,'repeat':rep});save()
    for row in state['runs']:
        suite=api('POST',f"/audits/{row['run_id']}/generate-tests")
        row['suite']=[{k:t[k] for k in ('test_id','dimension','prompt','expected_behavior','quality_status')} for t in suite];save()
        if len(suite)!=4 or len({t['dimension'] for t in suite})!=4 or any(t['quality_status']!='accepted' for t in suite): raise SystemExit('Suite incomplete; preserve for review')
    subset=json.loads((ROOT/'artifacts/local/phase4-c-openrouter-20261028-v6/longmemeval-subset.json').read_text())
    subset=[row for row in subset if row['question_type']=='knowledge-update'][:2]
    if len(subset)!=2: raise SystemExit('Benchmark subset not available')
    benchmark={'payload':subset,'source_authorised':True,'source_label':'two existing LongMemEval Oracle cases; exploratory dashboard verification','dataset_provenance':{'dataset_version':'longmemeval-cleaned oracle 98d7416c24c778c2fee6e6f3006e7a073259d48f','license':'MIT per dataset card','citation':'LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory, arXiv:2410.10813'},'random_seed':42,'provider':'openrouter','model':'openai/gpt-6-luna','strategies':strategies,'temperature':0,'target_memory_capacity':50,'target_memory_profile':profile,'max_cases':2}
    trials=[{'trial_id':f'repeat-{rep}','reference_run_id':next(r['run_id'] for r in state['runs'] if r['repeat']==rep and r['strategy']==strategies[0]),'candidate_run_id':next(r['run_id'] for r in state['runs'] if r['repeat']==rep and r['strategy']==strategies[1])} for rep in range(1,4)]
    state['benchmark']=benchmark;state['trials']=trials;save()
    plan=api('POST','/research/benchmarks/longmemeval/plans',{'benchmark':benchmark,'trials':trials,'sampling_rule':'First two previously used knowledge-update cases from the archived 30-case selection; exploratory UI verification, not independent validation.','evaluator_model':'openai/gpt-6-luna','evaluator_revision':'0'*40,'metadata_storage_authorised':True})
    state['plan_id']=plan['plan_id'];state['status']='prepared';save()
elif sys.argv[1]=='prepare-a':
    if state.get('a_comparison_id'): raise SystemExit('A already prepared')
    source='RUN1EF9BA360EA44037A06B991D46A7C680'
    result=api('POST',f'/audits/{source}/method-comparison',{})
    state['a_comparison_id']=result['comparison_id'];state['a_source_run_id']=source;state['a_runs']=result['runs'];save()
    (OUT/'A-inventory-human-review.json').write_text(json.dumps(result['inventory_template'],indent=2,ensure_ascii=False)+'\n')
elif sys.argv[1]=='execute':
    if state.get('status') not in ('prepared','collecting'): raise SystemExit('Not prepared')
    state['status']='collecting';save()
    for row in state['runs']:
        while not row.get('executed') and row.get('safe_retries',0)<3:
            try:
                if row.get('execute_started'):
                    info=api('GET',f"/audits/{row['run_id']}")
                    if info['status']=='FAILED':
                        plan=api('GET',f"/audits/{row['run_id']}/retry-plan")
                        if not plan['retryable'] or plan['next_stage']!='execute_tests': raise SystemExit(f"Cannot safely resume {row['run_id']}")
                        row['safe_resume_pending']=plan['pending'];row['safe_retries']=row.get('safe_retries',0)+1;save()
                        api('POST',f"/audits/{row['run_id']}/retry",{})
                    elif info['status'] not in ('TESTS_EXECUTED','COMPLETED'):
                        raise SystemExit(f"Ambiguous prior execution: {row['run_id']} ({info['status']})")
                else:
                    row['execute_started']=True;save();api('POST',f"/audits/{row['run_id']}/execute",{})
                row['executed']=True;save()
            except RuntimeError:
                time.sleep(2)
        if not row.get('executed'):
            row['failed_after_safe_retries']=True;save();continue
        if not row.get('evaluated'):
            api('POST',f"/audits/{row['run_id']}/evaluate",{});row['evaluated']=True;save()
    for trial in state['trials']:
        tid=trial['trial_id']; target=OUT/f'benchmark-{tid}.json'; marker=OUT/f'benchmark-{tid}.started'
        if marker.exists() and not target.exists():
            saved=api('GET',f"/research/benchmarks/longmemeval/plans/{state['plan_id']}")['executions'].get(tid,{})
            if saved.get('status')=='FAILED': print('Preserving failed C trial',tid,flush=True);continue
            raise SystemExit(f'Ambiguous prior benchmark execution: {tid}')
        if not target.exists():
            marker.write_text('dispatching\n')
            try:
                result=api('POST',f"/research/benchmarks/longmemeval/plans/{state['plan_id']}/execute",{'trial_id':tid,'benchmark':state['benchmark']},timeout=900)
                target.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
            except RuntimeError:
                saved=api('GET',f"/research/benchmarks/longmemeval/plans/{state['plan_id']}")['executions'].get(tid,{})
                if saved.get('status')!='FAILED': raise SystemExit(f'Ambiguous benchmark state: {tid}')
                print('Preserving failed C trial',tid,flush=True)
    c_missing=any(not (OUT/f"benchmark-{trial['trial_id']}.json").exists() for trial in state['trials'])
    state['status']='completed_with_missing_results' if c_missing or any(r.get('failed_after_safe_retries') for r in state['runs']) else 'completed';save()
else: raise SystemExit('Choose prepare or execute')
