"""Source-bound retry diagnostic on three saved AC1 extraction outputs.

This is a development check on previously observed histories, not an
independent effectiveness experiment or evidence of edge correctness.
Each history has an exclusive started marker, so unknown outcomes are not
silently resent. A successful model response still requires human review.
"""
import hashlib
import json
import os
from pathlib import Path

from app.extraction.llm import PipelineLLMClient
from app.extraction.relationship_agent import RelationshipAnalysisAgent
from app.schemas import Memory
from app.target_ai.request_contracts import observe_request_contracts
from scripts.run_ac1_extraction import _conversation, exclusive_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TwoBoundedRequests:
    def __init__(self):
        self.count = 0
        self.receipts = []

    def __call__(self, receipt):
        if receipt.get('phase') == 'before_send':
            contract = receipt.get('request_contract') or {}
            if (self.count >= 2 or receipt.get('attempt_index') != 1
                    or contract.get('role') != 'relationship_analysis'
                    or contract.get('provider_name') != 'openrouter'
                    or contract.get('model') != 'openai/gpt-6-luna'):
                raise ValueError('Unexpected or repeated provider request blocked')
            self.count += 1
        elif receipt.get('phase') == 'after_send':
            self.receipts.append(receipt)


def main():
    source_path = Path('/output/proposal-delivery/ac1-ac2-source-only-2026-10-28-v3/reviewed-source.json')
    old = Path('/output/ac3-generated/AC1-RETEST-1a74cc906df755f6-6e728e21d728188f')
    out = Path('/ac3-results/ac1-relationship-retry-diagnostic-20261029-v1')
    runtime = Path('/app/app/extraction/relationship_agent.py')
    plan = json.loads((out/'protocol.json').read_bytes())
    if (plan['source_sha256'] != sha(source_path) or plan['implementation_sha256'] != sha(runtime)
            or plan['script_sha256'] != sha(Path(__file__))):
        raise ValueError('Frozen source, implementation or runner changed')
    source = json.loads(source_path.read_bytes())
    histories = {h['history_id']: h for h in source['histories']}
    for hid in plan['history_ids']:
        item_path = old/f'{hid}.result.json'
        if sha(item_path) != plan['original_results_sha256'][hid]:
            raise ValueError('Original extraction evidence changed')
        saved = json.loads(item_path.read_bytes())
        if saved['status'] != 'partial':
            raise ValueError('Diagnostic is limited to previously partial cases')
        started, result = out/f'{hid}.started.json', out/f'{hid}.result.json'
        if started.exists() or result.exists():
            raise FileExistsError('Existing or unknown attempt must not be resent')
        exclusive_json(started, {'history_id':hid, 'source_result_sha256':sha(item_path),
                                 'model':'openai/gpt-6-luna', 'protocol_sha256':sha(out/'protocol.json')})
        conversation = _conversation(histories[hid])
        memories = [Memory.model_validate(c) for c in saved['candidates']]
        guard = TwoBoundedRequests()
        agent = RelationshipAnalysisAgent(PipelineLLMClient('openrouter', 'openai/gpt-6-luna'))
        error = None
        try:
            with observe_request_contracts(guard):
                answer = agent.analyze(conversation, memories)
        except Exception as exc:
            answer = None
            error = {'type':type(exc).__name__, 'code':(agent.last_observation or {}).get('error_code')}
        output = {'history_id':hid, 'protocol_sha256':sha(out/'protocol.json'),
                  'status':'completed' if answer is not None else 'failed',
                  'relationships':answer['relationships'] if answer is not None else None,
                  'attempt_observations':agent.attempt_observations,
                  'request_receipts':guard.receipts, 'http_attempts':guard.count, 'error':error,
                  'semantic_validation':'pending independent human review',
                  'scope':'development check on previously observed synthetic histories'}
        exclusive_json(result, output)
        print(json.dumps({'history_id':hid,'status':output['status'],'http_attempts':guard.count,
                          'relationships':len(output['relationships'] or []),'error':error}), flush=True)


if __name__ == '__main__':
    main()
