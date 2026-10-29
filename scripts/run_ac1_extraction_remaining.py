"""Predeclare and run untouched AC1 histories after a known partial result.

Never retries a started history. The original source, model, runtime and
single-request-per-role policy remain unchanged; all previous outputs and the
partial failure stay in the same private journal.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from scripts.run_ac1_extraction import (check_protocol, digest, read_regular, exclusive_json,
    _conversation, OneRequestPerRole, source_code_sha)


def prepare_addendum(frozen, frozen_sha, source, journal):
    config,data=check_protocol(frozen,frozen_sha,source)
    root=Path(journal)
    marker=json.loads(read_regular(root/'protocol.json'))
    if marker.get('frozen_sha256')!=frozen_sha: raise ValueError('Journal protocol differs')
    reviewed=[]; remaining=[]
    for case in data['histories']:
        hid=case['history_id']; started=root/f'{hid}.started.json'; result=root/f'{hid}.result.json'
        if not started.exists() and not result.exists(): remaining.append(hid); continue
        if not started.is_file() or not result.is_file():
            raise ValueError('A previous attempt has an unknown outcome; do not continue automatically')
        start_raw,result_raw=read_regular(started),read_regular(result)
        start,entry=json.loads(start_raw),json.loads(result_raw)
        if start.get('frozen_sha256')!=frozen_sha or entry.get('frozen_sha256')!=frozen_sha or start.get('history_id')!=hid or entry.get('history_id')!=hid or entry.get('status') not in ('completed','partial'):
            raise ValueError('Earlier outcome is unresolved, failed or belongs to another study')
        stages=entry.get('agent_stages',[])
        if entry['status']=='partial':
            if not stages or any((s.get('execution') or {}).get('request_attempts')!=1 or
                                  (s.get('execution') or {}).get('last_http_status')!=200 for s in stages):
                raise ValueError('Partial outcome has an unverified network attempt')
        reviewed.append({'history_id':hid,'status':entry['status'],'started_sha256':digest(start_raw),'result_sha256':digest(result_raw)})
    if not remaining or not any(item['status']=='partial' for item in reviewed):
        raise ValueError('No known partial outcome and untouched continuation set')
    return {'format':'ac1-extraction-continuation-v1','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'parent_frozen_sha256':frozen_sha,'source_sha256':config['source_sha256'],
        'runtime_source_sha256':config['runtime_source_sha256'],'continuation_script_sha256':digest(Path(__file__).read_bytes()),
        'previous_outcomes':reviewed,'remaining_history_ids':remaining,
        'policy':'Continue only never-started histories under the original frozen settings. Preserve all previous partial results and count them as incomplete. No previous request is retried.',
        'model_called':False,'new_results_observed':False}


def run_remaining(frozen,frozen_sha,source,journal,addendum,addendum_sha,*,extractor_factory=None):
    config,data=check_protocol(frozen,frozen_sha,source)
    add_raw=read_regular(addendum)
    if digest(add_raw)!=addendum_sha: raise ValueError('Continuation digest changed')
    spec=json.loads(add_raw)
    if (spec.get('format')!='ac1-extraction-continuation-v1' or spec.get('parent_frozen_sha256')!=frozen_sha or
        spec.get('source_sha256')!=config['source_sha256'] or spec.get('runtime_source_sha256')!=config['runtime_source_sha256'] or
        spec.get('continuation_script_sha256')!=digest(Path(__file__).read_bytes()) or
        spec.get('model_called') is not False or spec.get('new_results_observed') is not False):
        raise ValueError('Continuation does not bind the original frozen study and runner')
    root=Path(journal)
    for row in spec['previous_outcomes']:
        hid=row['history_id']
        if digest(read_regular(root/f'{hid}.started.json'))!=row['started_sha256'] or digest(read_regular(root/f'{hid}.result.json'))!=row['result_sha256']:
            raise ValueError('Earlier extraction evidence changed')
    histories={h['history_id']:h for h in data['histories']}
    pending=spec['remaining_history_ids']
    if len(set(pending))!=len(pending) or not set(pending)<=set(histories): raise ValueError('Continuation histories invalid')
    synthetic_factory=extractor_factory is not None
    if extractor_factory is None:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
        from app.extraction.factory import get_memory_extractor
        extractor_factory=get_memory_extractor
        allowed=Path(os.getenv('AC3_RESULTS_ROOT','/ac3-results')).resolve()/('AC1-'+config['source_sha256'][:24])
        if root.is_symlink() or root.resolve()!=allowed: raise ValueError('Use the existing source-bound journal')
    completed=0
    for hid in pending:
        check_protocol(frozen,frozen_sha,source)
        if digest(Path(__file__).read_bytes())!=spec['continuation_script_sha256']:
            raise ValueError('Continuation runner changed')
        begin=root/f'{hid}.started.json'; result=root/f'{hid}.result.json'
        if result.exists():
            entry=json.loads(read_regular(result))
            if entry.get('frozen_sha256')!=frozen_sha or entry.get('history_id')!=hid or entry.get('status')!='completed':
                raise ValueError('A continuation attempt is partial or failed; no automatic retry')
            completed+=1;continue
        if begin.exists(): raise ValueError('A continuation attempt is unresolved; no automatic retry')
        conversation=_conversation(histories[hid]);extractor=None
        exclusive_json(begin,{'format':'ac1-extraction-start-v1','frozen_sha256':frozen_sha,'history_id':hid,
            'continuation_sha256':addendum_sha,'started_at_utc':datetime.now(timezone.utc).isoformat()})
        try:
            from app.target_ai.request_contracts import observe_request_contracts
            extractor=extractor_factory(config['extractor']['provider'],config['extractor']['model'])
            observer=OneRequestPerRole(config['extractor']['model'])
            with observe_request_contracts(observer): memories=extractor.extract(conversation)
            candidates=[m.model_dump(mode='json') for m in memories]
            stable=source_code_sha()==config['runtime_source_sha256'] and digest(Path(__file__).read_bytes())==spec['continuation_script_sha256']
            stages=getattr(extractor,'last_agent_stages',[]); roles={s.get('role'):s.get('status') for s in stages if isinstance(s,dict)}
            complete=synthetic_factory or all(roles.get(role)=='completed' for role in ('memory_extraction','relationship_analysis','independent_memory_review'))
            status='runtime_changed' if not stable else ('completed' if complete else 'partial')
            exclusive_json(result,{'format':'ac1-extraction-result-v1','frozen_sha256':frozen_sha,'history_id':hid,'status':status,
                'source_message_ids':[m.message_id for m in conversation.messages], 'candidates':candidates,'agent_stages':stages,
                'continuation_sha256':addendum_sha,'finished_at_utc':datetime.now(timezone.utc).isoformat()})
            if status!='completed': raise ValueError('A required stage is incomplete; saved without automatic retry')
            completed+=1
        except BaseException as exc:
            if not result.exists(): exclusive_json(result,{'format':'ac1-extraction-result-v1','frozen_sha256':frozen_sha,'history_id':hid,
                'status':'failed','error_type':type(exc).__name__,'continuation_sha256':addendum_sha,
                'agent_stages':getattr(extractor,'last_agent_stages',[]) if extractor is not None else [],
                'finished_at_utc':datetime.now(timezone.utc).isoformat(),'notice':'No automatic retry; provider billing may be unknown.'})
            raise
    return {'status':'completed_with_preserved_partial','continued_histories':completed,'earlier_partial_count':sum(x['status']=='partial' for x in spec['previous_outcomes']),
            'frozen_sha256':frozen_sha,'human_output_review_completed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for name in ('prepare','run'):
        q=sub.add_parser(name);q.add_argument('--frozen',type=Path,required=True);q.add_argument('--frozen-sha256',required=True)
        q.add_argument('--source',type=Path,required=True);q.add_argument('--journal',type=Path,required=True);q.add_argument('--addendum',type=Path,required=True)
        if name=='run':q.add_argument('--addendum-sha256',required=True)
    a=p.parse_args()
    if a.command=='prepare':
        spec=prepare_addendum(a.frozen,a.frozen_sha256,a.source,a.journal);exclusive_json(a.addendum,spec)
        print(json.dumps({'addendum_sha256':digest(a.addendum.read_bytes()),'remaining_histories':len(spec['remaining_history_ids']),'previous_outcomes':len(spec['previous_outcomes']),'model_called':False}))
    else:print(json.dumps(run_remaining(a.frozen,a.frozen_sha256,a.source,a.journal,a.addendum,a.addendum_sha256)))

if __name__=='__main__':main()
