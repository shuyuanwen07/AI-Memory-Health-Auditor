"""Post-run message-provenance coverage check; never feeds annotations to targets."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/bc-reader-retest-20261101-v2/C'
sources={r['question_id']:r for r in json.loads((OUT/'selected-source.json').read_text())}
annotations={}
for cid,row in sources.items():
    ids=[];index=0
    for session in row['haystack_sessions']:
        for msg in session:
            index+=1
            if msg.get('has_answer') is True:
                ids.append(str(msg.get('message_id') or msg.get('id') or f'MSG-{index:03d}'))
    annotations[cid]=set(ids)
items=[];by=defaultdict(Counter);input_groups=defaultdict(list)
for path in sorted((OUT/'responses').glob('*.json')):
    state=json.loads(path.read_text())
    if state['status']!='completed':continue
    job=state['job'];case=state['result']['conditions'][0]['cases'][0]
    meta=case['execution_metadata'];receipt=meta.get('memory_input')or{}
    input_groups[(job['case_id'],job['strategy'])].append(receipt)
    gold=annotations[job['case_id']]
    coverage={stage:set() for stage in ['written','retained','retrieved','supplied']}
    for memory in case['memory_evidence']:
        supporting=set(memory.get('source_message_ids',[]))&gold
        coverage['written']|=supporting
        if memory['lifecycle_state'] not in {'EVICTED','SUPERSEDED'}:coverage['retained']|=supporting
        if memory.get('retrieved'):coverage['retrieved']|=supporting
        if memory.get('supplied'):coverage['supplied']|=supporting
    eligible=bool(gold)
    row={'job_id':job['job_id'],'case_id':job['case_id'],'strategy':job['strategy'],'repeat':job['repeat'],
         'annotated_answer_message_ids':sorted(gold),'coverage_check_applicable':eligible,
         **{stage+'_annotated_message_ids':sorted(value) for stage,value in coverage.items()},
         'stored_memory_count':case['stored_memory_count'],'retrieved_records':len(case['retrieved_memory_ids']),
         'supplied_records':len(case['supplied_memory_ids']),
         'model_effort_budget_verified':meta.get('reported_model')=='gpt-6-astra' and meta.get('requested_reasoning_effort')=='max' and meta.get('requested_output_token_limit')==8192 and meta.get('request_attempts')==1}
    items.append(row)
    counts=by[job['strategy']];counts['completed']+=1
    counts['receipt_verified']+=row['model_effort_budget_verified']
    if eligible:
        counts['annotated_message_cases']+=1
        for stage,value in coverage.items():
            counts[stage+'_any_annotated_message']+=bool(value)
            counts[stage+'_all_annotated_messages']+=value==gold
repeats=[]
for (cid,strategy),receipts in input_groups.items():
    if len(receipts)<2:continue
    repeats.append({'case_id':cid,'strategy':strategy,'observed_repeats':len(receipts),
        'distinct_context_hashes':len({r.get('context_sha256') for r in receipts}),
        'distinct_instruction_hashes':len({r.get('instruction_sha256') for r in receipts}),
        'distinct_prompt_hashes':len({r.get('prompt_sha256') for r in receipts})})
report={'format':'bc-c-delivery-diagnostic-v2','generated_at_utc':datetime.now(timezone.utc).isoformat(),
    'completed':len(items),'by_strategy':{s:dict(c) for s,c in by.items()},'items':items,
    'repeated_condition_inputs':repeats,
    'claim_boundary':'Post-run use of official has_answer message annotations for diagnostic provenance only. These annotations and gold answers never enter target model inputs. A record citing an annotated message can omit the answer-bearing clause, so provenance coverage is not proof of semantic evidence preservation or answer correctness.'}
p=OUT/'delivery-control-check.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
print(json.dumps({'completed':len(items),'repeated_conditions_checked':len(repeats),
    'input_drift_conditions':sum(any(r[k]!=1 for k in ['distinct_context_hashes','distinct_instruction_hashes','distinct_prompt_hashes']) for r in repeats)}))
