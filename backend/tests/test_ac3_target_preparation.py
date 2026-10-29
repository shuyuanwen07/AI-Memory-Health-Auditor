"""AC3 preparation must use the product's actual private memory retrieval."""
from app.target_ai.providers import target_instructions
from test_target_identity_integration import setup_target


def test_preparation_uses_actual_store_and_excludes_gold(monkeypatch):
    db, audit, test, adapter = setup_target(mode='off')
    calls = []
    original = adapter.store.retrieve
    def retrieve(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(adapter.store, 'retrieve', retrieve)
    from app.target_ai.providers import HttpTargetAIConnector
    monkeypatch.setattr(HttpTargetAIConnector, 'execute', lambda *_: (_ for _ in ()).throw(AssertionError('no provider call during preparation')))
    private, retrieval, identity = adapter.prepare_answer(test, audit)
    assert calls and calls[0][0][3].value == audit.memory_strategy
    assert retrieval.context and private.target_memory_context == retrieval.context
    assert private.expected_behavior == '' and private.supporting_memory_ids == []
    assert identity is None
    request = target_instructions(private, audit)
    assert 'Ada' in request and 'pavilion' in request
    assert 'EVALUATOR_PRIVATE_SECRET' not in request and 'GOLD_ID_SECRET' not in request
    db.close()


def test_ac3_helper_preserves_retrieval_for_durable_request_evidence():
    from app.services.ac3_target_prepare import prepare_ac3_input
    db, audit, test, adapter = setup_target(mode='off')
    private, evidence = prepare_ac3_input(adapter, test, audit, 'H0-Q0')
    assert evidence['retrieval_id'] and evidence['target_memory_context'] == private.target_memory_context
    assert len(evidence['selected_memory_ids']) == len(evidence['target_memory_context'])
    assert 'EVALUATOR_PRIVATE_SECRET' not in str(evidence) and 'GOLD_ID_SECRET' not in str(evidence)
    db.close()


def test_retrieved_private_input_binds_to_actual_request_without_gold(monkeypatch):
    import httpx
    from app.services.ac3_request_binding import AC3RequestBinding
    from app.target_ai.providers import HttpTargetAIConnector, single_attempt_target_request
    from app.target_ai.request_contracts import observe_request_contracts
    from scripts.ac3_fixed_suite_adapter import sha
    db, audit, test, adapter = setup_target(mode='off')
    frozen_sha, frozen_id = 'a' * 64, 'H0-Q0'
    local_id = 'AC3' + sha(f'{frozen_sha}|{audit.run_id}|{frozen_id}'.encode())[:32].upper()
    private, retrieval, _ = adapter.prepare_answer(test.model_copy(update={'test_id': local_id}), audit)
    class Ledger:
        def begin(self, scope, digest, key, contract, test_id):
            assert (scope, digest, key, test_id) == ('S', frozen_sha, 'request-1', frozen_id)
            return {'state':'dispatched', 'duplicate':False}
    binding = AC3RequestBinding(Ledger(), 'S', frozen_sha, 'request-1', private, audit, frozen_test_id=frozen_id)
    sent = []
    def post(url, **kwargs):
        sent.append(kwargs['json']['messages'])
        return httpx.Response(200, json={'model':'openai/gpt-6-luna',
            'choices':[{'finish_reason':'stop','message':{'content':'synthetic answer'}}],
            'usage':{'cost':0.001}})
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-key')
    monkeypatch.setattr('app.target_ai.providers.httpx.post', post)
    with single_attempt_target_request(), observe_request_contracts(binding):
        result = HttpTargetAIConnector().execute(private, audit)
    assert binding.bound and result.response_text == 'synthetic answer'
    assert result.execution_metadata.request_contract_sha256
    assert retrieval.context and 'Ada' in str(sent)
    assert 'EVALUATOR_PRIVATE_SECRET' not in str(sent) and 'GOLD_ID_SECRET' not in str(sent)
    db.close()
