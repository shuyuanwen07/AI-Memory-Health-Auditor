from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from mem0_target.metering import instrument


class Client:
    def chat(self, **kwargs):
        return {'message': {'content': 'private reply'}, 'prompt_eval_count': 10, 'eval_count': 3}

    def embed(self, **kwargs):
        if kwargs.get('fail'):
            raise RuntimeError('private error')
        return {'embeddings': [[1, 2]], 'prompt_eval_count': 2}


def test_meter_observes_real_boundary_preserves_reply_and_excludes_private_content():
    memory = SimpleNamespace(llm=SimpleNamespace(client=Client()), embedding_model=SimpleNamespace(client=Client()))
    meter = instrument(memory)
    start = meter.checkpoint()
    reply = memory.llm.client.chat(messages=['private prompt'])
    assert reply['message']['content'] == 'private reply'
    with ThreadPoolExecutor(max_workers=3) as workers:
        list(workers.map(lambda _: memory.embedding_model.client.embed(input='private fact'), range(5)))
    with pytest.raises(RuntimeError):
        memory.embedding_model.client.embed(fail=True)
    receipt = meter.receipt(start)
    assert receipt['llm_attempts'] == 1 and receipt['embedding_attempts'] == 6
    assert receipt['embedding_failures'] == 1
    assert 'private' not in str(receipt)
    assert receipt['events'][0]['prompt_eval_count'] == 10
    assert receipt['monetary_cost'] is None
    assert instrument(memory) is meter
    assert meter.receipt(meter.checkpoint())['embedding_attempts'] == 0


def test_unknown_instrumentation_is_not_reported_as_zero_calls():
    receipt = instrument(SimpleNamespace()).receipt(0)
    assert receipt['llm_attempts'] is None and receipt['embedding_attempts'] is None
