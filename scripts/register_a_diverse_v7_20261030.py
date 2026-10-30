"""Fork a consistent A campaign from completed v2 source audits; no target calls."""
import json,hashlib,os
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/experiment-a-expanded-20261030'
source_path=OUT/'four-scenario-v2-source-ledger.json'; target=OUT/'four-scenario-v7-source-ledger.json'
source=json.loads(source_path.read_text());state=json.loads(target.read_text()) if target.exists() else {'campaign_id':'diverse-a-20261030-v7','source_sha256':source['source_sha256'],'histories':{}}
def save():
 p=target.with_suffix('.tmp');p.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');os.replace(p,target)
for hid,old in source['histories'].items():
 if old.get('status')!='prepared_inventory_not_frozen':raise SystemExit(f'{hid}: source incomplete')
 row=state['histories'].setdefault(hid,{'history_id':hid,'conversation_id':old['conversation_id'],'memory_ids':old['memory_ids'],'source_run_id':old['source_run_id'],'operations':{}});save()
 body={'campaign_id':state['campaign_id'],'scenario_id':hid,'planned_scenarios':4}
 key='campaign-register';prior=row['operations'].get(key)
 if prior:
  if prior['status']!='returned':raise SystemExit(f'{hid}: reconcile previous request before retry')
  continue
 row['operations'][key]={'status':'dispatched','body':body};save()
 request=Request('http://127.0.0.1:8000/api/v1/audits/'+old['source_run_id']+'/method-comparison',method='POST',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:
  with urlopen(request,timeout=300) as response:result=json.load(response)
 except HTTPError as e:
  row['operations'][key].update(status='http_error',code=e.code,error=e.read().decode());save();raise
 except Exception:
  row['operations'][key]['status']='ambiguous';save();raise
 row['operations'][key].update(status='returned',response=result);row['comparison_id']=result['comparison_id'];row['status']='prepared_inventory_not_frozen';save();print(hid,'registered',flush=True)
print('New campaign registered from four retained completed source audits; no target calls.')
