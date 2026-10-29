"""Check frozen A selection against two AI question reviews; never imply human approval."""
import collections
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / 'output/proposal-delivery/experiment-a-diverse-candidate-20261029-v1'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def canonical(obj): return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

def analyze():
    selection_path = STUDY / 'private/pairing-selection.json'; key_path = STUDY / 'private/key.json'
    addendum_path = STUDY / 'pairing-addendum.json'; draft_path = STUDY / 'generated-draft.json'
    first_path = STUDY / 'independent-ai-selected-ai-review-v5.json'
    second_path = STUDY / 'ai-review/ai-reviewer-2-completed.json'
    original_path = STUDY / 'ai-review/ai-reviewer-2.json'
    sel, key, add, first, second, original = map(read, [selection_path, key_path, addendum_path, first_path, second_path, original_path])
    if (sel['pairing_addendum_sha256'] != sha(addendum_path) or sel['private_key_sha256'] != sha(key_path)
            or add['generated_draft_sha256'] != sha(draft_path)
            or first['pairing_selection_sha256'] != sha(selection_path)):
        raise ValueError('Frozen selection, source or AI review binding mismatch')
    if (first.get('format') != 'a-diverse-selected-independent-ai-review-v5'
            or second.get('reviewer_kind') != 'AI' or second.get('reviewer_slot') != 2
            or any(second.get(x) != original.get(x) for x in ('histories','questions','qualifications'))):
        raise ValueError('Review type, slot or source material changed')
    material = {'format':'a-diverse-question-material-v1','histories':original['histories'],
                'questions':original['questions'],'qualifications':original['qualifications']}
    digest = hashlib.sha256(canonical(material)).hexdigest()
    if digest != first['material_sha256'] or digest != second['material_sha256'] or digest != key['material_sha256']:
        raise ValueError('Question material does not match frozen review')
    questions = {q['blind_id']:q for q in original['questions']}; mapping = key['mapping']
    if len(questions) != 348 or set(questions) != set(mapping): raise ValueError('Question set incomplete')
    choices = sel['selected_triplets']; selected = [bid for t in choices for bid in t['blind_ids_by_arm'].values()]
    if len(choices) != 107 or len(selected) != 321 or len(set(selected)) != 321 or set(selected)-set(questions):
        raise ValueError('Frozen selected triplets not unique or complete')
    r1 = {q['blind_id']:q for q in first['items']}; r2 = {q['blind_id']:q for q in second['decisions']}
    if len(first['items']) != 321 or set(r1) != set(selected) or len(second['decisions']) != 348 or set(r2) != set(questions):
        raise ValueError('Review decisions missing or repeated')
    allowed={'valid','invalid','uncertain'}
    for bid in selected:
        q=questions[bid]; x=r1[bid]; y=r2[bid]; meta=mapping[bid]
        if (x['history_id'] != q['history_id'] or x['dimension'] != q['dimension'] or x['method'] != meta['arm']
                or x['question'] != q['question'] or x['expected_behavior'] != q['expected_behavior']
                or x['review_kind'] != 'independent AI only' or x['human_review'] != 'pending'
                or x['grounded'] not in allowed or x['structurally_executable'] not in allowed
                or y['grounded'] not in allowed or y['executable'] not in allowed):
            raise ValueError('AI review changed question, metadata or judgment')
    outcomes=[]; dims=collections.Counter(); histories=collections.Counter(); rejecting=collections.Counter()
    for t in choices:
        parts=[]
        for arm, bid in t['blind_ids_by_arm'].items():
            q=questions[bid]; x=r1[bid]; y=r2[bid]
            if (q['history_id'] != t['history_id'] or q['dimension'] != t['dimension'] or mapping[bid]['arm'] != arm):
                raise ValueError('Selected triplet identity mismatch')
            valid = x['grounded']=='valid' and x['structurally_executable']=='valid' and y['grounded']=='valid' and y['executable']=='valid'
            if not valid: rejecting[arm]+=1
            parts.append({'arm':arm,'blind_id':bid,'both_ai_valid':valid,
                'reviewer_1':{'grounded':x['grounded'],'executable':x['structurally_executable'],'reason':x['reason']},
                'reviewer_2':{'grounded':y['grounded'],'executable':y['executable'],'reason':y['reason']}})
        accepted=all(p['both_ai_valid'] for p in parts);dims[(t['dimension'], 'retained' if accepted else 'excluded')]+=1
        if accepted: histories[t['history_id']]+=1
        outcomes.append({'history_id':t['history_id'],'dimension':t['dimension'],'retained':accepted,'parts':parts})
    distribution={d:{k:dims[(d,k)] for k in ('retained','excluded')}
                  for d in ('accuracy','freshness','conflict_resolution','appropriate_use')}
    return {'format':'a-diverse-ai-readiness-v1','review_type':'two AI reviews, not human validation',
        'source_hashes':{'selection':sha(selection_path),'first_review':sha(first_path),'second_review':sha(second_path),'material_sha256':digest},
        'selected_triplets':len(choices),'selected_questions':len(selected),'retained_triplets':sum(histories.values()),
        'retained_questions':3*sum(histories.values()),'retained_histories':len(histories),
        'dimension_distribution':distribution,'excluded_triplet_members_by_arm':dict(rejecting),
        'supports_four_dimension_comparison':all(distribution[d]['retained'] > 0 for d in distribution),
        'outcomes':outcomes,'limitations':['Question validity labels are from two AI reviewers; human review remains pending.',
          'First reviewer had method labels; reviewer 2 could infer method from phrasing.',
          'Previously observed, related synthetic histories are not an independent population sample.',
          'No target responses or reviewed actual-defect inventory are created by this analysis.']}

if __name__=='__main__':
    result=analyze();out=STUDY/'ai-readiness-summary.json'
    with out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:result[k] for k in ('selected_triplets','retained_triplets','retained_histories','dimension_distribution','supports_four_dimension_comparison')}))
