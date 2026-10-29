"""Analyze a frozen, blinded semantic pilot without altering original human labels."""
import hashlib,json,pathlib,collections
R=pathlib.Path(__file__).resolve().parents[1]; out=R/'output/ac3-generated/semantic-scope-pilot-20261029-v1'
def sha(x):return hashlib.sha256(x).hexdigest()
def can(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
protocol=json.loads((out/'protocol.json').read_bytes()); raw=(out/'inputs.json').read_bytes();assert sha(raw)==protocol['inputs_sha256']; inputs=json.loads(raw);assert len(inputs)==33
source=R/'output/proposal-delivery/ac2-source-supplement-paired-20261029-v1/private/material.json';assert sha(source.read_bytes())==protocol['source_material_sha256'];m=json.loads(source.read_bytes());hist={h['history_id']:h['source_messages'] for h in m['histories']};q={v['blind_id']:v for v in m['questions']};assert len(q)==33
paths=[R/f'output/proposal-delivery/ac2-source-supplement-review-return-20261029-v1/user-confirmed/reviewer-{i}.json' for i in (1,2)];confpath=paths[0].parent/'confirmation.json';conf=json.loads(confpath.read_bytes());assert conf['confirmed_by']=='user' and conf['completed_by_humans'] is True and conf['review_sha256']==[sha(p.read_bytes()) for p in paths]
tables=[]
for p in paths:
 d=json.loads(p.read_bytes());assert d['reviewer_declaration']['completed_independently'] is True; t={x['blind_id']:x for x in d['decisions']};assert set(t)==set(q);tables.append(t)
reconpath=R/'output/proposal-delivery/ac2-source-supplement-review-return-20261029-v1/product-v3-pilot-reconstruction-v2.json';recon=json.loads(reconpath.read_bytes());base={x['blind_id']:x for x in recon['items']};assert set(base)==set(q)
counts=collections.Counter();statuses=collections.Counter();usage=collections.Counter();rows=[];verified=[]
for item in inputs:
 bid=item['blind_id'];expected={'source_messages':hist[q[bid]['history_id']],'question':q[bid]['prompt'],'expected_behavior':q[bid]['expected_behavior']};assert item['input']==expected and item['input_sha256']==sha(can(expected))
 fp=out/'responses'/f'{bid}.json';record=json.loads(fp.read_bytes());assert record['blind_id']==bid and record['input_sha256']==item['input_sha256'];assert (out/'requests'/f'{bid}.json').is_file();assert record['verdict'] in ('valid','invalid','uncertain');statuses[record['status']]+=1
 a,b=[table[bid] for table in tables]; hv='unresolved' if (a['grounded']!=b['grounded'] or a['structurally_executable']!=b['structurally_executable'] or 'uncertain' in (a['grounded'],a['structurally_executable'],b['grounded'],b['structurally_executable'])) else ('valid' if a['grounded']==a['structurally_executable']=='valid' else 'invalid');assert hv==base[bid]['human_consensus']
 counts[f'{hv}_model_{record["verdict"]}']+=1
 for k in ('prompt_tokens','completion_tokens','total_tokens','cost'):
  v=record.get('provider_response',{}).get('usage',{}).get(k)
  if v is not None:usage[k]+=v
 rows.append({'blind_id':bid,'human_consensus':hv,'model_verdict':record['verdict'],'model_status':record['status'],'existing_v3_disposition':base[bid]['v3_after_scope_review']});verified.append({'blind_id':bid,'response_sha256':sha(fp.read_bytes())})
ratio=lambda n,d:{'numerator':n,'denominator':d,'value':n/d if d else None}
assert len(rows)==33
valid=sum(v for k,v in counts.items() if k.startswith('valid_model_'));invalid=sum(v for k,v in counts.items() if k.startswith('invalid_model_'))
result={'format':'ac2-semantic-scope-pilot-result-v1','protocol_sha256':sha((out/'protocol.json').read_bytes()),'inputs_sha256':sha(raw),'review_confirmation_sha256':sha(confpath.read_bytes()),'human_review_sha256':[sha(p.read_bytes()) for p in paths],'baseline_reconstruction_sha256':sha(reconpath.read_bytes()),'model':'openai/gpt-6-luna','count':33,'provider_statuses':dict(statuses),'human_consensus_counts':{'valid':valid,'invalid':invalid,'unresolved':len(rows)-valid-invalid},'confusion':dict(counts),'invalid_detection_including_uncertain_as_miss':ratio(counts['invalid_model_invalid'],invalid),'valid_questions_marked_invalid_all':ratio(counts['valid_model_invalid'],valid),'valid_model_accepted':ratio(counts['valid_model_valid'],valid),'v3_pending_human_valid_model_valid':sum(1 for x in rows if x['human_consensus']=='valid' and x['existing_v3_disposition']=='pending' and x['model_verdict']=='valid'),'v3_pending_human_valid_total':sum(1 for x in rows if x['human_consensus']=='valid' and x['existing_v3_disposition']=='pending'),'provider_usage':dict(usage),'usage_note':'Provider reported token usage/cost; not reconciled to account bill. No automatic retries.','rows':rows,'response_hashes':verified,'limitations':['Human unresolved items are excluded from primary rates, not silently resolved.','A 10-history nonrandom synthetic pilot; repeated questions and shared histories are correlated.','This prompt was designed after the team observed earlier aggregate outcomes; not a prospective independent whole-system validation.','Four transport/parsing failures are conservatively uncertain; this is a standalone model test, not a production deployment.','Existing rule already rejected every human-consensus-invalid question in this 33-question pilot, so the apparent hybrid can demonstrate no incremental error detection here.']}
p=out/'analysis.json'
with p.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({k:result[k] for k in ('provider_statuses','human_consensus_counts','confusion','invalid_detection_including_uncertain_as_miss','valid_questions_marked_invalid_all','v3_pending_human_valid_model_valid','v3_pending_human_valid_total','provider_usage')},ensure_ascii=False))
