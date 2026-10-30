"""Prepare GARDEN and SHOP source audits in the existing four-scenario campaign.

Input is a previously frozen, human-confirmed synthetic source package. This
stage creates a completed *source audit* for each history so the application
can fork three controlled comparison conditions. Source audits invoke the
target four times each: 8 additional target answers in this runner. They are not
the 48 answers planned for the three-method experiment.

This script stops before freezing any comparison inventory, generating any A
questions, recording any human-validity decisions, or executing A conditions.
No AI decision is represented as a human decision. Every mutating request is
checkpointed before dispatch. An ambiguous or failed request stops the script;
it is never automatically repeated. Resume is safe only after a returned
successful response was durably recorded. Inspect and reconcile an ambiguous
request with the application before any manual intervention.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'experiment-a-expanded-20261030'
INPUT = OUT / 'four-scenario-frozen-input.json'
STATE = OUT / 'shop-preparation-ledger.json'
API = os.environ.get('AUDITOR_PREP_API', 'http://127.0.0.1:8000/api/v1').rstrip('/')
CAMPAIGN = 'diverse-a-20261030-v1'
MODEL = 'openai/gpt-6-luna'
PROFILE = {'label':'Four-scenario shared reader','version':1,'max_retrieved_records':50,
           'context_character_budget':16000,'isolate_project_scope':False,'prefer_current_state':False,
           'retain_assistant_history':True,'retrieve_message_context':False,'identity_analysis':'off',
           'identity_analysis_failure_policy':'fail_closed','identity_analysis_output_token_limit':4096,
           'additional_instructions':'','output_token_limit':1024}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def save(value):
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    os.replace(temporary, STATE)


def main():
    if not INPUT.is_file():
        raise SystemExit(f'Missing frozen input: {INPUT}')
    package = json.loads(INPUT.read_text())
    histories = package.get('histories')
    if not isinstance(histories, list) or len(histories) != 4:
        raise SystemExit('Frozen input must contain exactly four histories.')
    if len({h.get('history_id') for h in histories}) != 4:
        raise SystemExit('History IDs must be unique.')
    for h in histories:
        messages = h.get('messages', [])
        if len(messages) != 7 or any(m.get('role') != 'user' or not m.get('message_id') or not m.get('content') for m in messages):
            raise SystemExit(f"{h.get('history_id')}: expected seven identified user messages")
        if len({m['message_id'] for m in messages}) != 7:
            raise SystemExit(f"{h['history_id']}: duplicate source message IDs")
        if len(h.get('fixed_question_draft', [])) != 4 or len(h.get('candidate_failure_patterns', [])) != 4:
            raise SystemExit(f"{h['history_id']}: expected four questions and four candidate patterns")
    histories = [h for h in histories if h['history_id'] in {'SHOP'}]
    if len(histories) != 1:
        raise SystemExit('Frozen input must contain SHOP.')
    source_sha = hashlib.sha256(INPUT.read_bytes()).hexdigest()
    script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if STATE.exists():
        state = json.loads(STATE.read_text())
        if state['source_sha256'] != source_sha or state['script_sha256'] != script_sha or state['api'] != API:
            raise SystemExit('Frozen inputs, runner or API changed. Inspect existing ledger before continuing.')
    else:
        state = {'format':'a-diverse-preparation-ledger-v1','campaign_id':CAMPAIGN,
                 'source_sha256':source_sha,'script_sha256':script_sha,'api':API,
                 'created_at':now(),'source_audit_target_answers_planned':4,
                 'comparison_target_answers_planned':48,
                 'provenance':'Human-confirmed synthetic source; manually entered reference graph. No AI or simulated review is recorded as human.',
                 'status':'preparing','histories':{h['history_id']:{'operations':{}} for h in histories}}
        save(state)

    def call(row, key, method, path, body=None, timeout=900):
        operation = {'method':method,'path':path,'body':body}
        request_sha = digest(operation)
        previous = row['operations'].get(key)
        if previous:
            if previous['request_sha256'] != request_sha:
                raise RuntimeError(f'{key}: request changed; refusing to resume')
            if previous['state'] == 'returned':
                return previous['response']
            raise RuntimeError(f"{key}: prior request state {previous['state']} requires manual reconciliation; no retry")
        entry = {**operation,'request_sha256':request_sha,'state':'dispatched','started_at':now()}
        row['operations'][key] = entry
        save(state)
        request = Request(API+path, method=method,
                          data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
                          headers={'Content-Type':'application/json'})
        try:
            with urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read())
                entry.update(state='returned',status=response.status,response=result,finished_at=now())
        except HTTPError as exc:
            entry.update(state='http_error',status=exc.code,error=exc.read().decode(errors='replace'),finished_at=now())
            save(state)
            raise RuntimeError(f'{key}: HTTP {exc.code}; preserved, no automatic retry') from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            entry.update(state='ambiguous',error_type=type(exc).__name__,finished_at=now())
            save(state)
            raise RuntimeError(f'{key}: ambiguous response; preserved, no automatic retry') from exc
        save(state)
        print(f"{row['history_id']} {key}: complete", flush=True)
        return result

    for h in histories:
        row = state['histories'][h['history_id']]
        row['history_id'] = h['history_id']
        try:
            conversation = call(row,'conversation','POST','/conversations',
                {'authorised':True,'source_origin':'synthetic','messages':h['messages']})
            cid = conversation['conversation_id']
            memory_ids = []
            for i, message in enumerate(h['messages']):
                edges = {2:(1,'UPDATE'),4:(3,'CONFLICT'),6:(5,'CONTEXTUAL_OVERRIDE')}
                relations = []
                if i in edges:
                    other, kind = edges[i]
                    relations = [{'type':kind,'target_memory_id':memory_ids[other],
                                  'evidence_message_ids':[h['messages'][other]['message_id'],message['message_id']]}]
                memory = call(row,f'memory-{i+1}','POST','/memories',
                    {'conversation_id':cid,'canonical_value':message['content'],
                     'source_message_ids':[message['message_id']],'relationships':relations})
                memory_ids.append(memory['memory_id'])
            call(row,'ground-truth','POST',f'/conversations/{cid}/confirm-ground-truth',{'confirmed_memory_ids':memory_ids})
            preview = call(row,'coverage','GET',f'/conversations/{cid}/test-coverage-preview?test_budget=4&coverage_policy=strict_full_v1')
            if not preview.get('minimum_met'):
                raise RuntimeError('Strict four-dimension coverage unavailable; inspect source before continuing.')
            audit = call(row,'source-audit','POST','/audits',{
                'conversation_id':cid,'target_configuration':'weak','provider':'openrouter','model':MODEL,
                'pipeline_provider':'rule_based','pipeline_model':'rule-based-v2',
                'semantic_review_provider':'rule_based','semantic_review_model':'rule-based-v2',
                'evaluator_provider':'rule_based','evaluator_model':'rule-based-v65',
                'test_budget':4,'coverage_policy':'strict_full_v1','random_seed':42,'temperature':0,
                'memory_strategy':'weak_first_hit','memory_maintenance_policy':'update_aware_consolidation',
                'target_memory_capacity':50,'target_memory_writer':'rule_based','target_memory_profile':PROFILE})
            rid = audit['run_id']
            tests = call(row,'source-generate','POST',f'/audits/{rid}/generate-tests')
            if len(tests) != 4 or any(t.get('quality_status') != 'accepted' for t in tests):
                raise RuntimeError('Source suite is incomplete or needs review; inspect it before continuing.')
            call(row,'source-execute','POST',f'/audits/{rid}/execute',{})
            call(row,'source-evaluate','POST',f'/audits/{rid}/evaluate',{})
            detail = call(row,'source-completed','GET',f'/audits/{rid}')
            if detail.get('status') != 'COMPLETED':
                raise RuntimeError('Source audit did not complete; inspect before registration.')
            result = call(row,'campaign-register','POST',f'/audits/{rid}/method-comparison',
                {'campaign_id':CAMPAIGN,'scenario_id':h['history_id'],'planned_scenarios':4})
            row.update(conversation_id=cid,source_run_id=rid,memory_ids=memory_ids,
                       comparison_id=result['comparison_id'],status='prepared_inventory_not_frozen')
            save(state)
        except (RuntimeError, KeyError, TypeError) as exc:
            row.update(status='stopped',error=str(exc));state['status']='stopped';save(state)
            raise SystemExit(f"Stopped at {h['history_id']}: {exc}") from exc
    state['status'] = 'prepared_inventory_not_frozen'
    state['finished_at'] = now()
    save(state)
    print('GARDEN and SHOP source audits completed and campaign registered. A inventories and all human review gates remain pending.')


if __name__ == '__main__':
    main()
