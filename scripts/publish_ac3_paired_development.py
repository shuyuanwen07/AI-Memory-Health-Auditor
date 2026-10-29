"""Publish only aggregate paired counts, preserving retrospective status."""
import hashlib
import json
from pathlib import Path


def publish(source, destination):
    raw = source.read_bytes()
    data = json.loads(raw)
    if (data.get('format') != 'ac3-category-error-diagnosis-v1'
            or data.get('status') != 'retrospective development analysis only'
            or data.get('cases') != 120
            or data.get('run_sha256') != '46c3670eafb67a2f6e3a5e40b08e5a6fa2f126a7cbd5e1aad14752c389eafdb1'):
        raise ValueError('Expected the bound 120-answer development analysis')
    pairs = data['paired_verdict_transitions']
    def count(condition, human, old, new):
        return sum(r['count'] for r in pairs[condition]
                   if (r['reference'],r['original'],r['candidate']) == (human,old,new))
    for condition in ('hybrid', 'provider_only'):
        if sum(row['count'] for row in pairs[condition]) != 120:
            raise ValueError('Incomplete paired outcomes')
    # Include both changed passes and abstentions: each means something different.
    rows = [
        {'name':'False positives corrected', 'hybrid':count('hybrid','pass','fail','pass'), 'provider':count('provider_only','pass','fail','pass')},
        {'name':'False positives → uncertain', 'hybrid':count('hybrid','pass','fail','uncertain'), 'provider':count('provider_only','pass','fail','uncertain')},
        {'name':'Failures newly detected', 'hybrid':sum(count('hybrid','fail',old,'fail') for old in ('pass','uncertain')), 'provider':sum(count('provider_only','fail',old,'fail') for old in ('pass','uncertain'))},
        {'name':'Detected failures → pass', 'hybrid':count('hybrid','fail','fail','pass'), 'provider':count('provider_only','fail','fail','pass')},
        {'name':'Detected failures → uncertain', 'hybrid':count('hybrid','fail','fail','uncertain'), 'provider':count('provider_only','fail','fail','uncertain')},
    ]
    output={'format':'ac3-paired-development-public-v1','source_sha256':hashlib.sha256(raw).hexdigest(),
            'run_sha256':data['run_sha256'],'cases':120,'independent_retest':False,'rows':rows}
    with destination.open('x',encoding='utf-8') as file:
        json.dump(output,file,indent=2,ensure_ascii=False);file.write('\n')


if __name__ == '__main__':
    publish(Path('output/proposal-delivery/ac3-paired-development-diagnosis-2026-10-29.json'),
            Path('frontend/public/reports/ac3-paired-development-v1.json'))
