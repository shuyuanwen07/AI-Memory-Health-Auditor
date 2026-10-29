"""Bind a staged test to an exact OpenRouter request before a future dispatch.

This observer is not a release mechanism. The caller must hold the full audit,
source and review locks, verify the frozen suite, and manage the durable attempt
outcome. The current production AC3 bridge remains unconditionally disabled.
"""
from app.schemas import TargetProvider
from app.target_ai.providers import target_instructions, target_output_limit
from app.target_ai.request_contracts import request_contract_sha256
from app.target_ai.rule_based import target_question_input
from scripts.ac3_fixed_suite_adapter import sha


class AC3RequestBinding:
    def __init__(self, ledger, scope, frozen_sha256, request_key, test, audit, *, frozen_test_id):
        if audit.provider != TargetProvider.OPENROUTER or test.run_id != audit.run_id:
            raise ValueError('Test and OpenRouter audit do not match')
        if not isinstance(frozen_test_id, str) or not frozen_test_id.strip():
            raise ValueError('The frozen question identity is required')
        expected_id = 'AC3' + sha(f'{frozen_sha256}|{audit.run_id}|{frozen_test_id}'.encode())[:32].upper()
        if test.test_id != expected_id:
            raise ValueError('Staged test identity does not match the frozen question')
        self.ledger, self.scope, self.frozen_sha256, self.request_key = ledger, scope, frozen_sha256, request_key
        # Receipts use the frozen identity, not the per-audit generated DB ID.
        self.test_id, self.model = frozen_test_id, audit.model
        self.max_output = target_output_limit(audit)
        self.messages_sha = request_contract_sha256([
            {'role': 'system', 'content': target_instructions(test, audit)},
            {'role': 'user', 'content': target_question_input(test.prompt)},
        ])
        self.bound = False

    def __call__(self, receipt):
        if receipt.get('phase') != 'before_send':
            return
        contract = receipt.get('request_contract') or {}
        maximum = contract.get('max_tokens') or {}
        if (self.bound or receipt.get('attempt_index') != 1 or contract.get('role') != 'target_answer'
            or contract.get('provider_name') != 'openrouter' or contract.get('model') != self.model
            or contract.get('messages_sha256') != self.messages_sha
            or maximum.get('present') != (self.max_output is not None)
            or (self.max_output is not None and maximum.get('value') != self.max_output)
            or receipt.get('request_contract_sha256') != request_contract_sha256(contract)):
            raise ValueError('Request differs from the bound staged test or is a retry')
        result = self.ledger.begin(self.scope, self.frozen_sha256, self.request_key,
                                   receipt['request_contract_sha256'], self.test_id)
        if result.get('duplicate') or result.get('state') != 'dispatched':
            raise ValueError('Attempt already recorded; do not send again')
        self.bound = True
