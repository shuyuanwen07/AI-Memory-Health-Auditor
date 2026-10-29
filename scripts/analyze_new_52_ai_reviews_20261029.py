"""Verify and summarize two AI reviews; never treat them as human labels."""
import collections, hashlib, json, pathlib, shutil, sys, zipfile
root=pathlib.Path(__file__).resolve().parents[1]
zip_path=pathlib.Path(sys.argv[1])
orig=root/'output/proposal-delivery/new-audits-human-review-20261029'
out=root/'output/proposal-delivery/new-audits-ai-review-return-20261029'
out.mkdir(parents=True, exist_ok=False)
def sha(b):return hashlib.sha256(b).hexdigest()
def filehash(p):return sha(p.read_bytes())
with zipfile.ZipFile(zip_path) as z:
    manifest=json.loads(z.read('文件清单.json'))
    for v in manifest:
        if sha(z.read(v['path']))!=v['sha256']:raise ValueError('Manifest mismatch: '+v['path'])
    reviews=[json.loads(z.read(f'reviewer-{n}.json')) for n in (1,2)]
    for n,review in enumerate(reviews,1):
        old=json.loads((orig/f'reviewer-{n}.json').read_bytes())
        def content(items):
            ids=[x['review_id'] for x in items]
            if len(ids)!=52 or len(set(ids))!=52:raise ValueError('Review IDs missing or duplicated')
            return {x['review_id']:{k:v for k,v in x.items() if k!='review'} for x in items}
        if content(review['items'])!=content(old['items']) or review['sources']!=old['sources']:
            raise ValueError('Blind input changed')
        if review['review_metadata'].get('human') is not False:raise ValueError('Unexpected reviewer declaration')
        for row in review['items']:
            q=row['review'];v=q['question_validity'];a=q['answer_verdict']
            if v not in ('valid','invalid','uncertain') or a not in ('pass','fail','not_applicable','uncertain'):
                raise ValueError('Missing or unexpected review judgment')
    reviewer_hashes=[sha(z.read(f'reviewer-{n}.json')) for n in (1,2)]
    raw_disagreements=json.loads(z.read('分歧与待人工确认.json'))

mapping=json.loads((orig/'review-id-mapping.json').read_bytes())['mapping']
results_paths=[root/'output/proposal-delivery/large-single-audit-synthetic-16-20261029/result.json',*[root/f'output/proposal-delivery/exploratory-multi-history-{n}-20261029/result.json' for n in ('juniper','atlas','cedar','mistral')]]
answers={}
for path in results_paths:
    d=json.loads(path.read_bytes()); run=d['run_id']
    for a in d['result']['answers']:
        key=(run,a['test']['test_id'],a['response']['response_id'])
        if key in answers:raise ValueError('Duplicate original answer')
        answers[key]=a
left={x['review_id']:x for x in reviews[0]['items']};right={x['review_id']:x for x in reviews[1]['items']}
if set(left)!=set(right) or set(left)!=set(mapping) or len(answers)!=52:raise ValueError('Unexpected identity coverage')
summary=collections.Counter();dimensions=collections.defaultdict(collections.Counter);auto_compare=collections.Counter();disagreements=[];comparison=[]
for review_id,a in left.items():
    b=right[review_id];m=mapping[review_id];key=(m['run_id'],m['test_id'],m['response_id']); original=answers.get(key)
    if not original or a['question']!=original['test']['prompt'] or a['reference_behavior']!=original['test']['expected_behavior'] or a['model_answer']!=original['response']['response_text']:
        raise ValueError('Mismatch with original question/answer: '+review_id)
    l=a['review'];r=b['review'];pair=lambda v:(v['question_validity'],v['answer_verdict'])
    consensus=pair(l) if pair(l)==pair(r) else None
    status='disagreement' if consensus is None else '/'.join(consensus)
    summary[status]+=1;dimensions[a['ability']][status]+=1
    if consensus is None:
        disagreements.append({'review_id':review_id,'history':a['history'],'ability':a['ability'],'question':a['question'],'reference_behavior':a['reference_behavior'],'model_answer':a['model_answer'],'reviewer_1':l,'reviewer_2':r,'human_adjudication':None})
    if consensus and consensus[0]=='valid' and consensus[1] in ('pass','fail'):
        v=original['evaluation']['passed']; auto='pass' if v is True else 'fail' if v is False else 'uncertain'
        auto_compare[f'ai_{consensus[1]}_automatic_{auto}']+=1
        comparison.append({'review_id':review_id,'ai_consensus':consensus[1],'automatic_verdict':auto})
if len(disagreements)!=raw_disagreements['disagreement_count']:raise ValueError('Reported disagreement count mismatch')
result={'format':'new-audits-two-ai-review-summary-v1','zip_sha256':filehash(zip_path),'review_file_sha256':reviewer_hashes,'review_mapping_sha256':filehash(orig/'review-id-mapping.json'),'original_result_sha256':{str(p.relative_to(root)):filehash(p) for p in results_paths},'source_verification':'52 unique IDs; source histories, questions, expected behaviour, answers and cited memory evidence match original blank packages; mapped questions and answers match saved audit results.','reviewer_declarations':[r['review_metadata'] for r in reviews], 'provenance':'Two AI reviews as declared in received files; no human adjudication. Reviewer identity and independence are not independently verified. No assessment is treated as human ground truth.', 'consensus_counts':dict(summary),'by_ability':{k:dict(v) for k,v in dimensions.items()},'automatic_vs_ai_consensus':dict(auto_compare),'automatic_comparison_scope':'AI-consensus valid pass/fail items only; this compares two AI assessments, not accuracy against human ground truth. Automatic uncertain is retained.', 'remaining':'Four AI disagreements and two AI-consensus invalid questions require human review; additional human checking of all 52 is pending.', 'comparison':comparison}
for name,data in [('summary.json',result),('disagreements.json',{'format':'new-audits-two-ai-review-disagreements-v1','zip_sha256':filehash(zip_path),'items':disagreements,'note':'AI opinions, not human adjudications.'})]:
    (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
shutil.copy2(zip_path,out/'received-ai-reviews.zip')
print(json.dumps({'consensus':dict(summary),'automatic_comparison':dict(auto_compare),'disagreements':len(disagreements)},ensure_ascii=False))
