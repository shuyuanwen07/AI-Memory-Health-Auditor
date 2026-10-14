"""Database-free diagnostic probe on SHA-approved saved synthetic API cases."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.extraction.llm import PipelineLLMClient
from app.diagnostics.post_run_agent import PostRunDiagnosticAgent
from smoke_qwen_generation import approved_memories
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--output-limit',type=int,default=1200)
args=parser.parse_args()
if not 256 <= args.output_limit <= 12000:
 parser.error("Output limit must be between 256 and 12000.")
_,source_hash=approved_memories(ROOT/'datasets/smoke/qwen-four-dimension-source-v1.json',ROOT/'datasets/smoke/qwen-four-dimension-approval-v1.json')
saved=json.loads(args.input.read_text())
if saved.get('scope')!='synthetic_isolated_api_e2e_engineering_only' or saved.get('source_sha256')!=source_hash or saved.get('research_evidence') is not False:
 raise ValueError('Requires the exact approved synthetic smoke receipt.')
run=saved['runs'][0]
cases=run['diagnosis']['cases']
inventory=saved['confirmation']['inventory']
class ProbeClient(PipelineLLMClient):
 def complete_json(self,**kwargs):
  kwargs['max_output_tokens']=args.output_limit
  return super().complete_json(**kwargs)
client=ProbeClient('openrouter','openai/gpt-6-luna')
agent=PostRunDiagnosticAgent(client)
evidence={c['test_id']:[{k:m.get(k) for k in ['memory_id','canonical_value','source_message_ids','confidence','relationships']} for m in inventory if m['memory_id'] in c['supporting_memory_ids']] for c in cases}
report={'scope':'synthetic_diagnostic_only_probe','research_evidence':False,'source_sha256':source_hash,'output_limit':args.output_limit,'database_writes':0}
try:
 report['result']=agent.analyse(cases,evidence)
 report['status']='completed'
except Exception as exc:
 report.update(status='failed',error_code=type(exc).__name__,error=getattr(exc,'detail',str(exc)))
finally:
 report['observation']=agent.last_observation
 report['execution']=client.last_execution
 args.output.parent.mkdir(parents=True,exist_ok=True)
 args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'error':report.get('error'),'execution':report['execution']}),flush=True)
