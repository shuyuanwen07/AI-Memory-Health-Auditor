"""Real Luna API engineering smoke, isolated from the operational database.

Reuses prior user approval of the SHA-bound synthetic release, never produces
independent human research labels. Every request and partial failure is saved.
Run in backend container: python /scripts/smoke_luna_isolated_api.py --output /tmp/report.json
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
MODEL = 'openai/gpt-6-luna'


def completed_workflow_status(report):
    """A human-approved inventory cannot turn failed Agent stages into passes."""
    required = {'memory_extraction', 'relationship_analysis', 'independent_memory_review'}
    agents = report.get('extraction_agents', [])
    if (not required.issubset({a['role'] for a in agents})
            or any(a['status'] != 'completed' for a in agents)):
        return 'partial_extraction_failure'
    if not report.get('runs') or any(r.get('diagnostic_agent_status_code') != 200 for r in report['runs']):
        return 'partial_diagnostic_failure'
    return 'completed'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, help='Optional synthetic-only SQLite backup before disposable cleanup')
    parser.add_argument('--repetitions', type=int, choices=(1, 2, 3), default=1,
                        help='Predeclare repetitions per policy; all reuse one frozen suite')
    args = parser.parse_args()
    source_path = ROOT / 'datasets/smoke/qwen-four-dimension-source-v1.json'
    approval_path = ROOT / 'datasets/smoke/qwen-four-dimension-approval-v1.json'
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    approval = json.loads(approval_path.read_text())
    digest = hashlib.sha256(source_bytes).hexdigest()
    source_ids = [m['message_id'] for m in source['messages']]
    approved_source_ids = approval['confirmed_source_message_ids']
    if (len(source_ids) != len(set(source_ids)) or len(approved_source_ids) != len(set(approved_source_ids))
            or approval['source_sha256'] != digest or source['source_origin'] != 'synthetic'
            or source['authorised'] is not True
            or approval['approval_scope'] != 'synthetic_engineering_smoke_only'
            or set(approval['confirmed_source_message_ids']) != {m['message_id'] for m in source['messages']}):
        raise ValueError('Requires exact approved synthetic release')
    report = {'scope': 'synthetic_isolated_api_e2e_engineering_only', 'research_evidence': False,
              'source_sha256': digest, 'approval_sha256': hashlib.sha256(approval_path.read_bytes()).hexdigest(),
              'approval_basis': approval['approval_basis'], 'provider': 'openrouter', 'model': MODEL,
              'production_database_writes': 0, 'database': 'new disposable SQLite file before app import',
              'planned_repetitions_per_strategy': args.repetitions,
              'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'running', 'requests': [], 'runs': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='mha-luna-isolated-') as directory:
        # This process creates its sole application engine only after isolation.
        # No operational database engine or application session is constructed.
        os.environ['DATABASE_URL'] = f'sqlite:///{directory}/smoke.db'
        os.environ['AUTO_CREATE_SCHEMA'] = 'true'
        os.environ['AUDITOR_ACCESS_MODE'] = 'local'
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database.session import engine
        from app.services.runtime_freeze import audit_runtime_signature
        report['runtime_signature'] = audit_runtime_signature()
        try:
            with TestClient(app) as client:
                def request(method, path, payload=None, expected=(200, 201, 204)):
                    print(json.dumps({'event': 'dispatch', 'method': method, 'path': path}), flush=True)
                    started = datetime.now(timezone.utc)
                    response = client.request(method, '/api/v1' + path, json=payload) if payload is not None else client.request(method, '/api/v1' + path)
                    kind = response.headers.get('content-type', '')
                    body = response.json() if response.content and 'json' in kind else response.text
                    report['requests'].append({'method': method, 'path': path, 'status_code': response.status_code,
                        'elapsed_ms': (datetime.now(timezone.utc) - started).total_seconds() * 1000, 'body': body})
                    save()
                    print(json.dumps({'event': 'response', 'path': path, 'status_code': response.status_code}), flush=True)
                    if response.status_code not in expected:
                        raise RuntimeError(f'API {method} {path}: HTTP {response.status_code}')
                    return body
                conversation = request('POST', '/conversations', {k: source[k] for k in ('authorised', 'source_origin', 'messages')})
                cid = conversation['conversation_id']
                report['conversation_id'] = cid
                extracted = request('POST', f'/conversations/{cid}/extract', {'provider': 'openrouter', 'model': MODEL})
                report['extracted_candidates'] = extracted
                report['extraction_agents'] = request('GET', f'/conversations/{cid}/agent-executions')
                for candidate in extracted:
                    request('DELETE', f"/memories/{candidate['memory_id']}")
                approved_ids = {}
                for message in source['messages']:
                    memory = request('POST', '/memories', {'conversation_id': cid, 'canonical_value': message['content'],
                        'source_message_ids': [message['message_id']], 'timestamp': message['timestamp']})
                    approved_ids[message['message_id']] = memory['memory_id']
                for edge in approval['relationships']:
                    request('PATCH', f"/memories/{approved_ids[edge['source_message_id']]}", {'relationships': [{
                        'type': edge['type'], 'target_memory_id': approved_ids[edge['target_message_id']],
                        'evidence_message_ids': [edge['source_message_id'], edge['target_message_id']]}]})
                confirmed = request('POST', f'/conversations/{cid}/confirm-ground-truth', {'confirmed_memory_ids': list(approved_ids.values())})
                report['confirmation'] = {'kind': 'prior exact-source approval reused via supported reject/add/patch/confirm API',
                    'new_human_research_annotation': False, 'inventory': [m for m in confirmed if m['status'] in ('confirmed', 'edited')]}
                roles = {'pipeline_provider': 'openrouter', 'pipeline_model': MODEL, 'semantic_review_provider': 'openrouter',
                         'semantic_review_model': MODEL, 'evaluator_provider': 'openrouter', 'evaluator_model': MODEL}
                experiment = request('POST', '/experiments', {'conversation_id': cid, 'label': 'Isolated Luna engineering smoke only',
                    'test_suite_configuration': {**roles, 'test_budget': 4, 'random_seed': 42}})
                eid = experiment['experiment_id']
                report['experiment_id'] = eid
                for repetition, strategy in ((n, policy) for n in range(1, args.repetitions + 1)
                                             for policy in ('weak_first_hit', 'strong_rule_based')):
                    audit = request('POST', '/audits', {'conversation_id': cid, 'experiment_id': eid,
                        'target_configuration': 'strong', 'provider': 'openrouter', 'model': MODEL, **roles,
                        'test_budget': 4, 'random_seed': 42, 'temperature': 0, 'memory_strategy': strategy,
                        'memory_maintenance_policy': 'append_only', 'target_memory_writer': 'rule_based',
                        'target_system_adapter': 'controlled-memory', 'retrieval_mode': 'fixed'})
                    run = {'strategy': strategy, 'repetition': repetition,
                           'run_id': audit['run_id'], 'configuration': audit}
                    report['runs'].append(run)
                # Freeze complete experiment membership before generating its shared suite.
                for run in report['runs']:
                    rid = run['run_id']
                    suite = request('POST', f'/audits/{rid}/generate-tests')
                    if len(suite) != 4 or {t['dimension'] for t in suite} != {'accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'}:
                        raise ValueError('Suite does not contain exactly the four required dimensions')
                    run['tests'] = suite
                    run['responses'] = request('POST', f'/audits/{rid}/execute')
                    run['evaluations'] = request('POST', f'/audits/{rid}/evaluate')
                    run['result'] = request('GET', f'/audits/{rid}/results')
                    run['memory_trace'] = request('GET', f'/audits/{rid}/target-memory-trace')
                    run['diagnosis'] = request('GET', f'/audits/{rid}/diagnosis')
                    run['diagnostic_agent'] = request('POST', f'/audits/{rid}/diagnostic-agent', expected=(200, 502))
                    run['diagnostic_agent_status_code'] = report['requests'][-1]['status_code']
                    run['agents'] = request('GET', f'/audits/{rid}/agent-executions')
                    save()
                bundle = request('GET', f'/experiments/{eid}/reproducibility-bundle.json')
                csv_text = request('GET', f'/experiments/{eid}/export.csv')
                rows = list(csv.DictReader(io.StringIO(csv_text)))
                answer_rows = [row for row in rows if row['record_type'] == 'answer']
                exported_answers = [answer for run in bundle['runs'] for answer in run['answers']]
                actual_evaluations = {e['evaluation_id'] for r in report['runs'] for e in r['evaluations']}
                if {a['evaluation_id'] for a in exported_answers} != actual_evaluations or {r['evaluation_id'] for r in answer_rows} != actual_evaluations:
                    raise ValueError('JSON/CSV evaluation identities do not reconcile')
                report['export_reconciliation'] = {'passed': True, 'json_answer_count': len(exported_answers),
                    'csv_answer_count': len(answer_rows), 'evaluation_count': len(actual_evaluations),
                    'csv_sha256': hashlib.sha256(csv_text.encode()).hexdigest()}
                report['export_bundle'] = bundle
                for suffix, content in (('.bundle.json', json.dumps(bundle, indent=2)), ('.csv', csv_text)):
                    args.output.with_suffix(suffix).write_text(content)
                report['core_api_status'] = 'completed'
                report['status'] = completed_workflow_status(report)
        except Exception as exc:
            report.update(status='failed', error_code=type(exc).__name__, error=str(exc))
        finally:
            engine.dispose()
            if args.snapshot:
                import sqlite3
                origin = sqlite3.connect(f'file:{directory}/smoke.db?mode=ro', uri=True)
                destination = sqlite3.connect(str(args.snapshot))
                origin.backup(destination)
                destination.close()
                origin.close()
                report['synthetic_only_sqlite_snapshot'] = str(args.snapshot)
                report['snapshot_sha256'] = hashlib.sha256(args.snapshot.read_bytes()).hexdigest()
            report['finished_at'] = datetime.now(timezone.utc).isoformat()
            report['disposable_database_removed'] = False
            save()
    report['disposable_database_removed'] = not Path(directory).exists()
    if not report['disposable_database_removed']:
        report.update(status='failed', error_code='IsolationCleanupError')
    save()
    print(json.dumps({'status': report['status'], 'runs': len(report['runs']), 'report': str(args.output)}), flush=True)
    return 0 if report['status'] == 'completed' else 1

if __name__ == '__main__':
    raise SystemExit(main())
