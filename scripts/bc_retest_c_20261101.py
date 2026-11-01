"""Freeze and execute the 16-case, three-repeat OpenAI Astra C retest.

Every job calls the production LiveBenchmarkRunner in its own container process.
The operational audit database is not used; source/gold separation, reader and
retrieval implementation are the application's ordinary benchmark boundary.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
REL = Path('output/proposal-delivery/bc-reader-retest-20261101-v2/C')
OUT = ROOT / REL
CONTAINER_OUT = Path('/') / REL
SOURCE = Path('output/longmemeval-official-v1/source/longmemeval_oracle.json')
MANIFEST = Path('output/longmemeval-official-v1/source-manifest.json')
STRATEGIES = ['weak_first_hit', 'strong_rule_based', 'scope_aware', 'temporal_importance']
ANCHORS = ['affe2881', 'ba61f0b9']
QUOTAS = {'knowledge-update': 2, 'multi-session': 3, 'temporal-reasoning': 3,
          'single-session-user': 2, 'single-session-assistant': 2,
          'single-session-preference': 2, 'abstention': 2}
SEED = 20261101


def now():
    return datetime.now(timezone.utc).isoformat()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return sha_bytes(Path(path).read_bytes())


def load(path):
    return json.loads(Path(path).read_text())


def write(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if exclusive:
        with path.open('x', encoding='utf8') as f:
            f.write(data)
    else:
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(data, encoding='utf8')
        tmp.replace(path)


def stratum(row):
    return 'abstention' if '_abs' in row['question_id'] else row['question_type']


def prepare():
    if (OUT / 'protocol.json').exists():
        raise RuntimeError('Existing frozen protocol retained; do not prepare another sample.')
    manifest = load(ROOT / MANIFEST)
    entry = next(r for r in manifest['files'] if r['file'] == SOURCE.as_posix())
    source = ROOT / SOURCE
    if sha(source) != entry['sha256'] or source.stat().st_size != entry['bytes']:
        raise RuntimeError('Pinned official source does not match the saved release manifest.')
    if entry['commit'] != '98d7416c24c778c2fee6e6f3006e7a073259d48f':
        raise RuntimeError('Unexpected LongMemEval source revision.')
    rows = load(source)
    by_id = {r['question_id']: r for r in rows}
    if len(rows) != 500 or len(by_id) != 500:
        raise RuntimeError('Expected 500 unique official Oracle cases.')
    rng = random.Random(SEED)
    chosen = [by_id[qid] for qid in ANCHORS]
    for cat in sorted(QUOTAS):
        need = QUOTAS[cat] - sum(stratum(r) == cat for r in chosen)
        pool = sorted([r for r in rows if stratum(r) == cat and r['question_id'] not in ANCHORS],
                      key=lambda r: r['question_id'])
        rng.shuffle(pool)
        if len(pool) < need:
            raise RuntimeError('Category source pool is too small.')
        chosen.extend(pool[:need])
    if len(chosen) != 16 or Counter(map(stratum, chosen)) != Counter(QUOTAS):
        raise RuntimeError('Sample quota mismatch.')
    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / 'selected-source.json', chosen, exclusive=True)
    os.chmod(OUT / 'selected-source.json', 0o600)
    selection = [{'case_id': r['question_id'], 'stratum': stratum(r),
                  'source_row_sha256': sha_bytes(json.dumps(r, sort_keys=True, separators=(',', ':')).encode()),
                  'prior_two_case_anchor': r['question_id'] in ANCHORS} for r in chosen]
    jobs = [{'repeat': rep, 'case_id': r['question_id'], 'strategy': strategy}
            for rep in range(1, 4) for r in chosen for strategy in STRATEGIES]
    random.Random(SEED + 1).shuffle(jobs)
    for index, job in enumerate(jobs):
        job['job_id'] = f'C{index + 1:03d}'
    profile = {'label': 'BC fixed full reader, Astra max', 'version': 1,
               'max_retrieved_records': 50, 'context_character_budget': 16000,
               'isolate_project_scope': False, 'prefer_current_state': False,
               'retain_assistant_history': True, 'retrieve_message_context': False,
               'identity_analysis': 'off', 'identity_analysis_failure_policy': 'fail_closed',
               'identity_analysis_output_token_limit': 4096, 'additional_instructions': '',
               'output_token_limit': 8192}
    protocol = {'format': 'bc-reader-retest-c-v2', 'frozen_at_utc': now(),
                'selection_seed': SEED, 'job_order_seed': SEED + 1,
                'source_authorised': True, 'authorization_basis': 'User requested rerun of C with OpenAI Astra and broader objective source cases.',
                'source': entry, 'source_manifest_sha256': sha(ROOT / MANIFEST),
                'subset_sha256': sha(OUT / 'selected-source.json'), 'selection': selection,
                'category_quotas': QUOTAS, 'case_count': 16, 'repetitions': 3,
                'planned_answers_per_strategy': 48, 'planned_target_calls': 192,
                'strategies': STRATEGIES, 'provider': 'openai', 'model': 'gpt-6-astra',
                'requested_reasoning_effort': 'max', 'sampling_control': 'model_default; no provider temperature or seed sent',
                'reader_configuration': 'strong', 'writer': 'rule_based',
                'target_memory_capacity': 50, 'target_memory_profile': profile,
                'request_attempt_limit': 1, 'target_timeout_seconds': 300,
                'concurrency': 3, 'jobs': jobs,
                'script_sha256': sha(Path(__file__)),
                'application_sha256': {p.relative_to(ROOT).as_posix(): sha(p)
                                       for p in sorted((ROOT / 'backend/app').rglob('*.py'))},
                'evaluation': {'primary': 'Two independent source-grounded reviews and later explicit human confirmation.',
                               'reference_validity': 'valid/invalid/uncertain separately from answer correctness',
                               'answer_verdict': 'pass/fail/uncertain; missing and invalid references are not passes',
                               'automatic_lexical_metric': 'descriptive only, not the primary correctness metric',
                               'no_outcome_dependent_reruns': True,
                               'unit_of_analysis': '16 distinct questions; 48 repeated answers per strategy are not 48 independent questions'},
                'limits': ['Official Oracle evidence-only inputs, not full-history S/M or the official benchmark stack.',
                           'Two cases are reused anchors. Prior exposure of the additional selected cases has not been excluded; do not call the set held-out.',
                           'The sample is fixed by category, stable ID sorting and seeded shuffle, without consulting scores or reference contents.',
                           'Old Luna vs new Astra differs in model, sample composition and output budget; it is descriptive, not a causal model improvement comparison.',
                           'A common denominator does not make B synthetic histories and C benchmark cases equally difficult.',
                           'No hypothesis, reference answer, evidence-session annotation or has_answer flag is supplied to the target.',
                           'Timeouts/errors are retained as missing; a dispatched job is never silently repeated.']}
    write(OUT / 'protocol.json', protocol, exclusive=True)
    write(OUT / 'freeze-receipt.json', {'frozen_at_utc': now(), 'protocol_sha256': sha(OUT / 'protocol.json'),
                                     'subset_sha256': protocol['subset_sha256'], 'model_calls': 0}, exclusive=True)
    print(json.dumps({'protocol': str(OUT / 'protocol.json'), 'case_count': 16,
                      'planned_target_calls': 192, 'quotas': QUOTAS, 'selected_ids': [r['case_id'] for r in selection]}))


def worker(index):
    # Container execution sees the host-frozen sources read-only.
    directory = CONTAINER_OUT
    protocol = load(directory / 'protocol.json')
    receipt = load(directory / 'freeze-receipt.json')
    if sha(directory / 'protocol.json') != receipt['protocol_sha256']:
        raise RuntimeError('Frozen protocol changed.')
    if sha(directory / 'selected-source.json') != protocol['subset_sha256']:
        raise RuntimeError('Frozen source subset changed.')
    if sha(Path(__file__)) != protocol['script_sha256']:
        raise RuntimeError('Collector wrapper changed.')
    for relative, expected in protocol['application_sha256'].items():
        app_path = Path('/app') / Path(relative).relative_to('backend')
        if sha(app_path) != expected:
            raise RuntimeError('Application changed after freeze.')
    job = protocol['jobs'][index]
    raw = next(r for r in load(directory / 'selected-source.json') if r['question_id'] == job['case_id'])
    from app.benchmarks.live import LiveBenchmarkRunner
    from app.schemas.benchmark import LiveBenchmarkRequest
    from app.target_ai import providers
    from app.target_ai.providers import HttpTargetAIConnector, single_attempt_target_request
    providers._REQUEST_TIMEOUT_SECONDS = protocol['target_timeout_seconds']
    original = HttpTargetAIConnector.execute
    captured = []

    def observe(connector, test, audit):
        if test.expected_behavior or test.supporting_memory_ids:
            raise RuntimeError('Gold entered target boundary; refusing dispatch.')
        response = original(connector, test, audit)
        record = response.model_dump(mode='json')
        captured.append(record)
        print(json.dumps({'event': 'target_returned', 'job_id': job['job_id'], 'response': record}), flush=True)
        return response

    HttpTargetAIConnector.execute = observe
    request = LiveBenchmarkRequest(payload=[raw], source_authorised=True,
                source_label='Frozen 16-case C Astra retest; official Oracle subset',
                dataset_provenance={'dataset_version': 'longmemeval-cleaned oracle ' + protocol['source']['commit'],
                                    'license': 'MIT per pinned official dataset card',
                                    'citation': 'LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory, arXiv:2410.10813'},
                provider=protocol['provider'], model=protocol['model'], strategies=[job['strategy']],
                random_seed=42, temperature=0, target_memory_capacity=protocol['target_memory_capacity'],
                target_memory_profile=protocol['target_memory_profile'], max_cases=1,
                include_mem0=False, native_repair_comparison=False)
    try:
        with single_attempt_target_request():
            result = LiveBenchmarkRunner().run(request).model_dump(mode='json')
        case = result['conditions'][0]['cases'][0]
        meta = case['execution_metadata']
        if meta.get('reported_model') != 'gpt-6-astra' or meta.get('requested_reasoning_effort') != 'max':
            raise RuntimeError('Target model/effort receipt mismatch.')
        if meta.get('request_attempts') != 1 or meta.get('requested_output_token_limit') != 8192:
            raise RuntimeError('Attempt/output budget receipt mismatch.')
        print(json.dumps({'event': 'result', 'job_id': job['job_id'], 'status': 'completed',
                          'job': job, 'result': result}), flush=True)
    except Exception as exc:
        print(json.dumps({'event': 'result', 'job_id': job['job_id'], 'status': 'failed', 'job': job,
                          'error_type': type(exc).__name__, 'http_status': getattr(exc, 'status_code', None),
                          'target_execution': getattr(exc, 'target_execution', None),
                          'captured_answer_count': len(captured)}), flush=True)
        return 1
    return 0


def execute():
    protocol = load(OUT / 'protocol.json')
    receipt = load(OUT / 'freeze-receipt.json')
    if sha(OUT / 'protocol.json') != receipt['protocol_sha256'] or sha(Path(__file__)) != protocol['script_sha256']:
        raise RuntimeError('Frozen wrapper/protocol changed.')
    stop = threading.Event()
    lock = threading.Lock()
    def one(pair):
        index, job = pair
        dest = OUT / 'responses' / (job['job_id'] + '.json')
        if dest.exists():
            return {'job_id': job['job_id'], 'status': 'prior_attempt_retained'}
        if stop.is_set():
            return {'job_id': job['job_id'], 'status': 'not_dispatched_auth_halt'}
        raw_path = OUT / 'raw' / (job['job_id'] + '.jsonl')
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        state = {'job_id': job['job_id'], 'job': job, 'status': 'dispatched', 'dispatched_at_utc': now(),
                 'protocol_sha256': receipt['protocol_sha256']}
        write(dest, state, exclusive=True)
        cmd = ['docker', 'compose', 'exec', '-T', 'backend', 'python', '/scripts/bc_retest_c_20261101.py', '--worker', str(index)]
        with raw_path.open('x', encoding='utf8') as stdout, (raw_path.with_suffix('.stderr')).open('x', encoding='utf8') as stderr:
            process = subprocess.run(cmd, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=480)
        events = []
        for line in raw_path.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        results = [e for e in events if e.get('event') == 'result']
        if results:
            state.update(results[-1])
        else:
            state.update(status='ambiguous_worker_exit', error_type='worker_did_not_return_result')
        state.update(completed_at_utc=now(), worker_exit_code=process.returncode,
                     raw_sha256=sha(raw_path), captured_target_responses=[e['response'] for e in events if e.get('event') == 'target_returned'])
        write(dest, state)
        failure = state.get('target_execution') or {}
        if failure.get('last_http_status') in {401, 403}:
            stop.set()
        with lock:
            print(json.dumps({'job_id': job['job_id'], 'status': state['status'], 'case_id': job['case_id'],
                              'strategy': job['strategy'], 'repeat': job['repeat']}), flush=True)
        return {'job_id': job['job_id'], 'status': state['status']}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(one, pair) for pair in enumerate(protocol['jobs'])]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                print(json.dumps({'event': 'collector_error', 'error_type': type(exc).__name__}), flush=True)
    summarize()


def summarize():
    protocol = load(OUT / 'protocol.json')
    states = [load(p) for p in sorted((OUT / 'responses').glob('*.json'))]
    summary = {'format': 'bc-c-collection-summary-v2', 'generated_at_utc': now(),
               'protocol_sha256': sha(OUT / 'protocol.json'), 'planned_answers': 192,
               'status_counts': dict(Counter(s['status'] for s in states)),
               'by_strategy': {}, 'review_status': 'pending_independent_reviews_and_human_confirmation',
               'warning': 'Lexical matches below are an exploratory proxy, not source-grounded answer correctness.'}
    for strategy in STRATEGIES:
        entries = [s for s in states if s['job']['strategy'] == strategy]
        good = [s for s in entries if s['status'] == 'completed']
        summary['by_strategy'][strategy] = {'planned': 48, 'completed': len(good), 'missing': 48-len(good),
             'lexical_matches_only': sum(s['result']['conditions'][0]['cases'][0]['lexical_match'] for s in good),
             'per_repeat': [{'repeat': rep, 'completed': sum(s['job']['repeat']==rep for s in good),
                            'planned': 16} for rep in range(1,4)]}
    write(OUT / 'collection-summary.json', summary)
    source = {r['question_id']: r for r in load(OUT / 'selected-source.json')}
    blinded = []
    keys = []
    for state in states:
        if state['status'] != 'completed':
            continue
        job = state['job']; case = state['result']['conditions'][0]['cases'][0]
        raw = source[job['case_id']]
        rid = sha_bytes((str(SEED)+':blind:'+job['job_id']).encode())[:16]
        history = []
        for si, session in enumerate(raw['haystack_sessions']):
            for mi, message in enumerate(session):
                history.append({'message_id': f'S{si+1}-M{mi+1}', 'source_session_date': raw['haystack_dates'][si],
                                'role': message.get('role'), 'content': message.get('content')})
        blinded.append({'review_id': rid, 'source_messages': history, 'question': raw['question'],
                        'question_date': raw.get('question_date'), 'benchmark_reference': str(raw['answer']),
                        'response': case['response_text'], 'reference_validity': None,
                        'answer_verdict': None, 'reason': None, 'supporting_message_ids': []})
        keys.append({'review_id': rid, **job, 'result_path': str((REL/'responses'/(job['job_id']+'.json')))})
    random.Random(SEED + 2).shuffle(blinded)
    material = {'format': 'bc-c-blind-answer-review-v2', 'source': 'Pinned LongMemEval Oracle subset; all source statements shown without has_answer flags.',
                'instructions': 'Independently verify the reference against source messages, then judge the answer for factual correctness and sufficient response to the question. Accept semantic equivalence and safe justified abstention; reject contradictions/unsupported concrete claims. Label invalid/ambiguous references separately. Do not infer accuracy from wording overlap. Leave genuinely unresolved judgments uncertain.',
                'review_declaration': {'reviewer': None, 'reviewer_kind': None, 'completed_independently': None,
                                       'has_seen_automatic_scores_or_policy_labels': False, 'completed_by_human': False},
                'items': blinded}
    for slot in [1,2]:
        write(OUT / f'reviewer-{slot}.blank.json', {**material, 'reviewer_slot': slot})
    write(OUT / 'private-review-key.json', {'format': 'bc-c-private-review-key-v2', 'mapping': keys})
    print(json.dumps(summary), flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--prepare', action='store_true'); g.add_argument('--execute', action='store_true')
    g.add_argument('--summarize', action='store_true'); g.add_argument('--worker',type=int)
    a=p.parse_args()
    if a.prepare: prepare()
    elif a.execute: execute()
    elif a.summarize: summarize()
    else: return worker(a.worker)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
