"""Replace only noncanonical recovery runs; never edit their saved evidence."""
import json,subprocess,urllib.request
from pathlib import Path
D=Path(__file__).resolve().parents[1]/'artifacts/local/phase4-20261027';p=D/'B-live.json';b=json.loads(p.read_text());assert b['status']=='complete_automatic_collection'
def api(path):
 with urllib.request.urlopen('http://127.0.0.1:8000/api/v1'+path) as r:return json.load(r)
def sig(r):return sorted((t['dimension'],t['prompt'],t['expected_behavior'],tuple(sorted(t['supporting_memory_ids']))) for t in r['tests'])
for h in b['scenarios']:
 canonical=sig(h['runs'][0])
 for i,r in enumerate(h['runs']):
  if sig(r)==canonical:continue
  source=next(x for x in h['runs'] if x['strategy']==r['strategy'] and sig(x)==canonical and x.get('result'))
  output=subprocess.run(['docker','compose','exec','-T','backend','python','/scripts/fork_phase4_condition.py',source['run_id']],check=True,capture_output=True,text=True)
  fork=json.loads(output.stdout);rid=fork['runs'][0]['run_id'];new={'run_id':rid,'strategy':r['strategy'],'repetition':r['repetition'],'configuration':api('/audits/'+rid),'tests':api('/audits/'+rid+'/tests'),'recovery_provenance':{'original_run_id':r['run_id'],'copied_from_run_id':source['run_id'],'reason':'New-group deterministic regeneration chose a different accuracy slot. Original noncanonical run excluded; exact-suite application fork used instead.'}}
  assert sig(new)==canonical
  h.setdefault('excluded_noncanonical_runs',[]).append(r);h['runs'][i]=new;p.write_text(json.dumps(b,indent=2))
b['status']='collecting';p.write_text(json.dumps(b,indent=2))
