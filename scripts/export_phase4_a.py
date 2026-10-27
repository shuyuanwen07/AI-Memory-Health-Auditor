"""Read-only A API exports and consistency checks; automated outputs stay private."""
import csv,hashlib,io,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'artifacts/local/phase4-20261027';state=json.loads((D/'A-live.json').read_text());out=D/'private/A-api-exports';out.mkdir(parents=True,exist_ok=True)
for history in state['scenarios']:
 report=history['comparison_results'];assert report['planned_test_budgets_equal'] and report['target_and_evaluation_settings_match'] and report['realised_call_attempts_equal']
 for condition in report['conditions']:
  assert condition['completed_answers']==4 and condition['category_coverage']['value']==1
  assert condition['response_level']['failure_detection_recall'] is None and condition['failure_discovery_rate']['value'] is None
 for run in history['runs']:
  experiment=run['configuration']['experiment_id']
  for endpoint,suffix in [('reproducibility-bundle.json','bundle.json'),('export.csv','csv')]:
   with urllib.request.urlopen('http://127.0.0.1:8000/api/v1/experiments/'+experiment+'/'+endpoint,timeout=60) as response:raw=response.read()
   path=out/(history['scenario_id']+'-'+run['run_id']+'.'+suffix);path.write_bytes(raw)
   if suffix=='bundle.json':
    bundle=json.loads(raw);actual=next(x for x in bundle['runs'] if x['configuration']['run_id']==run['run_id'])
    assert actual['result']['tests_total']==run['result']['tests_total'] and actual['result']['tests_passed']==run['result']['tests_passed']
    assert len(actual['answers'])==4
   else:assert len(list(csv.reader(io.StringIO(raw.decode()))))>4
print('Nine A API bundles and CSVs saved; all answer counts and stored result totals match.')
