"""Collect locked, source-bound inputs and replay both AC3 evaluators offline."""
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AuditRunModel, MemoryModel, TargetResponseModel, TestCaseModel
from app.schemas import TargetResponse
from app.services.ac3_locked_preflight import ac3_sequence_locks
from app.services.ac3_paired_locked_preflight import locked_paired_preflight
from app.services.ac3_paired_replay_pair import replay_pair
from app.services.ac3_paired_target_export import collect_paired_targets
from scripts.ac3_paired_replay_collection import collect_paired_replays
from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_reference_stage import compile_reference_stage


def collect_paired_scores(engine, *, ledger, frozen, source, plan, reviews, components,
                          history_conversations, history_runs, scope, judge):
    """Use settled receipts and identical saved answers; never call a provider.

    The output is private automatic scoring, not independently judged truth.
    Missing or unresolved receipts prevent an export instead of being omitted.
    """
    kwargs = dict(ledger=ledger, frozen=frozen, source=source, plan=plan, reviews=reviews,
                  components=components, history_conversations=history_conversations,
                  history_runs=history_runs, scope=scope)
    targets = collect_paired_targets(engine, **kwargs)
    frozen_sha = hashlib.sha256(canonical(frozen)).hexdigest()
    stage = compile_reference_stage(frozen, source, plan, reviews, components)
    answers = {item['test_id']: item for item in targets['answers']}
    from app.api.routes import memory_schema, test_schema
    inputs = []
    with Session(engine) as db, ac3_sequence_locks(db, history_runs):
        with locked_paired_preflight(db, frozen, source, plan, reviews, components,
                                     history_conversations, history_runs):
            budget = db.execute(text('SELECT * FROM ac3_paired_budget_scopes WHERE scope_id=:scope FOR UPDATE'),
                                {'scope': scope}).mappings().first()
            if (not budget or budget['status'] != 'active' or budget['frozen_sha256'] != frozen_sha
                    or budget['budget_sha256'] != ledger.budget_sha256):
                raise ValueError('Study budget is missing, changed or unresolved')
            rows = [dict(row) for row in db.execute(text("SELECT * FROM ac3_paired_budget_receipts "
                "WHERE scope_id=:scope ORDER BY test_id,role FOR UPDATE"), {'scope': scope}).mappings()]
            receipts = {}
            for row in rows:
                key = (row['test_id'], row['role'])
                if key in receipts:
                    raise ValueError('Duplicate study receipt')
                receipts[key] = row
            expected = {(q['test_id'], role) for q in stage['questions'] for role in ('target', 'scorer')}
            if set(receipts) != expected:
                raise ValueError('Every frozen question needs both receipts')
            for question in stage['questions']:
                ident = question['test_id']; run_id = history_runs[question['history_id']]
                target = receipts[(ident, 'target')]; scorer = receipts[(ident, 'scorer')]
                recorded = answers[ident]; raw_evidence = target.get('request_evidence_json')
                if (target['status'] != 'settled' or scorer['status'] != 'settled'
                        or target['response_text'] != recorded['answer']
                        or target['request_key'] != recorded['request_key']
                        or not isinstance(raw_evidence, str)
                        or hashlib.sha256(raw_evidence.encode()).hexdigest() != target['request_evidence_sha256']):
                    raise ValueError('Target or scorer evidence changed or remains unresolved')
                evidence = json.loads(raw_evidence)
                if evidence.get('frozen_test_id') != ident or evidence.get('run_id') != run_id:
                    raise ValueError('Target evidence identifies another question or run')
                local_id = 'AC3' + hashlib.sha256(f'{frozen_sha}|{run_id}|{ident}'.encode()).hexdigest()[:32].upper()
                response_id = 'ACR' + hashlib.sha256(f"{scope}|{target['request_key']}".encode()).hexdigest()[:32].upper()
                audit = db.get(AuditRunModel, run_id); test = db.get(TestCaseModel, local_id)
                saved = list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.test_id == local_id)))
                if (not audit or not test or test.run_id != run_id or len(saved) != 1
                        or saved[0].id != response_id or saved[0].run_id != run_id
                        or saved[0].response_text != recorded['answer']
                        or (saved[0].execution_metadata or {}).get('ac3_paired_request_evidence_sha256') != target['request_evidence_sha256']):
                    raise ValueError('Saved answer differs from its settled target receipt')
                answer = TargetResponse(response_id=saved[0].id, test_id=local_id, run_id=run_id,
                    response_text=saved[0].response_text, model=saved[0].model, temperature=saved[0].temperature,
                    created_at=saved[0].created_at or datetime.now(timezone.utc))
                memories = [memory_schema(db, row) for row in db.scalars(select(MemoryModel)
                            .where(MemoryModel.conversation_id == audit.conversation_id).order_by(MemoryModel.id))]
                inputs.append((test_schema(test), answer, memories, question, scorer))
    replays = [replay_pair(frozen, components, judge, test, answer, memories, question, receipt,
                           scope=scope, frozen_test_id=question['test_id'])
               for test, answer, memories, question, receipt in inputs]
    return collect_paired_replays(frozen, targets, replays)
