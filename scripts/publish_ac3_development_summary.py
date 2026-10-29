"""Publish source-bound aggregate development metrics, never human decisions."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'output/ac3-generated/AC3-taxonomy-judge-development-v1/aggregate-development.json'
OUTPUT=ROOT/'frontend/public/reports/ac3-taxonomy-development-v1.json'


def build(raw):
    data=json.loads(raw)
    if (data.get('format')!='ac3-taxonomy-development-only-v1'
            or data.get('source_frozen_sha256')!='ec20077e07ead83925fa38bb67936d81773098e0762c1e4627ae3b94d8ff0f58'
            or data.get('human_reference',{}).get('fail')!=80 or data['human_reference'].get('pass')!=40):
        raise ValueError('Unexpected development evidence')
    names=('failure_recall_conservative','classification_accuracy_conservative','decided_coverage','false_positive_rate_decided')
    conditions=[]
    for key,label in (('hybrid','Model + rule check'),('provider_only','Model judgment only')):
        metrics=data[key]['metrics']; parsed={}
        for name in names:
            item=metrics[name];n=item['numerator'];d=item['denominator']
            if type(n) is not int or type(d) is not int or d<=0 or n<0 or n>d or abs(item['value']-n/d)>1e-9:
                raise ValueError('Inconsistent development metric')
            parsed[name]={'numerator':n,'denominator':d,'percentage':round(100*n/d,1)}
        conditions.append({'id':key,'label':label,'metrics':parsed})
    return {'format':'ac3-taxonomy-development-public-v1','source_sha256':hashlib.sha256(raw).hexdigest(),
            'source_frozen_sha256':data['source_frozen_sha256'],'sample_size':120,'conditions':conditions,
            'independent_retest':False,'formal_acceptance_established':False,
            'limitations':['Previously observed answers were used in development; these are not independent validation results.',
                'Synthetic histories are related and not representative of a population.',
                'False positive rate uses decided human-pass cases; abstentions are excluded from its denominator.']}


if __name__=='__main__':
    output=build(SOURCE.read_bytes())
    OUTPUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Published development-only aggregate from existing saved evidence; no model called.')
