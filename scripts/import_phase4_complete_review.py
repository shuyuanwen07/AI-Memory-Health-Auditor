"""Import validated real returns via normal API. No target/model calls.

Blank, AI-assisted, exposed or unresolved returns are refused for formal import.
"""
import argparse,hashlib,json,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase4_formal_review import analyse

def plan_import(material,key,reviews):
 report=analyse(material,key,reviews)
 if not report['formal_ready']:raise ValueError('Formal import not eligible: inspect unresolved items, mapping, fact inventory and exposure declarations. No writes performed.')
 operations=[];mappings={}
 binding=hashlib.sha256(json.dumps(reviews,sort_keys=True).encode()).hexdigest()
 for ident,item in material['items'].items():
  if item['kind']!='response':continue
  info=key['items'][ident]
  for review in reviews:
   label=review['labels'][ident];body={'human_passed':label['verdict']=='pass','human_failure_type':label['failure_dimension'] if label['verdict']=='fail' and label['failure_dimension']!='unclassified' else None,'reviewer_label':review['reviewer_id'].strip(),'review_role':'independent','note':('Actual human worksheet; independent/unexposed/no-AI declarations; return='+binding+'; sources='+','.join(label['source_message_ids'])+'; '+label.get('note',''))[:1500]}
   destinations=[(info['current_run_id'],info['current_evaluation_id'])]
   if item['study']=='A':destinations.append((info['source_run_id'],info['source_evaluation_id']))
   for run,evaluation in destinations:operations.append({'method':'PATCH','path':'/audits/'+run+'/evaluations/'+evaluation+'/review','body':body})
  if item['study']=='A':
   entry=mappings.setdefault(info['source_run_id'],{'schema_version':'mha-experiment-a-discovery-map-v1','comparison_id':info['comparison_id'],'inventory_fingerprint_sha256':info['inventory_fingerprint_sha256'],'mapping_release_id':'actual-review-'+binding[:24],'reviewer_pseudonym':reviews[0]['reviewer_id'].strip(),'completed_by_human':True,'entries':[]})
   entry['entries'].append({'response_id':info['source_response_id'],'test_id':info['source_test_id'],'defect_ids':reviews[0]['labels'][ident]['defect_ids']})
 for run,body in mappings.items():
  body['entries'].sort(key=lambda x:x['response_id']);operations.append({'method':'POST','path':'/audits/'+run+'/method-comparison-discovery-mapping','body':body})
 return report,operations

def main():
 p=argparse.ArgumentParser();p.add_argument('bundle',type=Path);p.add_argument('reviewer1',type=Path);p.add_argument('reviewer2',type=Path);p.add_argument('output',type=Path);p.add_argument('--apply-api',action='store_true');a=p.parse_args()
 if a.output.exists():raise SystemExit('Refuse to overwrite prior import receipt')
 key=json.loads((a.bundle/'private/key.json').read_text());material=json.loads((a.bundle/'private/material.json').read_text());reviews=[json.loads(x.read_text()) for x in [a.reviewer1,a.reviewer2]];report,operations=plan_import(material,key,reviews)
 result={'analysis':report,'planned_operations':operations,'applied':[],'server_import_performed':False}
 def save():a.output.write_text(json.dumps(result,indent=2))
 def api(method,path,body=None):
  req=urllib.request.Request('http://127.0.0.1:8000/api/v1'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
  with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)
 save()
 if not a.apply_api:print('Validated import plan saved; no server mutation.');return
 # Verify every exact current/source answer and assessment before any write.
 cache={}
 for ident,item in material['items'].items():
  if item['kind']!='response':continue
  info=key['items'][ident]
  destinations=[(info['current_run_id'],info['current_response_id'],info['current_evaluation_id'])]
  if item['study']=='A':destinations.append((info['source_run_id'],info['source_response_id'],info['source_evaluation_id']))
  for run,response,evaluation in destinations:
   if run not in cache:cache[run]=api('GET','/audits/'+run+'/evaluation-review')
   actual=next((x for x in cache[run] if x['response']['response_id']==response and x['automated']['evaluation_id']==evaluation),None)
   if actual is None or hashlib.sha256(actual['response']['response_text'].encode()).hexdigest()!=info['answer_sha256'] or actual['test']['prompt']!=item['question']:raise ValueError('Saved answer or question no longer matches frozen review material; no writes performed')
   for old in actual.get('human_reviews',[]):
    for r in reviews:
     if old['reviewer_label'].strip().casefold()==r['reviewer_id'].strip().casefold() and (old['human_passed']!=(r['labels'][ident]['verdict']=='pass') or old.get('human_failure_type')!=(r['labels'][ident]['failure_dimension'] if r['labels'][ident]['verdict']=='fail' and r['labels'][ident]['failure_dimension']!='unclassified' else None)):raise ValueError('Existing reviewer decision differs; explicit revision reconciliation required before writing')
 for op in operations:
  receipt=api(op['method'],op['path'],op['body']);result['applied'].append({'path':op['path'],'receipt':receipt});save()
 result['server_import_performed']=True;save();print('Actual independent labels and explicit mappings saved; no model call.')
if __name__=='__main__':main()
