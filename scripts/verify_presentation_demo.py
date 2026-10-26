"""Offline reconciliation/input replay for the saved visible presentation demo.

No grading, inference, database writes or network requests. Byte/contract checks
are not semantic truth, human gold, determinism or a benchmark claim.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
from datetime import datetime

from run_presentation_demo import (source_release,suite_fingerprint,inventory_fingerprint,
                                  canonical,sha,atomic_json,MODEL,DIMENSIONS)


def application_source_hash(package):
    digest=hashlib.sha256()
    for path in sorted(package.rglob('*.py')):
        relative=path.relative_to(package).as_posix().encode();content=path.read_bytes()
        digest.update(len(relative).to_bytes(8,'big'));digest.update(relative)
        digest.update(len(content).to_bytes(8,'big'));digest.update(content)
    return digest.hexdigest()


def verify(report,release,hashes):
    errors=[];warnings=[];input_checks=[];roles=[]
    def check(value,label):
        if not value:errors.append(label)
    check(report.get('source_hashes')==hashes,'source release byte hashes changed')
    check(report.get('database')=='existing_running_service_database' and report.get('database_replaced') is False,'existing database provenance missing')
    check(report.get('research_evidence') is False and report.get('new_human_annotation') is False,'engineering provenance absent')
    runs=report.get('runs',[]);check(len(runs)==6,'six predeclared runs missing')
    check(len({r['run_id'] for r in runs})==len(runs),'duplicate run ID')
    check(Counter(r['strategy'] for r in runs)==Counter({'weak_first_hit':3,'strong_rule_based':3}),'strategy/repetition grid differs')
    frozen=report.get('frozen_suite') or {};fingerprint=frozen.get('fingerprint')
    check(fingerprint is not None and suite_fingerprint(frozen.get('suite',[]))==fingerprint,'frozen suite missing or changed')
    if report.get('repeat_from'):
        check(frozen.get('generator_dispatches')==0 and report.get('repeat_suite_pin',{}).get('suite_fingerprint')==fingerprint,'repeat did not pin original suite without generation')
    else:
        check(frozen.get('generator_dispatches')==1,'initial suite generation count differs')
        expected={'memory_extraction','relationship_analysis','independent_memory_review'}
        agents=report.get('extraction_agents',[])
        check(expected<={a['role'] for a in agents},'three extraction roles not observed')
        for agent in agents:
            roles.append({key:agent.get(key) for key in ('role','status','model','reported_model','attempt_count')})
            if agent.get('status')!='completed':warnings.append('Actual extraction stage failed; curated reference cannot turn it into a model success: '+agent.get('role','unknown'))
            elif agent.get('model')!=MODEL or agent.get('reported_model')!=MODEL:errors.append('extraction actual model mismatch')
    memory_map=(report.get('confirmation') or {}).get('inventory_mapping',{})
    actual_inventory=(report.get('confirmation') or {}).get('inventory',[])
    expected=release['curated-inventory']['memories'];actual_by_id={m['memory_id']:m for m in actual_inventory}
    check(len(actual_inventory)==len(expected)==len(memory_map),'curated inventory count mismatch')
    for item in expected:
        actual=actual_by_id.get(memory_map.get(item['memory_id'])) or {}
        check(actual.get('canonical_value')==item['canonical_value'] and actual.get('source_message_ids')==item['source_message_ids'],'curated memory differs: '+item['memory_id'])
    for run in runs:
        rid=run['run_id'];config=run.get('configuration',{});profile=config.get('target_memory_profile',{})
        check(config.get('target_configuration')==('weak' if run['strategy']=='weak_first_hit' else 'strong'),rid+' ordinary condition differs')
        check(config.get('memory_strategy')==run['strategy'] and config.get('retrieval_mode')=='fixed' and config.get('target_memory_writer')=='rule_based',rid+' retrieval/writer configuration differs')
        check(config.get('target_memory_capacity')==100 and profile.get('max_retrieved_records')==100 and profile.get('context_character_budget')==24000,rid+' memory budget differs')
        check(profile.get('answer_validation','off')=='off' and profile.get('identity_analysis','off')=='off',rid+' unplanned extra target role')
        check(profile.get('output_token_limit')==8192 and profile.get('reasoning_effort')=='medium',rid+' target budget/effort differs')
        tests=run.get('tests',[]);check(suite_fingerprint(tests)==fingerprint,rid+' suite differs')
        check(Counter(t['dimension'] for t in tests)==Counter({d:2 for d in DIMENSIONS}),rid+' per-dimension count differs')
        responses={x['response_id']:x for x in run.get('responses',[])};evaluations=run.get('evaluations',[])
        check(len(responses)==len(evaluations)==8,rid+' first-attempt response/evaluation coverage incomplete')
        test_by_id={t['test_id']:t for t in tests}
        trace=run.get('memory_trace') or {};records={x['memory_id']:x for x in trace.get('records',[])}
        check(bool(records) and len(trace.get('retrievals',[]))==len(responses),rid+' private memory trace incomplete')
        for response in responses.values():
            meter=response.get('execution_metadata') or {}
            check(response.get('model')==MODEL and meter.get('reported_model')==MODEL,rid+' target actual model mismatch')
            check(meter.get('requested_output_token_limit')==8192,rid+' target actual budget mismatch')
            check(meter.get('completion_status')=='complete',rid+' target output incomplete')
        for evaluation in evaluations:
            response=responses.get(evaluation['response_id']);meter=evaluation.get('judge_execution') or {}
            check(response is not None and response['test_id']==evaluation['test_id'],rid+' evaluation binding mismatch')
            check(meter.get('provider')=='openrouter' and meter.get('model')==MODEL,rid+' judge configured model differs')
            if meter.get('reported_model')!=MODEL:warnings.append(rid+' judge actual model unverified for '+evaluation['evaluation_id'])
            if meter.get('requested_output_token_limit')!=8192:warnings.append(rid+' judge actual output cap unverified for '+evaluation['evaluation_id'])
            if evaluation.get('passed') is None:warnings.append(rid+' uncertain evaluation retained: '+evaluation['evaluation_id'])
        # Exact selected-context and instruction reconstruction uses this same
        # source version. No retrieval re-selection, model or evaluator rerun.
        from app.schemas import TestCase
        from app.schemas.target_profile import TargetMemoryProfile
        from app.memory_agent.store import SqlTargetMemoryStore
        from app.target_ai.rule_based import private_context_instruction,memory_input_evidence,selected_memory_context
        store=object.__new__(SqlTargetMemoryStore);store.profile=TargetMemoryProfile.model_validate(profile)
        for retrieval in trace.get('retrievals',[]):
            try:
                public=test_by_id[retrieval['test_id']]
                context=[]
                for mid in retrieval['selected_memory_ids']:
                    record=records[mid]
                    observed=record.get('observed_at')
                    record_object=SimpleNamespace(canonical_value=record['canonical_value'],source_message_ids=record['source_message_ids'],
                        observed_at=datetime.fromisoformat(observed.replace('Z','+00:00')) if observed else None)
                    context.append(store._render_context({'record':record_object,'test_prompt':public['prompt']}))
                private=TestCase.model_validate(public).model_copy(update={'expected_behavior':'','supporting_memory_ids':[],'target_memory_context':context})
                instruction=private_context_instruction(private,config['target_configuration'])
                rebuilt=memory_input_evidence(private,config['target_configuration'],instruction).model_dump(mode='json')
                saved=retrieval['memory_input']
                check({k:v for k,v in saved.items() if k!='sent_memory_ids'}=={k:v for k,v in rebuilt.items() if k!='sent_memory_ids'},rid+' exact input receipt mismatch '+public['test_id'])
                if saved.get('sent_memory_ids') is not None:
                    by_value={}
                    for mid,value in zip(retrieval['selected_memory_ids'],context):by_value.setdefault(value.strip(),mid)
                    check(saved['sent_memory_ids']==[by_value[v] for v in selected_memory_context(private,config['target_configuration'])],rid+' supplied IDs mismatch')
                input_checks.append({'run_id':rid,'test_id':public['test_id'],'instruction_sha256':rebuilt['instruction_sha256'],'context_sha256':rebuilt['context_sha256'],'prompt_sha256':rebuilt['prompt_sha256']})
            except Exception as exc:errors.append(rid+' replay reconstruction error '+type(exc).__name__)
    bundle=report.get('export_bundle') or {};csv_rows=list(csv.DictReader(io.StringIO(report.get('export_csv',''))))
    actual_evaluation_ids={e['evaluation_id'] for run in runs for e in run.get('evaluations',[])}
    json_answers=[answer for run in bundle.get('runs',[]) for answer in run.get('answers',[])]
    csv_answers=[row for row in csv_rows if row.get('record_type')=='answer']
    check({a['evaluation_id'] for a in json_answers}==actual_evaluation_ids,'JSON export evaluation identities differ')
    check({a['evaluation_id'] for a in csv_answers}==actual_evaluation_ids,'CSV export evaluation identities differ')
    check(len(json_answers)==len(csv_answers)==len(actual_evaluation_ids),'JSON/CSV duplicate or missing evaluation rows')
    for exported in bundle.get('runs',[]):
        original=next((r for r in runs if r['run_id']==exported['configuration']['run_id']),None)
        check(original is not None and exported.get('result')==original.get('result'),'exported group result differs from recorded API result')
    counts={strategy:[{'repetition':r['repetition'],'passed':(r.get('result') or {}).get('tests_passed'),
       'scored':(r.get('result') or {}).get('tests_total'),'uncertain':(r.get('result') or {}).get('uncertain_count')} for r in runs if r['strategy']==strategy]
       for strategy in ('weak_first_hit','strong_rule_based')}
    return {'status':'passed' if not errors else 'failed','errors':errors,'warnings':warnings,'actual_grade_summary':counts,
      'saved_workflow_status':report.get('status'),'runs_checked':len(runs),'exact_input_checks':input_checks,
      'json_answer_count':len(json_answers),'csv_answer_count':len(csv_answers),'evaluation_count':len(actual_evaluation_ids),
      'actual_extraction_roles':roles,'source_semantic_correctness_proven':False,
      'limitations':['Automated grades are preserved, not regraded.','Byte replay does not prove model attention, factual correctness or independent human annotation.',
       'Three repetitions of one authored example do not demonstrate broad stability/generalization.','Read the original group for exact prior results; a new same-suite peer group can produce different answers.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]/'datasets/demo/presentation-memory-v1')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('Never overwrite a verification receipt.')
    report=json.loads(args.report.read_text());release,_,hashes=source_release(args.source)
    root=Path(__file__).resolve().parents[1];package=Path('/app/app') if Path('/app/app').exists() else root/'backend/app'
    current=application_source_hash(package)
    saved={((r.get('configuration') or {}).get('reproducibility') or {}).get('audit_runtime_signature',{}).get('source_sha256') for r in report.get('runs',[])}
    if not saved or saved!={current}:raise ValueError('Restore the saved application source version before exact input reconstruction.')
    sys.path.insert(0,'/app' if Path('/app/app').exists() else str(root/'backend'))
    original=socket.socket.connect;attempts=0
    def blocked(*args,**kwargs):
        nonlocal attempts
        attempts+=1;raise RuntimeError('Network forbidden during offline verification.')
    socket.socket.connect=blocked
    try:proof=verify(report,release,hashes)
    finally:socket.socket.connect=original
    proof.update(report_sha256=sha(args.report.read_bytes()),source_hashes=hashes,current_application_source_sha256=current,model_calls=0,network_attempts=attempts)
    if attempts:proof['status']='failed';proof['errors'].append('Unexpected network attempt')
    atomic_json(args.output,proof)
    print(canonical({'status':proof['status'],'runs_checked':proof['runs_checked'],'input_checks':len(proof['exact_input_checks']),'output':str(args.output)}))
    return 0 if proof['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
