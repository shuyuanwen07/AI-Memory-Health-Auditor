"""Repeated source-critic development probe on ten flagged past questions.

Inputs deliberately omit earlier judgments and condition labels. Existing
ledgers are never re-dispatched after interruption or unknown request outcome.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
from app.extraction.llm import PipelineLLMClient
from scripts.run_ac2_full_source_critic_development_20261030 import FIELDS, INSTRUCTIONS, MODEL, SCHEMA

PACKET = Path('/output/proposal-delivery/AC2措辞疑点-10题双人复核-20261030.zip')
OUT = Path('/ac3-results/ac2-critic-wording-stability-20261030-v1')
SCRIPT = Path(__file__)
PARENT = Path('/scripts/run_ac2_full_source_critic_development_20261030.py')


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def write(p, value):
    temporary=p.with_suffix('.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temporary.replace(p)


def inputs():
    with ZipFile(PACKET) as z:
        left,right=(json.loads(z.read(f'reviewer-{i}.json')) for i in (1,2))
    assert left['source_sha256']==right['source_sha256']
    assert left['items']==right['items'] and len(left['items'])==10
    assert len({item['blind_id'] for item in left['items']})==10
    assert all(not any(item['review'].values()) for item in left['items'])
    return left['items']


def freeze():
    items=inputs(); OUT.mkdir(parents=True,exist_ok=False)
    protocol={'format':'ac2-critic-wording-stability-v1','frozen_at_utc':now(),'packet_sha256':sha(PACKET),
      'script_sha256':sha(SCRIPT),'critic_source_sha256':sha(PARENT),'item_ids':[x['blind_id'] for x in items],
      'model':MODEL,'provider':'openrouter','instructions':INSTRUCTIONS,'schema':SCHEMA,'max_output_tokens':2400,
      'repetitions_per_item':3,'order':'Fixed packet order in each of three repetitions; no previous labels or answers from other reviewers are supplied.',
      'limitations':'Development comparison on 10 previously identified questions sharing 3 synthetic histories, selected after earlier results. Repeated model calls are correlated, not independent cases. User-reported human review is in progress; no human labels or score exposure assumed. No outer retry after unknown outcome.'}
    write(OUT/'protocol.json',protocol);print('Protocol frozen; no model requests sent.',flush=True)


def run():
    protocol_path=OUT/'protocol.json';protocol=json.loads(protocol_path.read_text());ledger_path=OUT/'ledger.json'
    if ledger_path.exists():raise ValueError('Existing ledger; inspect rather than re-dispatch')
    def check():
        if sha(PACKET)!=protocol['packet_sha256'] or sha(SCRIPT)!=protocol['script_sha256'] or sha(PARENT)!=protocol['critic_source_sha256']:
            raise ValueError('Frozen source or script changed')
    check();items=inputs();assert [x['blind_id'] for x in items]==protocol['item_ids']
    rows=[{'repetition':rep,'blind_id':item['blind_id'],'state':'not_started'} for rep in range(1,4) for item in items]
    ledger={'protocol_sha256':sha(protocol_path),'started_at_utc':now(),'rows':rows};write(ledger_path,ledger)
    client=PipelineLLMClient('openrouter',MODEL)
    for row in rows:
        check();item=next(x for x in items if x['blind_id']==row['blind_id'])
        material={k:item[k] for k in ('source_messages','question','reference_answer')}
        prompt=json.dumps(material,ensure_ascii=False,sort_keys=True)
        row.update(state='dispatched',dispatched_at_utc=now(),input_sha256=hashlib.sha256(prompt.encode()).hexdigest());write(ledger_path,ledger)
        try:
            response=client.complete_json(instructions=INSTRUCTIONS,prompt=prompt,schema_name='full_source_question_review',
                schema=SCHEMA,max_output_tokens=2400,agent_role='source_question_review',prompt_template_version='full-source-critic-development-v1')
            if not isinstance(response,dict) or set(response)!=set(FIELDS)|{'notes'} or any(response[k] not in ('valid','invalid','uncertain') for k in FIELDS) or not isinstance(response['notes'],str) or not response['notes'].strip():
                raise ValueError('Invalid response shape')
            row.update(state='returned',review=response)
        except Exception as exc:row.update(state='failed',error_type=type(exc).__name__)
        row.update(finished_at_utc=now(),execution=client.last_execution);write(ledger_path,ledger)
        print('Completed request',sum(x['state'] in ('returned','failed') for x in rows),'of',len(rows),flush=True)
    ledger['finished_at_utc']=now();write(ledger_path,ledger)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run'])
    {'freeze':freeze,'run':run}[parser.parse_args().action]()
