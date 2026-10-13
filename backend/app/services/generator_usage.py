"""Observed generation usage, including failed operations and repair calls."""
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.assessor_observations import finite_sum


class PipelineReceipt(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)
    version: Literal['pipeline-http-meter-v1']
    provider: str
    model: str
    status: Literal['parsed', 'failed']
    request_attempts: int = Field(ge=0)
    failed_http_attempts: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0)
    reported_total_tokens: int | None = Field(default=None, ge=0, le=2**53-1)
    reported_cost_credits: float | None = Field(default=None, ge=0)


def generator_usage(run):
    history = (run.reproducibility_metadata or {}).get('generation_observations') or []
    counts = Counter(operation.get('operation_id') for operation in history)
    expected = sum(
        len(operation.get('attempts') or []) + len(operation.get('semantic_reviews') or [])
        for operation in history
    )
    unfinished = any(operation.get('status') == 'started' for operation in history)
    receipts = []
    reviewer_provider = getattr(run, 'semantic_review_provider', None) or run.pipeline_provider
    reviewer_model = getattr(run, 'semantic_review_model', None) or run.pipeline_model
    for operation in history:
        # An ambiguous operation identity cannot justify counting the same call
        # twice. Old unbound data remains visible as missing coverage.
        identity = operation.get('operation_id')
        if not identity or counts[identity] != 1:
            continue
        for attempt in operation.get('attempts') or []:
            try:
                receipt = PipelineReceipt.model_validate(attempt.get('http_execution'))
            except ValidationError:
                continue
            if (receipt.provider != run.pipeline_provider or receipt.model != run.pipeline_model
                    or receipt.failed_http_attempts > receipt.request_attempts):
                continue
            receipts.append(receipt)
        for review in operation.get('semantic_reviews') or []:
            try:
                receipt = PipelineReceipt.model_validate(review.get('http_execution'))
            except ValidationError:
                continue
            if (receipt.provider != reviewer_provider or receipt.model != reviewer_model
                    or receipt.failed_http_attempts > receipt.request_attempts):
                continue
            receipts.append(receipt)
    called = [receipt for receipt in receipts if receipt.request_attempts > 0]
    costs = [receipt.reported_cost_credits for receipt in called
             if receipt.provider == 'openrouter' and receipt.reported_cost_credits is not None]
    tokens = [receipt.reported_total_tokens for receipt in called if receipt.reported_total_tokens is not None]
    observed_cost = finite_sum(costs) if costs else None
    token_sum = sum(tokens) if tokens else None
    if token_sum is not None and token_sum > 2**53-1:
        token_sum = None
    return {
        'recorded_invocations': expected, 'receipt_count': len(receipts),
        'unfinished_operations': unfinished,
        'timed_invocations': len(called),
        'observed_elapsed_ms': finite_sum([receipt.elapsed_ms for receipt in called]) if called else None,
        'request_attempts': sum(receipt.request_attempts for receipt in receipts) if receipts else None,
        'failed_http_attempts': sum(receipt.failed_http_attempts for receipt in receipts) if receipts else None,
        'cost_reported_invocations': len(costs), 'observed_cost_credits': observed_cost,
        'complete_cost_coverage': bool(expected and not unfinished and len(costs) == expected
                                      and observed_cost is not None and all(
                                          receipt.request_attempts == 1 and receipt.failed_http_attempts == 0
                                          for receipt in receipts)),
        'token_reported_invocations': len(tokens), 'observed_total_tokens': token_sum,
        'scope': 'Saved generation invocations only, including failed generations, repairs and operator retries. '
                 'Counts include candidate-generation and semantic duplicate-review calls. '
                 'Time includes HTTP retry waits and parsing. Credits and tokens cover reported successful replies; '
                 'missing or failed-request usage remains unknown. No target execution or assessment usage included.',
    }
