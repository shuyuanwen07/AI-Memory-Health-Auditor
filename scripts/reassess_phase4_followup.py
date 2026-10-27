"""Current evaluator on exact historical answers, via immutable reassessment API."""
import argparse,hashlib,json,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=ROOT/'artifacts/local/phase4-20261027/A-live.json');p.add_argument('--output-dir',type=Path,default=ROOT/'artifacts/local/phase4-followup-20261027');args=p.parse_args();original=args.source;D=args.output_dir;D.mkdir(parents=True,exist_ok=True);out=D/'saved-answer-reassessment.json'
a=json.loads(original.read_text());state=json.loads(out.read_text()) if out.exists() else {'scope':'Development-only same-answer classification comparison; not a new independent target experiment','source_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'runs':[],'events':[],'new_target_calls':0}
def save():out.write_text(json.dumps(state,indent=2))
def api(method,path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8000/api/v1'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
 try:
  with urllib.request.urlopen(req,timeout=300) as response:data=json.load(response)
 except urllib.error.HTTPError as e:state['events'].append({'path':path,'status':e.code,'error':e.read().decode()});save();raise
 state['events'].append({'method':method,'path':path,'response':data});save();return data
for h in a['scenarios']:
 for source in h['runs']:
  row=next((r for r in state['runs'] if r['source_run_id']==source['run_id']),None)
  if row is None:
   config=api('POST','/audits/'+source['run_id']+'/reassessment',{'evaluator_provider':'rule_based'});row={'source_run_id':source['run_id'],'run_id':config['run_id'],'configuration':config,'history':h['scenario_id'],'method':source.get('label',source.get('strategy'))};state['runs'].append(row);save()
  if 'evaluations' not in row:row['evaluations']=api('POST','/audits/'+row['run_id']+'/evaluate');save()
  row['result']=api('GET','/audits/'+row['run_id']+'/results');row['tests']=api('GET','/audits/'+row['run_id']+'/tests');save()
  by_answer={x['response']['execution_metadata']['shared_source_response_id']:x for x in row['result']['answers']}
  assert set(by_answer)=={r['response_id'] for r in source['responses']}
  for old in source['responses']:
   now=by_answer[old['response_id']]['response'];assert now['response_text']==old['response_text'];assert now['execution_metadata']['request_attempts']==0
  old_verdicts={e['response_id']:e['passed'] for e in source['evaluations']}
  assert all(x['evaluation']['passed']==old_verdicts[key] for key,x in by_answer.items()),'Verdict drift; retain as separate result and inspect before claims'
  print('Verified exact answers and unchanged verdicts:',h['scenario_id'],source.get('label',source.get('strategy')),flush=True)
state['status']='complete';save();print('All saved answers reassessed, no new target requests.')
