"""Explicitly disabled bridge to the existing OpenRouter target connector.

This wiring is not a release mechanism. Until a real persistent budget guard,
provider cost bounds and locked prospective-review checks exist, the observer
vetoes every HTTP attempt before it reaches httpx. No API imports this module.
"""
from app.schemas import TargetProvider
from app.target_ai.providers import HttpTargetAIConnector, single_attempt_target_request
from app.target_ai.request_contracts import observe_request_contracts


class AC3DispatchBlocked(RuntimeError):
    pass


def _deny_every_http_attempt(receipt):
    if receipt.get('phase') == 'before_send':
        raise AC3DispatchBlocked('AC3 live execution is disabled: verified frozen review and real budget guard are not connected')


def execute_through_blocked_ac3_bridge(test, audit):
    """Exercise existing connector wiring with a non-overridable pre-send veto.

    This is deliberately fail-closed, including for apparently reviewed inputs.
    It must not be used to call local/other providers because the current
    OpenRouter-only observer would not intercept those transports.
    """
    if audit.provider != TargetProvider.OPENROUTER:
        raise AC3DispatchBlocked('Only the blocked OpenRouter connector can be inspected')
    with single_attempt_target_request(), observe_request_contracts(_deny_every_http_attempt):
        return HttpTargetAIConnector().execute(test, audit)
