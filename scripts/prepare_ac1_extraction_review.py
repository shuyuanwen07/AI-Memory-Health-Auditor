"""Prepare two independent AC1 reviews from a completed source-only journal.

This command produces no human decisions and makes no claim that reviewed
reference facts are exhaustive. It retains failed/missing histories explicitly.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


def sha(raw): return hashlib.sha256(raw).hexdigest()


def read(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError('Evidence must be a regular file')
    return path.read_bytes()


def stamp(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None: raise ValueError('Timestamp must have a timezone')
    return d.astimezone(timezone.utc)


def make_packets(frozen_path,frozen_sha,source_path,journal_dir,*,allow_partial=False):
    frozen_raw,source_raw=read(frozen_path),read(source_path)
    if sha(frozen_raw)!=frozen_sha: raise ValueError('Frozen extraction protocol digest changed')
    frozen,source=json.loads(frozen_raw),json.loads(source_raw)
    if (frozen.get('format')!='ac1-extraction-prospective-frozen-v1' or
        frozen.get('source_sha256')!=sha(source_raw) or frozen.get('model_called') is not False or
        frozen.get('results_observed') is not False or frozen.get('history_ids')!=[h['history_id'] for h in source['histories']]):
        raise ValueError('Protocol does not bind the reviewed source')
    root=Path(journal_dir)
    if root.is_symlink() or not root.is_dir(): raise ValueError('Journal must be a private directory')
    marker=read(root/'protocol.json')
    if json.loads(marker).get('frozen_sha256')!=frozen_sha: raise ValueError('Journal belongs to another protocol')
    qualifications=source.get('reference_qualifications',[])
    histories=[]; hashes={'frozen':frozen_sha,'source':sha(source_raw),'journal_marker':sha(marker)}
    for history in source['histories']:
        hid=history['history_id']; started=root/f'{hid}.started.json'; result=root/f'{hid}.result.json'
        start_raw=read(started) if started.is_file() else None
        result_raw=read(result) if result.is_file() else None
        start=json.loads(start_raw) if start_raw else None; entry=json.loads(result_raw) if result_raw else None
        if start and (start.get('history_id')!=hid or start.get('frozen_sha256')!=frozen_sha or stamp(start['started_at_utc'])<=stamp(frozen['frozen_at_utc'])):
            raise ValueError('Saved invocation differs or predates the protocol freeze')
        if entry and (not start or entry.get('history_id')!=hid or entry.get('frozen_sha256')!=frozen_sha or stamp(entry['finished_at_utc'])<stamp(start['started_at_utc'])):
            raise ValueError('Saved extraction result differs or predates its invocation')
        status=entry.get('status') if entry else ('unknown' if start else 'not_started')
        if status not in ('completed','partial','failed','runtime_changed','unknown','not_started'):
            raise ValueError('Unknown extraction state')
        if status in ('unknown','not_started') and not allow_partial:
            raise ValueError('Collection is still missing or has an unknown attempt; explicitly request a partial review if needed')
        candidates=[]; edges=[]
        for candidate in (entry.get('candidates',[]) if entry and status in ('completed','partial') else []):
            cid=candidate.get('memory_id')
            if not isinstance(cid,str) or not cid.strip() or any(c['candidate']['candidate_id']==cid for c in candidates):
                raise ValueError('Saved candidate identities are invalid or duplicated')
            candidates.append({'candidate':{'candidate_id':cid,'canonical_value':candidate.get('canonical_value'),
                'source_message_ids':candidate.get('source_message_ids',[])},
                'review':{'supported':None,'matched_reference_fact_ids':[],'note':''}})
            for i,edge in enumerate(candidate.get('relationships',[]),1):
                edges.append({'relationship':{'relationship_id':f'{cid}-R{i}','from_candidate_id':cid,
                    'to_candidate_id':edge.get('target_memory_id'),'relationship_type':edge.get('type'),
                    'evidence_message_ids':edge.get('evidence_message_ids',[])},'review':{'correct':None,'note':''}})
        facts=[]
        for fact in history['reviewed_reference']['facts']:
            unresolved=any(q.get('history_id')==hid and q.get('fact_id')==fact['memory_id'] and q.get('status')=='unresolved' for q in qualifications)
            facts.append({'fact':fact,'reference_status':'unresolved' if unresolved else 'reviewed'})
        relations=[]
        for edge in history['reviewed_reference']['relationships']:
            unresolved=any(q.get('history_id')==hid and q.get('memory_id')==edge['memory_id'] and
                q.get('target_memory_id')==edge['target_memory_id'] and q.get('relationship_type')==edge['relationship_type'] and
                q.get('status')=='unresolved' for q in qualifications)
            relations.append({'relationship':edge,'reference_status':'unresolved' if unresolved else 'reviewed'})
        if start_raw: hashes[f'{hid}.started']=sha(start_raw)
        if result_raw: hashes[f'{hid}.result']=sha(result_raw)
        histories.append({'history_id':hid,'source_messages':history['source_messages'],'extraction_status':status,
            'reviewed_reference_facts':facts,'reviewed_reference_relationships':relations,
            'candidates':candidates,'relationships':edges})
    instructions=['两人独立核对，不看对方判断，按实际情况声明是否使用 AI。',
        '对每条候选记忆，supported 填 valid、invalid 或 uncertain；valid 时 matched_reference_fact_ids 填所有语义对应的已审参考事实 ID。一个候选可匹配多条；不得因为部分匹配而忽略不受支持的内容。',
        '对每条预测 UPDATE/CONFLICT/CONTEXTUAL_OVERRIDE 关系，correct 填 valid、invalid 或 uncertain；证据、方向或类型不对时填 invalid。未预测出的参考关系仍会单独计入遗漏检查。',
        'reference_status=unresolved 的旧事实或关系不是确认金标准，不得仅因它出现在清单中判对；请根据原文给候选独立判断。',
        '请对 invalid 或 uncertain 写明理由。不要删除或改写来源、候选、参考和 ID；失败或未开始的历史没有假造候选。']
    result=[{'format':'ac1-extraction-human-review-v1','reviewer_slot':i,'frozen_sha256':frozen_sha,
        'evidence_sha256':hashes,'instructions':instructions,
        'reviewer_declaration':{'reviewer_label':None,'completed_by_human':None,'completed_independently':None,'used_ai_assistance':None,'note':''},
        'histories':histories} for i in (1,2)]
    return result,hashes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frozen',type=Path,required=True);p.add_argument('--frozen-sha256',required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--journal-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--allow-partial',action='store_true',help='Explicitly prepare only a partial review when collection is unresolved.');a=p.parse_args()
    packets,hashes=make_packets(a.frozen,a.frozen_sha256,a.source,a.journal_dir,allow_partial=a.allow_partial)
    if a.output_dir.exists():raise FileExistsError('Review output already exists')
    a.output_dir.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='.ac1-review-',dir=a.output_dir.parent))
    try:
        for i,packet in enumerate(packets,1):
            fd=os.open(temp/f'reviewer-{i}.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(packet,stream,ensure_ascii=False,indent=2);stream.write('\n')
        with (temp/'manifest.json').open('x',encoding='utf-8') as stream:json.dump({'format':'ac1-extraction-review-manifest-v1','source_hashes':hashes,'human_decisions_created':False},stream,ensure_ascii=False,indent=2);stream.write('\n')
        os.chmod(temp/'manifest.json',0o600);os.rename(temp,a.output_dir)
    except BaseException:
        shutil.rmtree(temp,ignore_errors=True);raise
    print(json.dumps({'histories':len(packets[0]['histories']),'reviewer_packets':2,'human_decisions_created':False,'model_called':False}))

if __name__=='__main__':main()
