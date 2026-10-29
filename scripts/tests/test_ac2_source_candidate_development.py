"""The source supplement is provisional and never invents relations."""
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from app.schemas import Conversation


def candidate():
    path = Path('output/proposal-delivery/ac2-scope-guard-development-20261029/source_candidate_v1.py')
    spec = importlib.util.spec_from_file_location('source_candidate_v1', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_unsupported_third_party_statements_are_provisional_source_bound():
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    conversation = Conversation(conversation_id='FIX', created_at=now, authorised=True, source_origin='synthetic',
        messages=[{'message_id':'S1','role':'user','content':'The ferry app lists gate 3.','timestamp':now},
                  {'message_id':'S2','role':'user','content':'The printed pass lists gate 5.','timestamp':now}])
    memories = candidate().extract(conversation)
    added = [m for m in memories if m.memory_id.startswith('SRC')]
    assert {m.canonical_value for m in added} == {'The ferry app lists gate 3.','The printed pass lists gate 5.'}
    assert all(m.status.value == 'candidate' and len(m.source_message_ids)==1 and not m.relationships for m in added)


def test_does_not_add_assistant_or_meta_speculation():
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    conversation = Conversation(conversation_id='FIX', created_at=now, authorised=True, source_origin='synthetic',
        messages=[{'message_id':'S1','role':'assistant','content':'The user lives on Mars.','timestamp':now},
                  {'message_id':'S2','role':'user','content':'I might assume an additional detail, but please verify it.','timestamp':now}])
    added = [m for m in candidate().extract(conversation) if m.memory_id.startswith('SRC')]
    assert not added
