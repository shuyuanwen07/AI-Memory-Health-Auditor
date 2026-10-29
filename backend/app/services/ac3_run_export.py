"""Read-only bridge from settled receipts and saved assessments to AC3 blind review.

This does not run a model or authorize a study. Callers must supply a digest-bound
receipt export; provider reports and timestamps remain independently unverified.
"""
from datetime import datetime, timezone  # noqa: F401
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from sqlalchemy import select
from app.models import AuditRunModel, TestCaseModel, TargetResponseModel, EvaluationResultModel
from app.services.formal_freeze import formal_input_signature
from scripts.ac3_database_mapping import compile_database_stage
from scripts.ac3_fixed_suite_adapter import sha
from scripts.analyze_ac3_heldout import _read_bound, _time
from app.services.ac3_metrics import _review
from scripts.ac3_rehearsal_workflow import _write_new_json


def build_heldout_run(db, frozen_path, frozen_sha256, receipt_path, receipt_sha256,
                      reservation, history_conversations, history_runs):
    """Match exactly one saved response and automatic result to each settled receipt."""
    if db.new or db.dirty or db.deleted:
        raise ValueError('A clean read-only session is required')
    frozen = _read_bound(frozen_path, frozen_sha256)
    receipts = _read_bound(receipt_path, receipt_sha256)
    if (receipts.get('format') != 'ac3-settled-receipts-v1' or receipts.get('frozen_sha256') != frozen_sha256 or
        receipts.get('reported_cost_status') != 'provider_report_unreconciled'):
        raise ValueError('Receipt export does not bind to the frozen suite')
    plan = compile_database_stage(db, Path(frozen_path), frozen_sha256, reservation, history_conversations)
    eligible = {item['test_id']: item for item in plan['items'] if item['grounding_review'] == 'valid'}
    rows = receipts.get('responses')
    if (not isinstance(rows, list) or not eligible or len(rows) != len(eligible) or
        receipts.get('receipt_count') != len(rows) or len({r.get('test_id') for r in rows}) != len(rows) or
        {r.get('test_id') for r in rows} != set(eligible)):
        raise ValueError('Receipts must cover every eligible question exactly once')
    keys = [row.get('request_key') for row in rows]
    if any(not isinstance(key, str) or not key.strip() for key in keys) or len(set(keys)) != len(keys):
        raise ValueError('Each receipt must bind a distinct request')
    for row in rows:
        if not isinstance(row.get('contract_sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', row['contract_sha256']):
            raise ValueError('Receipt request contract digest is invalid')
        if not isinstance(row.get('reported_cost_usd'), str):
            raise ValueError('Receipt provider cost is missing')
        try:
            cost = Decimal(row['reported_cost_usd'])
        except InvalidOperation as exc:
            raise ValueError('Receipt provider cost is invalid') from exc
        if not cost.is_finite() or cost < 0:
            raise ValueError('Receipt provider cost is invalid')
    histories = {item['history_id'] for item in eligible.values()}
    if (not isinstance(history_runs, dict) or set(history_runs) != histories or
        set(history_conversations) != histories or len(set(history_runs.values())) != len(histories)):
        raise ValueError('Distinct saved audits are required for each history')
    cfg = plan['model_configuration']
    evaluator_version = cfg.get('evaluator_implementation_version')
    if not isinstance(evaluator_version, str) or not evaluator_version.strip():
        raise ValueError('Frozen evaluator implementation version is required')
    if cfg['evaluator_provider'] == 'rule_based':
        from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
        if evaluator_version != RuleBasedBehaviourEvaluator.VERSION:
            raise ValueError('Frozen evaluator implementation differs from installed implementation')
    pipeline_version = cfg.get('pipeline_implementation_version')
    if not isinstance(pipeline_version, str) or not pipeline_version.strip():
        raise ValueError('Frozen pipeline implementation version is required')
    if cfg['pipeline_provider'] == 'rule_based':
        from app.test_generator.rule_based import RuleBasedTestGenerator
        if pipeline_version != RuleBasedTestGenerator.VERSION:
            raise ValueError('Frozen pipeline implementation differs from installed implementation')
    result, starts = [], []
    with db.no_autoflush:
        for row in rows:
            item = eligible[row['test_id']]
            history = item['history_id']
            run_id = history_runs[history]
            run = db.get(AuditRunModel, run_id, populate_existing=True)
            if not run or run.conversation_id != history_conversations[history]:
                raise ValueError('Saved audit does not match source history')
            if any(getattr(run, key) != cfg[value] for key, value in (
                ('provider','target_provider'), ('model','target_model'),
                ('evaluator_provider','evaluator_provider'), ('evaluator_model','evaluator_model'),
                ('pipeline_provider','pipeline_provider'), ('pipeline_model','pipeline_model'),
                ('memory_strategy','target_strategy'))):
                raise ValueError('Saved audit configuration differs from frozen protocol')
            metadata = (run.reproducibility_metadata or {}).get('ac3_staged_suite') or {}
            if metadata.get('frozen_sha256') != frozen_sha256 or metadata.get('history_id') != history or metadata.get('input_sha256') != formal_input_signature(db, run):
                raise ValueError('Saved audit input fingerprint differs from staged source')
            local_id = 'AC3' + sha(f"{frozen_sha256}|{run_id}|{row['test_id']}".encode())[:32].upper()
            test = db.get(TestCaseModel, local_id, populate_existing=True)
            if (not test or test.run_id != run_id or test.prompt != item['question'] or
                test.expected_behavior != item['expected_behavior'] or test.dimension != item['dimension'] or
                test.supporting_memory_ids != item['supporting_memory_ids']):
                raise ValueError('Saved test differs from frozen question')
            matches = list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.test_id == local_id)))
            if len(matches) != 1 or matches[0].run_id != run_id or matches[0].response_text != row.get('response_text') or matches[0].model != cfg['target_model']:
                raise ValueError('Saved response does not match exactly one settled receipt')
            evaluations = list(db.scalars(select(EvaluationResultModel).where(EvaluationResultModel.response_id == matches[0].id)))
            if len(evaluations) != 1 or evaluations[0].test_id != local_id or evaluations[0].evaluator != evaluator_version:
                raise ValueError('Exactly one matching configured automatic evaluation is required')
            evaluation = evaluations[0]
            verdict = 'uncertain' if evaluation.passed is None else ('pass' if evaluation.passed is True else 'fail')
            automatic = {'verdict': verdict, 'failure_dimension': evaluation.failure_type}
            _review(automatic, automatic=True)
            dispatched = _time(row['dispatched_at_utc'])
            if dispatched <= _time(frozen['frozen_at_utc']):
                raise ValueError('Receipt dispatch predates frozen protocol')
            starts.append(dispatched)
            response = matches[0].response_text
            result.append({'test_id': row['test_id'], 'history_id': history, 'response': response,
                           'response_sha256': sha(response.encode()), 'automatic': automatic})
    if sha(Path(frozen_path).read_bytes()) != frozen_sha256 or sha(Path(receipt_path).read_bytes()) != receipt_sha256:
        raise ValueError('Evidence changed during export')
    return {'format': 'ac3-heldout-run-export-v1', 'frozen_path': str(Path(frozen_path).resolve()),
            'frozen_sha256': frozen_sha256, 'started_at_utc': min(starts).astimezone(timezone.utc).isoformat(),
            'receipts_sha256': receipt_sha256, 'responses': result,
            'provenance_limitations': 'Saved provider cost and dispatch clock are not independently authenticated; '
                                      'no human outcome review is implied.'}


def export_heldout_run(db, frozen_path, frozen_sha256, receipt_path, receipt_sha256,
                       reservation, history_conversations, history_runs, output_path):
    """Write a new private export after validating all records, without overwriting."""
    run = build_heldout_run(db, frozen_path, frozen_sha256, receipt_path, receipt_sha256,
                            reservation, history_conversations, history_runs)
    return {'output_sha256': _write_new_json(Path(output_path), run),
            'response_count': len(run['responses']), 'human_outcome_reviewed': False}
