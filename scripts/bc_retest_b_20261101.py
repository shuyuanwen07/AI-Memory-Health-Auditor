"""Frozen B reader-delivery retest: four histories, four policies, three repeats.

Preparation and registration are unbilled. Only --execute dispatches answers.
The shared reader is deliberately changed from weak to strong; writer, source
questions and all policy definitions are held fixed. Never retry an existing
condition journal. Expected answers are only copied to the evaluator-owned
test table; the ordinary target adapter removes them before provider calls.
"""
from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REL = Path('output/proposal-delivery/bc-reader-retest-20261101-v2/B')
OUT = ROOT / REL
OLD = ROOT / 'output/proposal-delivery/b-astra-four-strategy-20261101-v1/protocol.json'
ROLE = 'b_reader_delivery_retest_v2'
STRATEGIES = ['weak_first_hit', 'strong_rule_based', 'scope_aware', 'temporal_importance']
API = 'http://127.0.0.1:8000/api/v1'


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data, exclusive=False):
    path = Path(path)
    if exclusive:
        with path.open('x', encoding='utf8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
    else:
        temp = path.with_suffix(path.suffix + '.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        temp.replace(path)


def read(path):
    return json.loads(Path(path).read_text())


def signature(question):
    return (question['dimension'], question['prompt'], question['expected_behavior'],
            tuple(sorted(question['supporting_memory_ids'])))


def snapshot():
    from sqlalchemy import select
    from app.database.session import SessionLocal
    from app.models import AuditRunModel, MessageModel, TestCaseModel
    from app.api.routes import audit_schema, public_test_schema
    plan = read(OLD)
    sources = []
    with SessionLocal() as db:
        for item in plan['histories']:
            source = db.get(AuditRunModel, item['source_run_id'])
            if not source:
                raise ValueError('Missing frozen source audit')
            tests = list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == source.id)).all())
            rows = [public_test_schema(t).model_dump(mode='json') for t in tests]
            if sorted(map(signature, rows)) != sorted(map(signature, item['questions'])):
                raise ValueError('Source question contents changed')
            messages = list(db.scalars(select(MessageModel).where(
                MessageModel.conversation_id == source.conversation_id).order_by(MessageModel.sequence)).all())
            sources.append({'history_id': item['history_id'], 'source_run_id': source.id,
                'audit': audit_schema(source).model_dump(mode='json'), 'questions': rows,
                'messages': [{'message_id': m.source_message_id, 'role': m.role, 'content': m.content,
                              'timestamp': m.observation_timestamp.isoformat()} for m in messages]})
    print(json.dumps({'sources': sources}, ensure_ascii=False))


def prepare():
    if OUT.exists():
        raise ValueError('Existing B retest folder retained; no overwrite')
    result = subprocess.run(['docker', 'compose', 'exec', '-T', 'backend', 'python',
                             '/scripts/bc_retest_b_20261101.py', '--snapshot'],
                            check=True, capture_output=True, text=True, cwd=ROOT)
    material = json.loads(result.stdout)
    if len(material['sources']) != 4 or any(len(h['questions']) != 4 for h in material['sources']):
        raise ValueError('Need four histories and sixteen unchanged questions')
    old_protocol = read(OLD)
    if old_protocol['target_provider'] != 'openai' or old_protocol['target_model'] != 'gpt-6-astra':
        raise ValueError('Historical B target differs')
    OUT.mkdir(parents=True)
    write(OUT / 'sources.json', material, exclusive=True)
    schedule = []
    for repeat in range(1, 4):
        for hi, source in enumerate(material['sources']):
            offset = (repeat - 1 + hi) % 4
            for strategy in STRATEGIES[offset:] + STRATEGIES[:offset]:
                schedule.append({'repetition': repeat, 'history_id': source['history_id'],
                                 'source_run_id': source['source_run_id'], 'strategy': strategy})
    protocol = {'format': 'b-reader-delivery-retest-v2', 'frozen_at_utc': now(),
        'source_protocol_sha256': sha(OLD), 'source_snapshot_sha256': sha(OUT / 'sources.json'),
        'script_sha256': sha(__file__), 'sources': [{k: s[k] for k in ('history_id', 'source_run_id')}
                                                  for s in material['sources']],
        'strategies': STRATEGIES, 'provider': 'openai', 'model': 'gpt-6-astra',
        'requested_reasoning_effort': 'max', 'reader_configuration': 'strong',
        'common_reader_budget': {'output_token_limit': 8192, 'max_retrieved_records': 50,
                                'context_character_budget': 16000, 'capacity': 50},
        'provider_attempt_limit': 1, 'provider_timeout_seconds': 300,
        'writer': 'rule_based', 'unique_questions': 16, 'histories': 4, 'repetitions': 3,
        'planned_answers_per_strategy': 48, 'planned_answers': 192, 'schedule': schedule,
        'app_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / 'backend/app').rglob('*.py'))},
        'change_from_historical': 'Shared reader configuration changes weak to strong, altering both single-record trimming and reader instructions. Common reader budgets are explicit; retrieval definitions, deterministic writer, source questions and model are retained. This is not an isolated delivery-only causal test.',
        'score_protocol': {'primary': 'Independent source-grounded review; exact/lexical metrics are secondary only.',
            'verdicts': ['pass', 'partial', 'fail', 'uncertain'],
            'strict_pass': 'Answer satisfies all explicit requested criteria using source-supported facts.',
            'partial': 'Correct safe handling or some correct facts, but missing a requested factual component.',
            'fail': 'Wrong factual answer, wrong scope/update, unsupported selection, or no requested factual answer.',
            'uncertain': 'Question/reference ambiguity or reviewer cannot establish a result.',
            'denominator': 'Show strict passes / all 48 planned slots, and pass/partial/fail/uncertain/missing separately. Do not turn missing into semantic fail.',
            'uncertainty_unit': 'History clusters; repeats are correlated measurements, not new histories.'},
        'limits': ['Reuses previously observed related synthetic sources; development retest, not held-out validation.',
                  'Reader change is an intentional intervention; historical and current scores are not identical conditions.',
                  'Shared deterministic writer may still omit source facts; this is measured and not silently repaired.',
                  'Provider sampling is not deterministic; three repeats describe stability, not generalisation.',
                  'No score-dependent retries or case replacements. Partial/missing runs remain visible.',
                  'Two independent AI reviews are not human labels until separately confirmed.']}
    write(OUT / 'protocol.json', protocol, exclusive=True)
    print(json.dumps({'prepared': str(OUT), 'protocol_sha256': sha(OUT / 'protocol.json'),
                      'planned_answers': 192, 'paid_calls': 0}))


def register():
    from sqlalchemy import select
    from app.database.session import SessionLocal
    from app.models import AuditRunModel, ExperimentModel, TestCaseModel
    from app.schemas import AuditCreate, TestSuiteConfiguration
    from app.api.routes import audit_schema, audit_run_lock, build_audit, ident, persist_generated_tests
    protocol = read(OUT / 'protocol.json')
    sources = read(OUT / 'sources.json')['sources']
    if sha(OUT / 'sources.json') != protocol['source_snapshot_sha256']:
        raise ValueError('Frozen source snapshot changed')
    registrations = []
    with SessionLocal() as db, audit_run_lock(ROLE, db=db):
        existing = [g for g in db.scalars(select(ExperimentModel)).all()
                    if (g.test_suite_metadata or {}).get('study_role') == ROLE]
        if existing:
            raise ValueError('Existing B retest groups retained; do not duplicate registration')
        for source_item in sources:
            source = db.get(AuditRunModel, source_item['source_run_id'])
            original = audit_schema(source)
            questions = list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == source.id)).all())
            if sorted(signature({'dimension': q.dimension, 'prompt': q.prompt,
                 'expected_behavior': q.expected_behavior, 'supporting_memory_ids': q.supporting_memory_ids})
                 for q in questions) != sorted(map(signature, source_item['questions'])):
                raise ValueError('Live questions changed from freeze')
            suite = TestSuiteConfiguration(test_budget=4, random_seed=original.random_seed,
                prompt_template_version=original.prompt_template_version,
                pipeline_provider=original.pipeline_provider, pipeline_model=original.pipeline_model,
                semantic_review_provider=original.semantic_review_provider,
                semantic_review_model=original.semantic_review_model,
                evaluator_provider='rule_based', evaluator_model='rule-based-v66')
            group = ExperimentModel(id=ident('EXP'), conversation_id=source.conversation_id,
                label=f"B reader-delivery retest · {source_item['history_id']} · 3 repeats",
                status='CREATED', test_suite_configuration=suite.model_dump(mode='json'),
                test_suite_metadata={'study_role': ROLE, 'diagnostic_source_run_id': source.id})
            db.add(group); db.flush()
            canonical = {}
            for scheduled in [s for s in protocol['schedule'] if s['history_id'] == source_item['history_id']]:
                audit = build_audit(AuditCreate(conversation_id=source.conversation_id, experiment_id=group.id,
                    target_configuration='strong', provider='openai', model='gpt-6-astra',
                    temperature=original.temperature, random_seed=original.random_seed, test_budget=4,
                    prompt_template_version=original.prompt_template_version,
                    memory_strategy=scheduled['strategy'], retrieval_mode='fixed',
                    memory_maintenance_policy=original.memory_maintenance_policy,
                    target_memory_capacity=50, target_memory_writer='rule_based',
                    target_system_adapter=original.target_system_adapter,
                    target_memory_profile=original.target_memory_profile.model_copy(update={
                        'output_token_limit': 8192, 'max_retrieved_records': 50,
                        'context_character_budget': 16000})), db)
                row = db.get(AuditRunModel, audit.run_id)
                copies = persist_generated_tests(db, row, questions)
                for old, new in zip(questions, copies, strict=True):
                    new.target_memory_context = []
                    new.comparison_test_id = old.id
                    new.human_validity_status = old.human_validity_status
                    new.human_validity_reviewer = old.human_validity_reviewer
                    new.human_validity_note = old.human_validity_note
                    new.human_validity_reviewed_at = old.human_validity_reviewed_at
                    if canonical:
                        new.suite_test_id = canonical[old.id]
                if not canonical:
                    canonical = {old.id: new.id for old, new in zip(questions, copies, strict=True)}
                    group.test_suite_source_run_id = row.id
                row.status = 'TESTS_GENERATED'
                row.reproducibility_metadata = {**row.reproducibility_metadata,
                    'study_role': ROLE, 'diagnostic_source_run_id': source.id,
                    'bc_retest_repetition': scheduled['repetition'],
                    'bc_retest_protocol_sha256': sha(OUT / 'protocol.json'),
                    'reader_intervention': 'shared_reader_configuration_weak_to_strong',
                    'target_retry_policy': {'max_attempts': 1, 'timeout_seconds': 300,
                                            'retryable_status_codes': []},
                    'execution_budget': {'max_target_calls': 4, 'max_execution_seconds': 1400},
                    'human_validation': 'pending', 'validation_split': 'diagnostic_replay'}
                registrations.append({**scheduled, 'experiment_id': group.id, 'run_id': row.id})
            group.status = 'TEST_SUITE_GENERATED'
            group.test_suite_metadata = {**group.test_suite_metadata, 'test_count': 4,
                'generator_version': questions[0].generator_version}
        db.commit()
    print(json.dumps({'registered_utc': now(), 'protocol_sha256': sha(OUT / 'protocol.json'),
                      'registrations': registrations}, ensure_ascii=False))


def check_frozen(protocol, registration):
    if sha(OUT / 'protocol.json') != registration['protocol_sha256']:
        raise ValueError('Frozen protocol changed')
    if sha(OUT / 'sources.json') != protocol['source_snapshot_sha256']:
        raise ValueError('Frozen sources changed')
    if any(sha(ROOT / p) != value for p, value in protocol['app_sha256'].items()):
        raise ValueError('Application changed during collection')


def worker(run_id):
    """One production execute route in a dedicated no-retry provider scope."""
    from app.database.session import SessionLocal
    from app.api.routes import execute as production_execute
    from app.target_ai import providers
    providers._REQUEST_TIMEOUT_SECONDS = 300.0
    result = {'state': 'dispatched', 'run_id': run_id, 'provider_timeout_seconds': 300,
              'provider_attempt_limit': 1}
    try:
        with SessionLocal() as db, providers.single_attempt_target_request():
            responses = production_execute(run_id, db)
            result.update(state='returned', status=200,
                          response=[r.model_dump(mode='json') for r in responses])
    except Exception as error:
        result.update(state='failed_without_retry', status=getattr(error, 'status_code', None),
                      error_type=type(error).__name__, error=str(getattr(error, 'detail', ''))[:250])
    print(json.dumps(result, ensure_ascii=False), flush=True)


def execute():
    protocol = read(OUT / 'protocol.json')
    registration = read(OUT / 'registrations.json')
    by_history = {h['history_id']: h for h in read(OUT / 'sources.json')['sources']}
    rows = registration['registrations']
    if len(rows) != 48:
        raise ValueError('Expected 48 audit conditions')
    rank = {(x['history_id'], x['strategy'], x['repetition']): i
            for i, x in enumerate(protocol['schedule'])}
    rows.sort(key=lambda x: rank[(x['history_id'], x['strategy'], x['repetition'])])
    executions = OUT / 'executions'; executions.mkdir(exist_ok=True)

    def one(row):
        path = executions / f"r{row['repetition']}-{row['history_id']}-{row['strategy']}.json"
        if path.exists():
            return {'run_id': row['run_id'], 'status': 'existing_attempt_not_redispatched'}
        state = {**row, 'started_utc': now(), 'status': 'started', 'operations': []}
        write(path, state, exclusive=True)
        def call(method, route, body=None):
            check_frozen(protocol, registration)
            op = {'method': method, 'path': route, 'state': 'dispatched', 'dispatched_utc': now()}
            state['operations'].append(op); write(path, state)
            try:
                req = Request(API + route, method=method,
                    data=None if body is None else json.dumps(body).encode(),
                    headers={'Content-Type': 'application/json'})
                with urlopen(req, timeout=2400) as response:
                    op.update(state='returned', status=response.status, response=json.load(response), returned_utc=now())
            except HTTPError as error:
                op.update(state='http_error', status=error.code, error=error.read().decode(errors='replace')[:500])
                write(path, state); raise
            except Exception as error:
                op.update(state='ambiguous', error_type=type(error).__name__)
                write(path, state); raise
            write(path, state); return op['response']
        rid = row['run_id']
        try:
            audit = call('GET', f'/audits/{rid}')
            tests = call('GET', f'/audits/{rid}/tests')
            if (audit['provider'] != 'openai' or audit['model'] != 'gpt-6-astra'
                or audit['target_configuration'] != 'strong' or audit['target_memory_writer'] != 'rule_based'
                or audit['memory_strategy'] != row['strategy']):
                raise ValueError('Condition settings differ from freeze')
            if sorted(map(signature, tests)) != sorted(map(signature, by_history[row['history_id']]['questions'])):
                raise ValueError('Frozen questions changed')
            check_frozen(protocol, registration)
            op = {'method': 'POST', 'path': f'/audits/{rid}/execute', 'state': 'dispatched',
                  'dispatched_utc': now(), 'execution_boundary': 'production_route_in_single_attempt_worker'}
            state['operations'].append(op); write(path, state)
            process = subprocess.run(['docker','compose','exec','-T','backend','python',
                '/scripts/bc_retest_b_20261101.py','--worker',rid], cwd=ROOT,
                capture_output=True, text=True, timeout=1600)
            if process.returncode:
                op.update(state='ambiguous', error_type='worker_process_error', returncode=process.returncode)
                write(path, state)
                raise ValueError('Worker failed; outcome retained, no redispatch')
            payload = json.loads(process.stdout)
            op.update(payload); op['returned_utc'] = now(); write(path, state)
            if payload.get('state') != 'returned':
                raise ValueError('Provider condition failed; outcome retained, no retry')
            answers = payload['response']
            if len(answers) != 4:
                raise ValueError('Incomplete answer count')
            for answer in answers:
                meta = answer.get('execution_metadata', {})
                if meta.get('reported_model') != 'gpt-6-astra' or meta.get('requested_reasoning_effort') != 'max':
                    raise ValueError('Model/reasoning receipt differs from Astra max')
            call('GET', f'/audits/{rid}/target-memory-trace')
            call('GET', f'/audits/{rid}/agent-executions')
            state['status'] = 'completed_ai_review_pending'
        except Exception as error:
            state.update(status='stopped_without_redispatch', error_type=type(error).__name__, error=str(error)[:200])
            for suffix in ('responses', 'target-memory-trace'):
                try:
                    call('GET', f'/audits/{rid}/{suffix}')
                except Exception:
                    pass
        state['completed_utc'] = now(); write(path, state)
        print(json.dumps({k: state[k] for k in ('history_id','strategy','repetition','status')}) , flush=True)
        return {k: state[k] for k in ('history_id','strategy','repetition','run_id','status')}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(one, rows))
    write(OUT / 'collection-status.json', {'completed_utc': now(), 'conditions': results,
        'planned_answers': 192, 'assessment_status': 'independent_review_pending'})
    prepare_review()


def prepare_review():
    protocol = read(OUT / 'protocol.json')
    sources = {h['history_id']: h for h in read(OUT / 'sources.json')['sources']}
    items, private = [], []
    receipts = []
    for path in sorted((OUT / 'executions').glob('*.json')):
        state = read(path)
        tests = next((op['response'] for op in state['operations'] if op['path'].endswith('/tests') and op.get('state') == 'returned'), [])
        answers = next((op['response'] for op in state['operations'] if op['path'].endswith('/execute') and op.get('state') == 'returned'), None)
        if answers is None:
            answers = next((op['response'] for op in state['operations'] if op['path'].endswith('/responses') and op.get('state') == 'returned'), [])
        by_id = {t['test_id']: t for t in tests}
        trace = next((op['response'] for op in state['operations'] if op['path'].endswith('/target-memory-trace') and op.get('state') == 'returned'), {})
        retrieved = {r['test_id']: r for r in trace.get('retrievals', [])}
        for answer in answers:
            t = by_id.get(answer['test_id'])
            if not t:
                continue
            review_id = hashlib.sha256((sha(OUT/'protocol.json') + answer['response_id']).encode()).hexdigest()[:20]
            items.append({'review_id': review_id, 'source_statements': sources[state['history_id']]['messages'],
                'dimension': t['dimension'], 'question': t['prompt'], 'expected_behavior': t['expected_behavior'],
                'answer': answer['response_text'], 'question_validity': None, 'verdict': None, 'reason': None})
            private.append({'review_id': review_id, 'history_id': state['history_id'], 'strategy': state['strategy'],
                'repetition': state['repetition'], 'run_id': state['run_id'], 'test_id': answer['test_id'],
                'response_id': answer['response_id']})
            memory_input = answer.get('execution_metadata', {}).get('memory_input') or {}
            selected = retrieved.get(answer['test_id'], {}).get('selected_memory_ids', [])
            receipts.append({'review_id': review_id, 'strategy': state['strategy'], 'repetition': state['repetition'],
                'selected_memory_count': len(selected), 'sent_memory_count': memory_input.get('record_count'),
                'selected_memory_ids': selected, 'sent_memory_ids': memory_input.get('sent_memory_ids', []),
                'request_attempts': answer.get('execution_metadata',{}).get('request_attempts'),
                'model': answer.get('execution_metadata',{}).get('reported_model'),
                'requested_reasoning_effort': answer.get('execution_metadata',{}).get('requested_reasoning_effort')})
    random.Random(2026110199).shuffle(items)
    review = OUT / 'blind-review'; review.mkdir(exist_ok=True)
    common = {'format': 'b-reader-retest-independent-review-v2', 'protocol_sha256': sha(OUT/'protocol.json'),
        'procedure': 'Review every source-grounded answer independently. Policy/model/repetition and automated scores are withheld. AI review is not human review.',
        'rubric': protocol['score_protocol']}
    for slot in (1, 2):
        dest = review / f'reviewer-{slot}.blank.json'
        if not dest.exists():
            write(dest, {**common, 'reviewer_slot': slot, 'completed_by_human': False, 'items': items}, exclusive=True)
    write(OUT / 'private-review-key.json', {'mapping': private})
    write(OUT / 'memory-delivery-receipts.json', {'items': receipts})
    totals = {s: sum(x['strategy'] == s for x in private) for s in STRATEGIES}
    write(OUT / 'answer-collection-summary.json', {'planned_answers_per_strategy': 48,
        'saved_answers_per_strategy': totals, 'planned_answers': 192, 'saved_answers': len(private),
        'missing_answers': 192-len(private), 'score_status': 'independent_review_pending',
        'reader': 'strong', 'writer': 'rule_based', 'model': 'gpt-6-astra', 'effort': 'max'})
    print(json.dumps({'review_items': len(items), 'saved_per_strategy': totals, 'missing': 192-len(items)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ('snapshot','prepare','register','execute','prepare-review'):
        modes.add_argument('--'+name, action='store_true')
    modes.add_argument('--worker', metavar='RUN_ID')
    args = parser.parse_args()
    if args.worker: worker(args.worker)
    elif args.snapshot: snapshot()
    elif args.prepare: prepare()
    elif args.register: register()
    elif args.execute: execute()
    else: prepare_review()


if __name__ == '__main__':
    main()
