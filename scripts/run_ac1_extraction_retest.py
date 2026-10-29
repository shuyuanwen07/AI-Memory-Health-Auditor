"""Freeze and run the repaired AC1 extraction in a separate no-repeat journal.

The freeze step never calls a model. Running may incur OpenRouter charges.
Each source history is independent; any unknown/failed attempt stops rather
than silently resending it. The extractor sees only source messages, never the
human reference facts, AC3 questions, or expected answers.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
MODEL='openai/gpt-6-luna'


def digest(raw): return hashlib.sha256(raw).hexdigest()


def source_code_sha():
    package=ROOT/'backend/app'; value=hashlib.sha256()
    for path in sorted(package.rglob('*.py')):
        name=path.relative_to(package).as_posix().encode(); body=path.read_bytes()
        value.update(len(name).to_bytes(8,'big')); value.update(name)
        value.update(len(body).to_bytes(8,'big')); value.update(body)
    return value.hexdigest()


def read_regular(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError('A regular input file is required')
    return path.read_bytes()


def exclusive_json(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def verify_source_bundle(source):
    """Recheck user-confirmed provenance before creating the source freeze."""
    from scripts.import_ac3_expanded_reviews import verify_expanded_manifest
    from scripts.ac3_reviewed_fact_map import validate_fact_plan
    entries=source.get('inputs')
    if not isinstance(entries,list) or len(entries)!=7:
        raise ValueError('Reviewed source provenance is incomplete')
    paths=[Path(item['path']) for item in entries]
    raw=[read_regular(path) for path in paths]
    if any(digest(data)!=entry.get('sha256') for data,entry in zip(raw,entries)):
        raise ValueError('Reviewed source evidence changed')
    verified=verify_expanded_manifest(paths[2],raw[0],raw[3:5],raw[5:7])
    original, plan=json.loads(raw[0]),json.loads(raw[1])
    fact_review=validate_fact_plan(original,plan,[json.loads(data) for data in raw[5:7]])
    if verified['fact_plan_sha256']!=fact_review['fact_plan_sha256']:
        raise ValueError('Reviewed fact plan differs from source provenance')
    derived=[{'history_id':case['history_id'],'source_messages':case['source_messages'],
              'reviewed_reference':plan['histories'][case['history_id']]} for case in original['cases']]
    if derived!=source['histories']:
        raise ValueError('Source-only bundle differs from the reviewed histories')
    required=[{'history_id':'AC3-H19','fact_id':'AC3-H19-F8','status':'unresolved',
        'reason':'The additional public-library location is not established by the cited source. Preserve the earlier reviewed fact, but do not count it as confirmed gold without independent resolution.'},
        {'history_id':'AC3-H19','relationship_type':'CONTEXTUAL_OVERRIDE',
        'memory_id':'AC3-H19-F8','target_memory_id':'AC3-H19-F7','status':'unresolved',
        'reason':'Offering digital instructions is an option and does not by itself override a paper preference. Preserve this earlier reviewed edge, but do not count it as a confirmed override without independent resolution.'}]
    if source.get('reference_qualifications') != required:
        raise ValueError('The known H19 relationship qualification must remain explicit')


def prepare_freeze(source_path):
    source_raw=read_regular(source_path); source=json.loads(source_raw)
    if source.get('format')!='ac1-ac2-reviewed-source-v1' or source.get('history_count')!=len(source.get('histories',[])):
        raise ValueError('Expected the verified source-only review bundle')
    verify_source_bundle(source)
    ids=[h.get('history_id') for h in source['histories']]
    if not ids or len(ids)!=len(set(ids)) or any(not isinstance(x,str) or not x.strip() for x in ids):
        raise ValueError('The source history set is empty or duplicated')
    return {'format':'ac1-extraction-prospective-frozen-v1','frozen_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_sha256':digest(source_raw),'source_path':str(Path(source_path).resolve()),'history_ids':ids,
        'runtime_source_sha256':source_code_sha(),'runner_source_sha256':digest(Path(__file__).read_bytes()),
        'extractor':{'provider':'openrouter','model':MODEL,'implementation_version':'memory-extraction-agent-v12',
                     'relationship_version':'relationship-analysis-agent-v6','review_version':'independent-memory-review-agent-v2'},
        'source_timestamp_policy':'2000-01-01T00:00:00Z + source_order seconds; synthetic placeholder, not observation time',
        'reference_policy':'Only source messages are passed to the extractor. Human-reviewed facts and relationships are kept for subsequent independent review.',
        'reference_qualifications':source.get('reference_qualifications',[]),
        'repeat_policy':'One app extraction invocation per history and at most one HTTP request per extraction role. Automatic transport retries, fallback and format corrections are vetoed before sending; failed or unresolved histories are not automatically rerun.',
        'billing':'User authorized use of available credits. Provider-reported usage may be incomplete and is not a reconciled invoice.',
        'model_called':False,'results_observed':False}


def check_protocol(path, expected_sha, source_path):
    raw=read_regular(path)
    if digest(raw)!=expected_sha: raise ValueError('Frozen protocol digest changed')
    config=json.loads(raw); source_raw=read_regular(source_path); source=json.loads(source_raw)
    if (config.get('format')!='ac1-extraction-prospective-frozen-v1' or config.get('model_called') is not False or
        config.get('results_observed') is not False or config.get('source_sha256')!=digest(source_raw) or
        config.get('runtime_source_sha256')!=source_code_sha() or config.get('runner_source_sha256')!=digest(Path(__file__).read_bytes()) or
        config.get('history_ids')!=[h['history_id'] for h in source.get('histories',[])]):
        raise ValueError('Frozen source, runtime or protocol does not match')
    return config, source


def _conversation(history):
    from app.schemas import Conversation, ConversationMessage
    start=datetime(2000,1,1,tzinfo=timezone.utc)
    messages=[]
    for i, message in enumerate(history['source_messages']):
        if message.get('order') != i+1 or message.get('role')!='user':
            raise ValueError('Source message order or role differs from the reviewed source')
        messages.append(ConversationMessage(message_id=message['message_id'],role='user',content=message['text'],timestamp=start+timedelta(seconds=i)))
    return Conversation(conversation_id=history['history_id'],authorised=True,source_origin='synthetic',created_at=start,messages=messages)


class OneRequestPerRole:
    """Veto fallback or automatic retry before any repeated paid request."""
    def __init__(self, model): self.model,self.seen=model,set()
    def __call__(self, receipt):
        if receipt.get('phase')!='before_send': return
        contract=receipt.get('request_contract') or {}
        role=contract.get('role')
        if (role not in {'memory_extraction','relationship_analysis','independent_memory_review'} or
            role in self.seen or receipt.get('attempt_index')!=1 or
            contract.get('provider_name')!='openrouter' or contract.get('model')!=self.model):
            raise ValueError('Unexpected provider, role, or repeated paid request is blocked')
        self.seen.add(role)


def run(frozen_path, frozen_sha, source_path, results_dir, *, extractor_factory=None):
    config, source=check_protocol(frozen_path,frozen_sha,source_path)
    # Dependency injection is permitted only for isolated tests. Production
    # callers use the actual application factory, never a supplied gold plan.
    synthetic_factory = extractor_factory is not None
    if extractor_factory is None:
        sys.path.insert(0,str(ROOT/'backend'))
        from app.extraction.factory import get_memory_extractor
        extractor_factory=get_memory_extractor
        root=Path(os.getenv('AC3_RESULTS_ROOT',str(ROOT/'output/ac3-generated'))).resolve()
        wanted=root/('AC1-RETEST-'+config['source_sha256'][:16]+'-'+config['runtime_source_sha256'][:16])
        if Path(results_dir).is_symlink() or Path(results_dir).resolve()!=wanted:
            raise ValueError('Production results must use the single source-bound journal directory')
    directory=Path(results_dir)
    if directory.is_symlink(): raise ValueError('Results directory cannot be a symlink')
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    marker=directory/'protocol.json'
    if marker.exists():
        if marker.is_symlink() or json.loads(marker.read_text()).get('frozen_sha256')!=frozen_sha:
            raise ValueError('Results belong to a different frozen extraction protocol')
    else: exclusive_json(marker,{'format':'ac1-extraction-ledger-v1','frozen_sha256':frozen_sha})
    completed=0
    for history in source['histories']:
        check_protocol(frozen_path,frozen_sha,source_path)
        hid=history['history_id']
        if not all(c.isalnum() or c in '-_' for c in hid): raise ValueError('Unsafe history ID')
        begin=directory/f'{hid}.started.json'; result=directory/f'{hid}.result.json'
        if result.exists():
            entry=json.loads(read_regular(result))
            if entry.get('frozen_sha256')!=frozen_sha or entry.get('history_id')!=hid or entry.get('status')!='completed':
                raise ValueError('Saved extraction result is invalid or failed; no automatic retry')
            completed+=1;continue
        if begin.exists():
            raise ValueError('Previous extraction has an unresolved outcome; no automatic retry')
        conversation=_conversation(history)
        exclusive_json(begin,{'format':'ac1-extraction-start-v1','frozen_sha256':frozen_sha,'history_id':hid,
            'started_at_utc':datetime.now(timezone.utc).isoformat()})
        extractor=None
        try:
            extractor=extractor_factory(config['extractor']['provider'],config['extractor']['model'])
            from app.target_ai.request_contracts import observe_request_contracts
            observer=OneRequestPerRole(config['extractor']['model'])
            with observe_request_contracts(observer):
                memories=extractor.extract(conversation)
            candidates=[memory.model_dump(mode='json') for memory in memories]
            # The app retains actual model outputs and observations; reference
            # labels are not substituted or marked as automatically correct.
            stable=(source_code_sha()==config['runtime_source_sha256'] and digest(Path(__file__).read_bytes())==config['runner_source_sha256'])
            stages=getattr(extractor,'last_agent_stages',[])
            roles={stage.get('role'):stage.get('status') for stage in stages if isinstance(stage,dict)}
            complete = synthetic_factory or all(roles.get(role)=='completed' for role in ('memory_extraction','relationship_analysis','independent_memory_review'))
            state = 'runtime_changed' if not stable else ('completed' if complete else 'partial')
            entry={'format':'ac1-extraction-result-v1','frozen_sha256':frozen_sha,'history_id':hid,'status':state,
                'source_message_ids':[m.message_id for m in conversation.messages], 'candidates':candidates,
                'agent_stages':stages,
                'finished_at_utc':datetime.now(timezone.utc).isoformat()}
            exclusive_json(result,entry)
            if not stable: raise ValueError('Runtime changed during extraction; saved output requires investigation')
            if not complete: raise ValueError('A required extraction role did not complete; output saved, no automatic retry')
            completed+=1
        except BaseException as exc:
            # The output may have been charged even when the client has no
            # usable reply. Preserve a bounded category and stop the batch.
            if not result.exists():
                exclusive_json(result,{'format':'ac1-extraction-result-v1','frozen_sha256':frozen_sha,'history_id':hid,
                    'status':'failed','error_type':type(exc).__name__,'finished_at_utc':datetime.now(timezone.utc).isoformat(),
                    'agent_stages':getattr(extractor,'last_agent_stages',[]) if extractor is not None else [],
                    'notice':'No automatic retry. Provider billing may be unknown.'})
            raise
    return {'status':'completed','histories_completed':completed,'frozen_sha256':frozen_sha,
            'human_output_review_completed':False,'provider_cost_status':'provider_reports_not_reconciled'}


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    f=sub.add_parser('freeze');f.add_argument('--source',type=Path,required=True);f.add_argument('--output',type=Path,required=True)
    r=sub.add_parser('run');r.add_argument('--source',type=Path,required=True);r.add_argument('--frozen',type=Path,required=True);r.add_argument('--frozen-sha256',required=True);r.add_argument('--results-dir',type=Path,required=True)
    a=p.parse_args()
    if a.command=='freeze':
        value=prepare_freeze(a.source);exclusive_json(a.output,value)
        print(json.dumps({'frozen_sha256':digest(a.output.read_bytes()),'histories':len(value['history_ids']),'model_called':False}))
    else: print(json.dumps(run(a.frozen,a.frozen_sha256,a.source,a.results_dir)))

if __name__=='__main__':main()
