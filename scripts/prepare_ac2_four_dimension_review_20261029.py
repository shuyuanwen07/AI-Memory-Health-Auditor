"""Prepare two blind source reviews after the frozen feasibility study finishes."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'output/proposal-delivery/ac2-four-dimension-new-source-20261029-v1'

def main():
    ledger_bytes=(RUN/'ledger.json').read_bytes(); ledger=json.loads(ledger_bytes)
    protocol=(RUN/'protocol.json').read_bytes()
    assert ledger['protocol_sha256']==hashlib.sha256(protocol).hexdigest()
    assert 'finished_at_utc' in ledger and len(ledger['histories'])==8
    items=[];failed=[];private={}
    for history in ledger['histories']:
        if history['state']!='completed':
            failed.append({'history_id':history['id'],'state':history['state'],'error':history.get('error')});continue
        requests=history['requests']
        created=next(r['body']['messages'] for r in requests if r['path']=='/conversations' and r['state']=='returned')
        messages=[{'source_id':m['message_id'],'role':m['role'],'text':m['content'],'timestamp':m['timestamp']} for m in created]
        memory_calls=[r for r in requests if r['path']=='/memories' and r['state']=='returned']
        memories={r['response']['memory_id']:r['body'] for r in memory_calls}
        tests=next(r['response']['tests'] for r in requests if r['path'].endswith('/test-review') and r['state']=='returned')
        for test in tests:
            assert all(mid in memories for mid in test['supporting_memory_ids'])
            ident=f'Q{len(items)+1:03}'
            items.append({'review_item_id':ident,'history_id':history['id'],'dimension':test['dimension'],'source_messages':messages,
                          'cited_facts':[{'fact':memories[mid]['canonical_value'],'source_message_ids':memories[mid]['source_message_ids']} for mid in test['supporting_memory_ids']],
                          'question':test['prompt'],'reference_answer':test['expected_behavior'],
                          'review':{'source_support':'','question_clarity':'','reference_answer_correctness':'','overall':'','notes':''}})
            private[ident]={'test_id':test['test_id'],'run_id':history['run_id'],'automated_quality_status':test['quality_status']}
    out=RUN/'blind-review';out.mkdir(exist_ok=False)
    def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    ledger_hash=hashlib.sha256(ledger_bytes).hexdigest()
    for reviewer in (1,2):
        write(out/f'reviewer-{reviewer}.json',{'reviewer_id':f'reviewer-{reviewer}','completed_by_human':None,'independent_review':None,
              'reviewed_without_other_review':None,'reviewed_without_system_quality_feedback':None,'source_ledger_sha256':ledger_hash,
              'instructions':'Use valid, invalid or uncertain and explain; check every source message. Candidate memories and relations were authored for a synthetic study and have not been independently human verified.','items':items})
    write(out/'private-mapping.json',{'ledger_sha256':ledger_hash,'items':private})
    write(out/'failed-histories.json',failed)
    with ZipFile(out/'双人审核-四维题目.zip','w',ZIP_DEFLATED) as archive:
        for filename in ('reviewer-1.json','reviewer-2.json','failed-histories.json'):
            archive.write(out/filename,filename)
    print(json.dumps({'questions':len(items),'dimensions':dict(Counter(item['dimension'] for item in items)), 'failed_histories':len(failed)}))

if __name__=='__main__':main()
