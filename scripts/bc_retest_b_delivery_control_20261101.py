"""Read-only B delivery and repeat-input controls; does not grade answers."""
from collections import Counter,defaultdict
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/bc-reader-retest-20261101-v2/B'
read=lambda p:json.loads(Path(p).read_text())
digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def analyse():
    snapshots=read(OUT/'read-only-final-snapshots.json')['conditions']
    source={s['history_id']:s for s in read(OUT/'sources.json')['sources']}
    control_groups=defaultdict(list);stores=defaultdict(list);delivery=defaultdict(list)
    allmeta=[];questions=defaultdict(set)
    for row in snapshots:
        tests={q['test_id']:q for q in row['tests']}
        trace=row['trace'];byvalue={r['memory_id']:r['canonical_value'] for r in trace['records']}
        record_values=[]
        for r in trace['records']:
            rel=[(e.get('type') or e.get('relationship_type'),byvalue.get(e.get('target_memory_id')))
                 for e in r.get('relationships',[])]
            record_values.append([r['canonical_value'],r['scope'],r['lifecycle_state'],r['source_message_ids'],rel])
        stores[row['history_id']].append({'run_id':row['run_id'],'signature':digest(record_values),
            'record_count':len(trace['records']),
            'covered_source_ids':sorted({s for r in trace['records'] for s in r.get('source_message_ids',[])})})
        retrievals={r['test_id']:r for r in trace['retrievals']}
        for a in row['responses']:
            q=tests[a['test_id']];meta=a['execution_metadata'];receipt=meta.get('memory_input') or {}
            sig=(q['dimension'],q['prompt'],q['expected_behavior'])
            questions[row['history_id']].add(sig)
            group=(row['history_id'],row['strategy'],*sig)
            control_groups[group].append({'repetition':row['repetition'],**{
                k:receipt.get(k) for k in ('context_sha256','instruction_sha256','prompt_sha256')}})
            selected=retrievals.get(a['test_id'],{}).get('selected_memory_ids',[])
            sent=receipt.get('sent_memory_ids',[])
            delivery[row['strategy']].append({'selected_count':len(selected),'sent_count':receipt.get('record_count'),
                'same_ids':selected==sent,'selected_ids':selected,'sent_ids':sent})
            allmeta.append(meta)
    invariants=[]
    for group,items in control_groups.items():
        hashes={k:len({i[k] for i in items}) for k in ('context_sha256','instruction_sha256','prompt_sha256')}
        invariants.append({'history_id':group[0],'strategy':group[1],'dimension':group[2],
            'question_sha256':digest(group[3]),'observations':len(items),
            'repetitions':sorted(i['repetition'] for i in items),
            'unique_hashes':hashes,
            'passed':len(items)==3 and all(v==1 for v in hashes.values())
                and all(i[k] for i in items for k in hashes)})
    writer=[]
    for hid,rows in stores.items():
        venue=[m for m in source[hid]['messages'] if 'venue' in m['content'].lower()]
        covered=set(rows[0]['covered_source_ids'])
        writer.append({'history_id':hid,'condition_count':len(rows),
            'distinct_store_signatures':len({r['signature'] for r in rows}),
            'record_counts':sorted({r['record_count'] for r in rows}),
            'venue_source_message_ids':[m['message_id'] for m in venue],
            'unrepresented_venue_source_ids':[m['message_id'] for m in venue if m['message_id'] not in covered],
            'interpretation':'Source-provenance coverage is not strict fact recall. Missing venue-message records indicate a shared writer limitation; retrieval cannot repair facts absent from its store.'})
    compliance={
        'model_astra':sum(m.get('reported_model')=='gpt-6-astra' for m in allmeta),
        'effort_max':sum(m.get('requested_reasoning_effort')=='max' for m in allmeta),
        'output_budget_8192':sum(m.get('requested_output_token_limit')==8192 for m in allmeta),
        'one_provider_attempt':sum(m.get('request_attempts')==1 for m in allmeta),
        'openai_source':sum(m.get('response_source')=='openai' for m in allmeta),
        'complete':sum(m.get('completion_status')=='complete' for m in allmeta)}
    policy={s:{'answers':len(rows),'same_selected_and_sent_ids':sum(r['same_ids'] for r in rows),
        'selected_counts':dict(Counter(r['selected_count'] for r in rows)),
        'sent_counts':dict(Counter(r['sent_count'] for r in rows))} for s,rows in delivery.items()}
    result={'format':'b-reader-delivery-control-analysis-v1','planned_answers':192,'saved_answers':len(allmeta),
        'missing_answers':192-len(allmeta),'unique_questions_by_history':{h:len(q) for h,q in questions.items()},
        'provider_receipt_compliance':compliance,'by_strategy':policy,
        'repeat_input_group_count':len(invariants),'repeat_input_groups_passed':sum(i['passed'] for i in invariants),
        'repeat_input_groups':invariants,'shared_writer_controls':writer,
        'total_input_tokens':sum(m.get('input_tokens') or 0 for m in allmeta),
        'total_output_tokens':sum(m.get('output_tokens') or 0 for m in allmeta),
        'total_reasoning_tokens':sum(m.get('reasoning_tokens') or 0 for m in allmeta),
        'claim_boundary':'Execution/delivery checks only. No answer judgments or model accuracy are derived by this analysis.'}
    (OUT/'delivery-control-analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('saved_answers','missing_answers','provider_receipt_compliance','repeat_input_groups_passed','repeat_input_group_count','by_strategy')},ensure_ascii=False))


if __name__=='__main__':analyse()
