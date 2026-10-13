"""Model-written observation dates cannot change chronology without source support."""
from datetime import datetime, timedelta, timezone

import pytest

from app.extraction.llm import PipelineRequestError
from app.extraction.llm_extractor import LLMMemoryExtractor
from app.memory_agent.writers import LLMTargetMemoryWriter
from app.schemas import Conversation, ConversationMessage


class Client:
    def __init__(self, timestamp):
        self.timestamp = timestamp
        self.request = None

    def complete_json(self, **kwargs):
        self.request = kwargs
        assert 'source observation' in kwargs['instructions']
        memory = {'memory_id':'M001',
            'canonical_value':'The launch is scheduled for 2030-01-01.',
            'timestamp':self.timestamp, 'confidence':0.9}
        if kwargs['schema_name'] == 'target_agent_memory_write':
            memory['source_message_ids'] = ['MSG001']
            memory['relationships'] = []
        else:
            memory['source_message_refs'] = [1]
        return {'memories': [memory]}


def history():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Conversation(conversation_id='C-TIME', created_at=now, authorised=True, messages=[
        ConversationMessage(message_id='MSG001', role='user', content='Launch is 2030-01-01.', timestamp=now),
        ConversationMessage(message_id='MSG002', role='user', content='Unrelated later fact.',
                            timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc)),
    ])


def configured(extractor, timestamp):
    client = Client(timestamp)
    return (extractor(client=client) if extractor is LLMMemoryExtractor
            else extractor('openrouter', client=client))


@pytest.mark.parametrize('extractor', [LLMMemoryExtractor, LLMTargetMemoryWriter])
@pytest.mark.parametrize('timestamp', [None, '2026-01-01T00:00:00Z', '2026-01-01T11:00:00+11:00'])
def test_source_observation_time_accepts_unknown_and_equivalent_offsets(extractor, timestamp):
    result = configured(extractor, timestamp).extract(history())
    assert result[0].canonical_value == 'The launch is scheduled for 2030-01-01.'
    if timestamp is None:
        assert result[0].timestamp is None
    else:
        assert result[0].timestamp == history().messages[0].timestamp


@pytest.mark.parametrize('timestamp', [
    '2030-01-01T00:00:00Z',  # A date in the fact is not its observation time.
    '2026-01-02T00:00:00Z',  # A real but uncited message does not support it.
    '2026-01-01T00:00:00',   # A guessed timezone must not use the server zone.
])
def test_extractor_discards_untraceable_optional_time(timestamp):
    result = configured(LLMMemoryExtractor, timestamp).extract(history())
    assert result[0].canonical_value == 'The launch is scheduled for 2030-01-01.'
    assert result[0].timestamp is None


@pytest.mark.parametrize('timestamp', [
    '2030-01-01T00:00:00Z',
    '2026-01-02T00:00:00Z',
    '2026-01-01T00:00:00',
])
def test_target_writer_still_rejects_untraceable_time(timestamp):
    with pytest.raises(PipelineRequestError, match='does not match a cited source message'):
        configured(LLMTargetMemoryWriter, timestamp).extract(history())


def test_historical_extractor_drops_guessed_timezone_for_untimed_source():
    conversation = history()
    conversation.messages[0].timestamp = datetime(2026, 1, 1)
    records = configured(LLMMemoryExtractor, '2026-01-01T00:00:00').extract(conversation)
    assert records[0].timestamp == conversation.messages[0].timestamp
    assert records[0].timestamp.tzinfo is None

    records = configured(LLMMemoryExtractor, '2026-01-01T00:00:00Z').extract(conversation)
    assert records[0].timestamp is None


def test_local_extraction_output_budget_scales_with_source_message_count():
    base = history()
    now = datetime(2026, 1, 3, tzinfo=timezone.utc)
    messages = [*base.messages, *[
        ConversationMessage(message_id=f'MSG{index:03d}', role='user', content=f'Fact {index}.',
                            timestamp=now + timedelta(minutes=index))
        for index in range(3, 35)
    ]]
    conversation = Conversation(conversation_id='C-LARGE', created_at=base.created_at,
                                authorised=True, messages=messages)
    client = Client(None)

    LLMMemoryExtractor(client=client).extract(conversation)

    assert client.request['max_output_tokens'] == 3264


def test_target_writer_historical_source_without_timezone_cannot_get_guessed_zone():
    conversation = history()
    conversation.messages[0].timestamp = datetime(2026, 1, 1)
    records = configured(LLMTargetMemoryWriter, '2026-01-01T00:00:00').extract(conversation)
    assert records[0].timestamp == conversation.messages[0].timestamp
    assert records[0].timestamp.tzinfo is None
    with pytest.raises(PipelineRequestError, match='does not match a cited source message'):
        configured(LLMTargetMemoryWriter, '2026-01-01T00:00:00Z').extract(conversation)
