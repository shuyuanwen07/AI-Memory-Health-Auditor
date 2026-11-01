"""Blind quality scores when reviewing new questions from the repair retest."""
import hashlib,json,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/ac2-astra-generation-repair-retest-20261101-v1'
summary=json.loads((OUT/'summary.json').read_text())
source=json.loads((ROOT/'output/proposal-delivery/ac2-prospective-new-histories-20261029/histories.json').read_text())
sources={x['conversation_id']:x['messages'] for x in source['conversations']};items=[]
for run in summary['runs']:
    path=OUT/(run['history_id']+'.json');raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=run['sha256']:raise SystemExit('Changed run record')
    data=json.loads(raw)
    for call in data['requests']:
        if call['path'].endswith('/generate-tests') and call['status']=='returned':
            for t in call['response']:
                items.append({'history_id':run['history_id'],'test_id':t['test_id'],'source_messages':sources[run['history_id']],
                    'dimension':t['dimension'],'question':t['prompt'],'expected_behavior':t['expected_behavior'],
                    'source_grounding':'','question_executability':'','reference_answer_validity':'','review_note':''})
if not items:raise SystemExit('No questions generated')
random.Random(20261105).shuffle(items)
for n in (1,2):
    dest=OUT/f'question-ai-reviewer-{n}-blank.json'
    if dest.exists():raise SystemExit('Existing packet retained')
    dest.write_text(json.dumps({'reviewer':f'ai-reviewer-{n}','scope':'AI source-based review; automated quality scores omitted','items':items},ensure_ascii=False,indent=2)+'\n')
print('Prepared',len(items),'questions')
