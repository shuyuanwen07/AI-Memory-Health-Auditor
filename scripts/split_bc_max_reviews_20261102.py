"""Format completed MAX reviews into immutable batch identities, without regrading."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'output/proposal-delivery/bc-reader-retest-20261101-v2'


def read(path):return json.loads(path.read_text())


def main():
    for slot in (1,2):
        for sid,folder,pattern in [('B','B/blind-review','compact-batch-*.json'),('C','C/compact-review','batch-*.json')]:
            origin=BASE/f'review-max/reviewer-{slot}/{sid}-all.review.json'
            full=read(origin)
            byid={x['review_id']:x for x in full['items']}
            if len(full['items'])!=192 or len(byid)!=192:raise ValueError('MAX review must cover192unique answers')
            seen=set()
            for pack in sorted((BASE/folder).glob(pattern)):
                if '.private-key.' in pack.name:continue
                source=read(pack)
                ids=[x['review_id'] for x in source['items']]
                if any(rid not in byid or rid in seen for rid in ids):raise ValueError('Batch IDs do not partition MAX review')
                seen.update(ids)
                number=pack.stem.split('-')[-1]
                result={k:v for k,v in full.items() if k!='items'}
                result.update(items=[byid[rid] for rid in ids],origin_review_sha256=hashlib.sha256(origin.read_bytes()).hexdigest(),
                    material_sha256=hashlib.sha256(pack.read_bytes()).hexdigest(),reviewer_kind='ai',review_model='gpt-6-astra',
                    review_reasoning_effort='max',completed_by_human=False,human_confirmation_pending=True)
                target=BASE/f'review-max/reviewer-{slot}/{sid}-batch-{number}.review.json'
                target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            if seen!=set(byid):raise ValueError('Missing MAX review handles')
    print('Both MAX reviewers cover all384 B/C answers; batch formatting did not change any judgment.')


if __name__=='__main__':main()
