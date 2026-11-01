"""Exploratory direct OpenAI question generation, not the product pipeline."""
import concurrent.futures, hashlib, json, os, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'output/proposal-delivery/ac2-prospective-new-histories-20261029/histories.json'
OUT = ROOT / 'output/proposal-delivery/ac2-astra-max-pilot-20261101'
PROMPT = '''Create exactly four distinct memory-audit questions for the supplied conversation, one each for accuracy, freshness, conflict resolution, and appropriate use. Each question must be answerable using only the source; avoid invented details. For unresolved contradictory claims, the expected answer must acknowledge the conflict, not choose a winner. Include question, expected_answer, dimension, and the exact supporting source_message_ids. If a dimension cannot be tested from this history, return an object with dimension and unavailable_reason rather than inventing a question. Output JSON as {"questions": [...]} only.'''

def save(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
def run(item):
    index, rep, history = item
    payload = {'model':'gpt-6-astra','reasoning':{'effort':'max'},'max_output_tokens':8000,'store':False,
               'input':[{'role':'system','content':PROMPT}, {'role':'user','content':json.dumps({'messages':history['messages']},ensure_ascii=False)}]}
    req=urllib.request.Request('https://api.openai.com/v1/responses', data=json.dumps(payload).encode(),
        headers={'Authorization':'Bearer '+os.environ['PILOT_OPENAI_KEY'],'Content-Type':'application/json'},method='POST')
    started=datetime.now(timezone.utc).isoformat(); path=OUT / f'{index:02d}-repeat-{rep}.json'
    record={'history_id':history['conversation_id'],'repeat':rep,'started_at':started,'status':'dispatched','request':payload}
    save(path,record)
    try:
        with urllib.request.urlopen(req,timeout=600) as response: data=json.load(response)
        record.update(status='returned',response=data)
    except urllib.error.HTTPError as e:
        record.update(status='http_error',http_status=e.code,error=e.read().decode()[:2000])
    except Exception as e: record.update(status='transport_error',error_type=type(e).__name__)
    record['finished_at']=datetime.now(timezone.utc).isoformat();save(path,record)
    print(history['conversation_id'], rep, record['status'],flush=True)
    return record

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    histories=json.loads(SOURCE.read_text())['conversations'][:3]
    protocol={'source':str(SOURCE.relative_to(ROOT)),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
      'history_ids':[h['conversation_id'] for h in histories], 'repetitions_per_history':2,'requested_slots':24,
      'model':'gpt-6-astra','reasoning_effort':'max','provider':'OpenAI Responses API',
      'design':'Direct prompt to model using original source messages, not the original product generator; exploratory, 3 previously seen synthetic histories, 2 repeated calls each; no retry, no target execution.',
      'review':'Model output is not validity evidence; independent source-based human review needed. Missing slots remain missing; uncertainty retained.',
      'comparison':'62/120 was from a 30-history product pipeline and human-checked adjudication, not a model-only baseline; this pilot changes generator, model, sample and sampling.'}
    save(OUT/'protocol.json',protocol);save(OUT/'sources.json',histories)
    os.environ['PILOT_OPENAI_KEY']=dotenv_values(ROOT/'.env')['OPENAI_API_KEY']
    jobs=[(i,rep,h) for i,h in enumerate(histories,1) for rep in (1,2)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(run,jobs))
    items=[]
    for r in results:
        data=r.get('response',{}); parts=[c.get('text','') for out in data.get('output',[]) for c in out.get('content',[]) if c.get('type')=='output_text']
        try: questions=json.loads(''.join(parts))['questions']
        except Exception: questions=[]
        for n,q in enumerate(questions,1): items.append({'history_id':r['history_id'],'repeat':r['repeat'],'item':n,'question':q,'human_validity':'','reason':''})
    save(OUT/'review-pending.json',{'instructions':'Judge each item against the complete source; use valid / invalid / uncertain. Do not treat model output as validated.', 'items':items})
    save(OUT/'summary.json',{'requested_calls':len(jobs),'returned':sum(x['status']=='returned' for x in results),'items_to_review':len(items),
      'response_statuses':[x.get('response',{}).get('status') for x in results], 'usage':[x.get('response',{}).get('usage') for x in results],
      'human_validity':'pending','comparison_to_62_120':'not yet established'})
    print('Review items:',len(items),flush=True)

if __name__=='__main__': main()
