"""Import two independent blinded reviews of the AC2 reference-input generation run.

Reconstructs immutable review content from the exact frozen protocol and raw
outputs. Never writes a result for incomplete human reviews.
"""
import argparse,copy,hashlib,json,os,subprocess,sys,tempfile
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_ac1_extraction import read_regular

BLIND_INSTRUCTIONS=['请两人独立逐题审核，不查看对方判断。grounded 与 structurally_executable 填 valid、invalid 或 uncertain。','对 invalid 或 uncertain 写明理由；不修改题目或来源。','这些题来自人工确认记忆输入；审核材料不显示系统质量门禁评分。']
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp(value):
 d=datetime.fromisoformat(value.replace('Z','+00:00'))
 if d.tzinfo is None:raise ValueError('Timestamp must be timezone aware')
 return d

def verify_outputs(protocol,started,raw,corrected,protocol_sha,raw_sha):
 if (protocol.get('format')!='ac2-reference-generation-frozen-v1' or protocol.get('model_called') is not False or protocol.get('results_observed') is not False or
  started.get('format')!='ac2-reference-generation-started-v1' or started.get('model_called') is not False or started.get('protocol_sha256')!=protocol_sha or
  raw.get('format')!='ac2-reference-generation-output-v1' or raw.get('protocol_sha256')!=protocol_sha or raw.get('source_frozen_sha256')!=protocol.get('source_frozen_sha256') or raw.get('model_called') is not False or
  stamp(protocol['frozen_at_utc'])>=stamp(started['started_at_utc']) or stamp(started['started_at_utc'])>stamp(raw['finished_at_utc'])):
  raise ValueError('Protocol, run timestamps or raw output do not match.')
 expected=copy.deepcopy(raw)
 for h in expected['histories']:
  if h['status']=='failed':continue
  rejected=[t['test']['test_id'] for t in h['tests'] if t['quality_assessment']['quality_status'].lower()=='rejected']
  h['rejected_test_ids']=rejected;h['status']='rejected_by_product_gate' if rejected or h['suite_problem'] else ('empty' if not h['tests'] else 'completed')
 expected['correction']={'original_output_sha256':raw_sha,'description':'Offline correction: product quality_status is lowercase; recomputed gate status from preserved raw quality assessments. No generation repeated.'}
 if expected!=corrected:raise ValueError('Corrected output is not the exact derivation of the raw gate results.')
 if [h['history_id'] for h in raw['histories']]!=protocol['history_ids']:raise ValueError('Output history set differs from protocol.')

def blind(packet):
 packet=copy.deepcopy(packet);packet['instructions']=BLIND_INSTRUCTIONS
 for h in packet['histories']:
  h.pop('generation_status',None);h.pop('suite_problem',None)
  for item in h['generated_tests']:item.pop('product_quality_assessment',None)
 return packet

def aggregate(expected,reviews,gate_by_id):
 labels=[]
 for original,review in zip(expected,reviews):
  decl=review.get('reviewer_declaration',{});label=decl.get('reviewer_label')
  if (not isinstance(label,str) or not label.strip() or decl.get('completed_by_human') is not True or decl.get('completed_independently') is not True or type(decl.get('used_ai_assistance')) is not bool):
   raise ValueError('Each reviewer must declare human completion, independence, label and AI assistance.')
  labels.append(label.strip().casefold());clean=copy.deepcopy(review)
  for key in ('status','human_review_confirmation','ai_reviewer_declaration'):clean.pop(key,None)
  clean['reviewer_declaration']=original['reviewer_declaration']
  for h in clean.get('histories',[]):
   for t in h.get('generated_tests',[]):t['review']={'grounded':None,'structurally_executable':None,'note':''}
  if clean!=original:raise ValueError('Review altered question, source, reference, IDs, slot or blinding instructions.')
  for h in review['histories']:
   for t in h['generated_tests']:
    r=t['review']
    if (set(r)!={'grounded','structurally_executable','note'} or r['grounded'] not in ('valid','invalid','uncertain') or r['structurally_executable'] not in ('valid','invalid','uncertain') or not isinstance(r['note'],str) or
      ('uncertain' in (r['grounded'],r['structurally_executable']) or 'invalid' in (r['grounded'],r['structurally_executable'])) and not r['note'].strip()):raise ValueError('Incomplete or malformed human judgment.')
 if len(reviews)!=2 or len(expected)!=2 or labels[0]==labels[1]:raise ValueError('Two different independent human reviewer labels are required; identities are not authenticated.')
 counts={key:{'valid':0,'invalid':0,'unresolved':0,'denominator':0} for key in ('grounded','structurally_executable','joint')};unresolved=[];gate={}
 for h1,h2 in zip(reviews[0]['histories'],reviews[1]['histories']):
  for a,b in zip(h1['generated_tests'],h2['generated_tests']):
   r1,r2=a['review'],b['review']; outcomes={}
   for field in ('grounded','structurally_executable'):
    x,y=r1[field],r2[field];outcomes[field]=x if x==y and x!='uncertain' else 'unresolved'
   outcomes['joint']='valid' if all(outcomes[x]=='valid' for x in ('grounded','structurally_executable')) else ('invalid' if any(outcomes[x]=='invalid' for x in ('grounded','structurally_executable')) else 'unresolved')
   for field,outcome in outcomes.items():counts[field][outcome]+=1;counts[field]['denominator']+=1
   tid=a['test']['test_id'];g=gate_by_id[(h1['history_id'],tid)];gate.setdefault(g,{'valid':0,'invalid':0,'unresolved':0,'denominator':0});gate[g][outcomes['joint']]+=1;gate[g]['denominator']+=1
   if 'unresolved' in outcomes.values():unresolved.append({'history_id':h1['history_id'],'test_id':tid,'reviewer_1':r1,'reviewer_2':r2})
 for row in list(counts.values())+list(gate.values()):
  row['valid_rate_all']=row['valid']/row['denominator'] if row['denominator'] else None
  decided=row['valid']+row['invalid'];row['valid_rate_decided']=row['valid']/decided if decided else None;row['decided_denominator']=decided
 return {'format':'ac2-reference-generation-reviewed-summary-v1','reviewer_labels':[p['reviewer_declaration']['reviewer_label'] for p in reviews],
  'ai_assistance':[p['reviewer_declaration']['used_ai_assistance'] for p in reviews],'original_ai_declarations':[p.get('ai_reviewer_declaration') for p in reviews],'human_identity_note':'Independence and identity are self-reported, not independently authenticated.',
  'results':counts,'joint_by_product_gate':gate,'unresolved':unresolved,
  'limitations':['Human-reviewed memory inputs; not an evaluation of automatic extraction.','Generated questions are assessed for grounding and structural executability, not target responses.','Disagreements and uncertain labels are unresolved; both all-question and decided denominators are shown.','Histories are synthetic and not an independent random population.']}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('protocol','started','raw-output','corrected-output','review-1','review-2','output'):p.add_argument('--'+name,required=True)
 a=p.parse_args(); paths=[Path(getattr(a,x)) for x in ('protocol','started','raw_output','corrected_output','review_1','review_2')]
 bs=[read_regular(x) for x in paths];protocol,started,raw,corrected,r1,r2=map(json.loads,bs)
 verify_outputs(protocol,started,raw,corrected,sha(bs[0]),sha(bs[2]))
 script=ROOT/'scripts/run_ac2_reference_generation.py'
 if sha(read_regular(script))!=protocol['script_sha256']:raise ValueError('Protocol generation implementation changed.')
 with tempfile.TemporaryDirectory() as tmp:
  generated=Path(tmp)/'packets'
  subprocess.run([sys.executable,str(script),'review','--protocol',str(paths[0]),'--output',str(paths[3]),'--output-dir',str(generated)],cwd=ROOT,check=True,capture_output=True,text=True)
  expected=[blind(json.loads((generated/f'reviewer-{i}.json').read_bytes())) for i in (1,2)]
  gate={(h['history_id'],t['test']['test_id']):t['quality_assessment']['quality_status'] for h in corrected['histories'] for t in h['tests']}
  result=aggregate(expected,[r1,r2],gate)
 result['evidence_sha256']={str(path):sha(b) for path,b in zip(paths,bs)}
 result['requested_test_count']=sum(h['requested_test_count'] for h in expected[0]['histories']);result['generated_test_count']=sum(len(h['generated_tests']) for h in expected[0]['histories']);result['missing_test_count']=sum(h['missing_test_count'] for h in expected[0]['histories'])
 fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
 print(json.dumps({'output':a.output,'generated_questions':result['generated_test_count'],'unresolved':len(result['unresolved'])}))
if __name__=='__main__':main()
