"""Make blank source-based review packets without leaking automatic judgments."""
import json, random, zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'output/proposal-delivery/ac2-astra-product-four-source-20261101-v1'
ledger=json.loads((OUT/'ledger.json').read_text())
if not ledger.get('finished_at_utc'):
    raise SystemExit('Generation has not finished; no review packet created.')
items=[]
for history in ledger['histories']:
    sources=next((r['body']['messages'] for r in history['requests'] if r['path']=='/conversations' and r['method']=='POST'),[])
    review=next((r['response'] for r in history['requests'] if r['path'].endswith('/test-review') and r['state']=='returned'),None)
    if not review: continue
    for test in review.get('tests',[]):
        items.append({'history_id':history['id'],'test_id':test['test_id'],'source_messages':sources,
                      'dimension':test['dimension'],'question':test['prompt'],'expected_behavior':test['expected_behavior'],
                      'source_grounding':'','question_executability':'','reference_answer_validity':'','review_note':''})
random.Random(20261101).shuffle(items)
instructions=('两位审核者分别独立对照原文检查题目和参考答案。三个字段填写 valid、invalid 或 uncertain，'
              '并在 review_note 说明依据。系统自动质量状态未提供；缺失的题目不当作有效题。')
for n in (1,2):
    (OUT/f'reviewer-{n}-blank.json').write_text(json.dumps({'reviewer':f'reviewer-{n}','instructions':instructions,'items':items},ensure_ascii=False,indent=2)+'\n')
(OUT/'审核说明.txt').write_text(instructions+'\n',encoding='utf8')
with zipfile.ZipFile(OUT/'AC2-系统内Astra-四场景-待人工审核.zip','w',zipfile.ZIP_DEFLATED) as z:
    for name in ('审核说明.txt','reviewer-1-blank.json','reviewer-2-blank.json'):z.write(OUT/name,name)
print('Review items:',len(items),'from',len({x['history_id'] for x in items}),'histories')
