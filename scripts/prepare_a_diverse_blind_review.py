"""Prepare blinded, explicitly AI-reviewed question packets for exploratory A."""
import hashlib
import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/proposal-delivery/experiment-a-diverse-candidate-20261029-v1'

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

def main():
    draft_bytes = (OUT / 'generated-draft.json').read_bytes()
    draft = json.loads(draft_bytes); protocol = json.loads((OUT / 'protocol.json').read_bytes())
    if draft['protocol_sha256'] != hashlib.sha256((OUT / 'protocol.json').read_bytes()).hexdigest():
        raise ValueError('Draft differs from frozen protocol')
    if [h['history_id'] for h in draft['histories']] != protocol['history_ids']:
        raise ValueError('Wrong source set')
    histories = [{'history_id': h['history_id'], 'source_messages': h['source_messages'],
                  'reference': h['reference']} for h in draft['histories']]
    questions=[]; mapping={}
    for h in draft['histories']:
        for arm, condition in h['arms'].items():
            for row in condition['tests']:
                item=row['test']; bid=secrets.token_hex(16)
                if bid in mapping: raise ValueError('Duplicate identity')
                questions.append({'blind_id':bid, 'history_id':h['history_id'], 'question':item['prompt'],
                    'expected_behavior':item['expected_behavior'], 'supporting_memory_ids':item['supporting_memory_ids'],
                    'dimension':item['dimension']})
                mapping[bid]={'history_id':h['history_id'], 'arm':arm, 'test_id':item['test_id'],
                              'automatic_quality':row['quality']}
    secrets.SystemRandom().shuffle(questions)
    material={'format':'a-diverse-question-material-v1','histories':histories,'questions':questions,
              'qualifications':protocol['source_qualifications']}
    digest=hashlib.sha256(canonical(material)).hexdigest()
    packet={'format':'a-diverse-ai-question-review-v1','material_sha256':digest,'reviewer_kind':'AI',
            'limitations':['Reviewer sees contextual/direct wording and may infer method; no method labels or gate scores supplied.',
                           'Source histories were used previously, not independent held-out data.',
                           'No human judgments or target responses exist in this packet.'],
            **material,'decisions':[{'blind_id':q['blind_id'],'grounded':None,'executable':None,'reason':''} for q in questions]}
    # Ensure the public packet format remains distinct from the material format.
    packet['format']='a-diverse-ai-question-review-v1'
    def write(path, value):
        with path.open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
    review = OUT / 'ai-review'; review.mkdir(exist_ok=False)
    for i in (1,2):
        write(review / f'ai-reviewer-{i}.json', {**packet, 'reviewer_slot':i})
    private = OUT / 'private'; private.mkdir(exist_ok=False)
    write(private / 'key.json', {'format':'a-diverse-review-key-v1','material_sha256':digest,
        'generated_draft_sha256':hashlib.sha256(draft_bytes).hexdigest(),'mapping':mapping})
    print(json.dumps({'histories':len(histories),'questions':len(questions),'human_labels_created':False}))

if __name__=='__main__':main()
