"""Create blank source-and-edge reviews for the authored synthetic reference."""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'output/proposal-delivery/ac2-four-dimension-new-source-20261029-v1'

def main():
    raw=(RUN/'sources.json').read_bytes();source=json.loads(raw);protocol=json.loads((RUN/'protocol.json').read_text())
    assert hashlib.sha256(raw).hexdigest()==protocol['source_sha256'] and len(source['histories'])==8
    histories=[]
    for h in source['histories']:
        facts=[{'id':f"{h['id']}-M{i+1}",'text':text,'source_support':None,'reason':''} for i,text in enumerate(h['texts'])]
        edges=[{'source_id':facts[e['source']]['id'],'target_id':facts[e['target']]['id'],'claimed_relation':e['type'],
                'relation_validity':None,'reason':''} for e in h['edges']]
        histories.append({'history_id':h['id'],'source_messages':[{'id':f['id'],'text':f['text']} for f in facts],
                          'facts':facts,'relationships':edges})
    out=RUN/'source-review';out.mkdir(exist_ok=False)
    for reviewer in (1,2):
        result={'reviewer':f'reviewer-{reviewer}','completed_by_human':None,'independent_review':None,
                'source_sha256':protocol['source_sha256'],
                'instructions':'逐条判断事实是否由对应原文支持，以及标出的关系是否符合原文。填写 valid、invalid 或 uncertain，并说明。来源为合成材料，模拟确认不代表人工审核。',
                'histories':histories}
        (out/f'reviewer-{reviewer}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    with ZipFile(out/'四维来源与关系-双人审核.zip','w',ZIP_DEFLATED) as archive:
        for reviewer in (1,2):archive.write(out/f'reviewer-{reviewer}.json',f'reviewer-{reviewer}.json')
    print(f"Prepared {len(histories)} histories, {sum(len(h['facts']) for h in histories)} facts and {sum(len(h['relationships']) for h in histories)} relations per reviewer.")

if __name__=='__main__':main()
