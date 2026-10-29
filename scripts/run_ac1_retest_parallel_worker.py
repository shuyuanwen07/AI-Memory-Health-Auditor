"""Execute a preassigned untouched subset of the frozen AC1 retest once.

The caller records assignments before dispatch. Started or failed histories
are never retried and the original source-bound journal is shared unchanged.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from scripts.run_ac1_extraction_retest import (
    check_protocol, digest, exclusive_json, read_regular, source_code_sha,
    _conversation, OneRequestPerRole,
)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frozen',type=Path,required=True);p.add_argument('--frozen-sha256',required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--journal',type=Path,required=True)
    p.add_argument('--start',type=int,required=True);p.add_argument('--stop',type=int,required=True)
    args=p.parse_args()
    cfg,data=check_protocol(args.frozen,args.frozen_sha256,args.source)
    if args.start<0 or args.stop>len(data['histories']) or args.start>=args.stop:
        raise ValueError('Invalid bounded history assignment')
    marker=json.loads(read_regular(args.journal/'protocol.json'))
    if marker.get('frozen_sha256')!=args.frozen_sha256:raise ValueError('Journal differs from frozen study')
    assignment=json.loads(read_regular(args.journal/'parallel-assignment.json'))
    if (assignment.get('frozen_sha256')!=args.frozen_sha256
            or assignment.get('worker_sha256')!=digest(Path(__file__).read_bytes())
            or {'start':args.start,'stop':args.stop,'history_ids':cfg['history_ids'][args.start:args.stop]}
               not in assignment.get('assignments',[])):
        raise ValueError('Worker differs from the recorded assignment')
    from app.extraction.factory import get_memory_extractor
    from app.target_ai.request_contracts import observe_request_contracts
    for history in data['histories'][args.start:args.stop]:
        check_protocol(args.frozen,args.frozen_sha256,args.source)
        hid=history['history_id'];begin=args.journal/f'{hid}.started.json';result=args.journal/f'{hid}.result.json'
        if begin.exists() or result.exists():raise ValueError('Assigned history already started; no retry')
        conversation=_conversation(history);extractor=None
        exclusive_json(begin,{'format':'ac1-extraction-start-v1','frozen_sha256':args.frozen_sha256,
            'history_id':hid,'started_at_utc':datetime.now(timezone.utc).isoformat(),
            'worker_assignment':[args.start,args.stop]})
        try:
            extractor=get_memory_extractor(cfg['extractor']['provider'],cfg['extractor']['model'])
            with observe_request_contracts(OneRequestPerRole(cfg['extractor']['model'])):
                memories=extractor.extract(conversation)
            stages=getattr(extractor,'last_agent_stages',[])
            roles={s.get('role'):s.get('status') for s in stages if isinstance(s,dict)}
            stable=source_code_sha()==cfg['runtime_source_sha256']
            complete=all(roles.get(role)=='completed' for role in ('memory_extraction','relationship_analysis','independent_memory_review'))
            status='runtime_changed' if not stable else 'completed' if complete else 'partial'
            exclusive_json(result,{'format':'ac1-extraction-result-v1','frozen_sha256':args.frozen_sha256,
                'history_id':hid,'status':status,'source_message_ids':[m.message_id for m in conversation.messages],
                'candidates':[m.model_dump(mode='json') for m in memories], 'agent_stages':stages,
                'finished_at_utc':datetime.now(timezone.utc).isoformat()})
            print(f'{hid}: {status}',flush=True)
            if status!='completed':raise ValueError('Incomplete history retained; no automatic retry')
        except BaseException as exc:
            if not result.exists():exclusive_json(result,{'format':'ac1-extraction-result-v1',
                'frozen_sha256':args.frozen_sha256,'history_id':hid,'status':'failed','error_type':type(exc).__name__,
                'finished_at_utc':datetime.now(timezone.utc).isoformat(),
                'agent_stages':getattr(extractor,'last_agent_stages',[]) if extractor is not None else [],
                'notice':'No automatic retry. Provider billing may be unknown.'})
            raise


if __name__=='__main__':main()
