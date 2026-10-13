"""Bounded observations from saved assessor receipts, never billing estimates."""
from collections import Counter
import math

from pydantic import ValidationError
from sqlalchemy import select

from app.models import EvaluationResultModel, TargetResponseModel, TestCaseModel
from app.schemas import JudgeExecutionEvidence


def finite_sum(values):
    try:
        value = math.fsum(values)
    except OverflowError:
        return None
    return value if math.isfinite(value) else None


def assessor_observations(db, run):
    tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run.id)).all()
    accepted = {test.id for test in tests if test.quality_status == 'accepted'}
    evaluations = db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id == run.id)).all()
    counts = Counter(row.test_id for row in evaluations)
    receipts = []
    bound = 0
    for row in evaluations:
        if row.test_id not in accepted or counts[row.test_id] != 1:
            continue
        response = db.get(TargetResponseModel, row.response_id)
        if not response or response.run_id != run.id or response.test_id != row.test_id:
            continue
        bound += 1
        try:
            receipt = JudgeExecutionEvidence.model_validate(row.judge_execution, strict=True)
        except ValidationError:
            continue
        if receipt.provider == run.evaluator_provider and receipt.model == run.evaluator_model:
            receipts.append(receipt)
    timed = [receipt for receipt in receipts if receipt.request_attempts > 0]
    costs = [receipt.reported_cost_credits for receipt in timed
             if receipt.provider == 'openrouter' and receipt.reported_cost_credits is not None]
    tokens = [receipt.reported_total_tokens for receipt in timed if receipt.reported_total_tokens is not None]
    elapsed = finite_sum([receipt.elapsed_ms for receipt in timed]) if timed else None
    observed_cost = finite_sum(costs) if costs else None
    return {
        'expected_answers':len(accepted), 'bound_assessments':bound,
        'receipt_count':len(receipts), 'timed_answers':len(timed),
        'mean_elapsed_ms':elapsed / len(timed) if elapsed is not None else None,
        'request_attempts':sum(receipt.request_attempts for receipt in receipts) if receipts else None,
        'failed_http_attempts':sum(receipt.failed_http_attempts for receipt in receipts) if receipts else None,
        'cost_reported_answers':len(costs), 'observed_cost_credits':observed_cost,
        'complete_cost_coverage':bool(accepted and observed_cost is not None and len(costs) == len(accepted)
                                      and all(receipt.request_attempts == 1 and receipt.failed_http_attempts == 0 for receipt in timed)),
        'token_reported_answers':len(tokens), 'observed_total_tokens':sum(tokens) if tokens else None,
        'scope':'Saved assessor operations only. Time includes retries and local validation. Tokens and credits cover reported successful HTTP replies; unreported or failed-request usage remains unknown.',
    }
