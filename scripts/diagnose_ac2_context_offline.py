"""Reconstruct target retrieval for AC2 questions in isolated in-memory SQLite.

This is a prospective engineering diagnostic, not the actual AC2 run (which
did not execute targets), not model answers and not a human judgment. It does
not connect to a live database or call a network provider.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.session import Base
from app.models import ConversationModel, AuditRunModel, TargetAgentMemoryModel
from app.schemas.domain import AuditRun, Conversation, ConversationMessage, TestCase
from app.services.formal_freeze import formal_runtime_signature
from app.target_systems.controlled import ControlledTargetSystemAdapter
from app.target_ai.rule_based import selected_memory_context

SOURCE = Path('/output/proposal-delivery/review-package-intake-2026-10-28/user-confirmed/ac2-adjudication.json')
FROZEN = Path('/output/proposal-delivery/ac3-expanded-primary-frozen-2026-10-28.json')
OUTPUT = Path('/ac3-results/ac2-context-reconstruction-2026-10-28.json')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    source_raw, frozen_raw = SOURCE.read_bytes(), FROZEN.read_bytes()
    source, frozen = json.loads(source_raw), json.loads(frozen_raw)
    model = frozen['protocol']['model_configuration']
    actual_runtime = formal_runtime_signature()['source_sha256']
    if model['runtime_source_sha256'] != actual_runtime:
        raise ValueError('Current runtime differs from the frozen target setup.')
    if source['format'] != 'ac2-structural-disagreement-adjudication-v1':
        raise ValueError('Unexpected adjudication source.')
    if model['audit_setup']['target_memory_writer'] != 'rule_based' or model['audit_setup']['retrieval_mode'] != 'fixed':
        raise ValueError('Only offline fixed rule-based target memory is permitted.')
    def deny_network(*args, **kwargs):
        raise RuntimeError('Network is disabled in this offline diagnostic.')
    httpx.post = deny_network
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    rows = []
    timestamp = datetime(2000, 1, 1, tzinfo=timezone.utc)
    with Session(engine) as db:
        for history in source['histories']:
            cases = [case for case in history['cases'] if case['adjudication']['structurally_executable'] == 'uncertain']
            if not cases:
                continue
            hid = history['history_id']; run_id = 'OFFLINE-' + hid; conversation_id = 'OFFLINE-C-' + hid
            conversation = Conversation(conversation_id=conversation_id, created_at=timestamp, authorised=True,
                messages=[ConversationMessage(message_id=m['message_id'], role=m['role'],
                    content=m['text'], timestamp=timestamp + timedelta(seconds=m['order']-1)) for m in history['source_messages']])
            db.add(ConversationModel(id=conversation_id, authorised=True, source_origin='synthetic'))
            setup = model['audit_setup']
            db.add(AuditRunModel(id=run_id, conversation_id=conversation_id, status='CREATED',
                target_configuration=setup['target_configuration'], provider=setup['provider'], model=setup['model'],
                temperature=setup['temperature'], random_seed=setup['random_seed'], test_budget=4,
                prompt_template_version=setup['prompt_template_version'], memory_strategy=setup['memory_strategy']))
            db.flush()
            audit = AuditRun(run_id=run_id, conversation_id=conversation_id, status='CREATED', created_at=timestamp, **setup)
            adapter = ControlledTargetSystemAdapter(db, audit)
            adapter.ingest(conversation)
            reference = {fact['memory_id']: fact for fact in history['reviewed_reference']['facts']}
            for case in cases:
                test = TestCase(test_id=hid+'-'+case['test_id'], run_id=run_id, dimension=case['dimension'],
                    prompt=case['question'], expected_behavior='', supporting_memory_ids=[], generator_version='offline-retrieval-diagnostic')
                private, retrieval, _ = adapter.prepare_answer(test, audit)
                sent_values = set(selected_memory_context(private, audit.target_configuration))
                sent_ids = [mid for mid, value in zip(retrieval.evidence.selected_memory_ids, retrieval.context, strict=True)
                            if value.strip() in sent_values]
                selected_source_ids = set()
                for mid in sent_ids:
                    record = db.get(TargetAgentMemoryModel, mid)
                    if record is None:
                        raise ValueError('Selected target memory is missing.')
                    selected_source_ids.update(record.source_message_ids)
                wanted = {reference[mid]['source_message_id'] for mid in case['supporting_memory_ids']}
                rows.append({'history_id':hid, 'test_id':case['test_id'], 'dimension':case['dimension'],
                    'required_source_ids':sorted(wanted), 'selected_source_ids':sorted(selected_source_ids),
                    'source_id_coverage':'all' if wanted <= selected_source_ids else ('partial' if wanted & selected_source_ids else 'none'),
                    'sent_context_count':len(sent_ids)})
    counts = Counter(row['source_id_coverage'] for row in rows)
    result = {'format':'ac2-offline-target-context-diagnostic-v1', 'scope':'99 human-adjudicated uncertain cases; no target answering',
        'input_sha256':sha(source_raw), 'frozen_sha256':sha(frozen_raw), 'runtime_sha256':actual_runtime,
        'cases':len(rows), 'source_id_coverage_counts':dict(counts), 'cases_detail':rows,
        'model_called':False, 'live_database_written':False,
        'limitations':['Reconstructed in isolated SQLite from synthetic source using frozen target settings, not the actual AC2 generation run.',
            'Matching source IDs shows retrieved record provenance, not full semantic coverage or a correct model answer.',
            'Coverage does not by itself make a question structurally valid or invalid.',
            'Only one deterministic memory setting is simulated; external deployment and provider outputs are untested.']}
    if len(rows)!=99:
        raise ValueError('Expected exactly 99 unresolved cases.')
    if (SOURCE.read_bytes()!=source_raw or FROZEN.read_bytes()!=frozen_raw or
        formal_runtime_signature()['source_sha256']!=actual_runtime):
        raise ValueError('Source, frozen setup, or runtime changed during reconstruction.')
    fd=os.open(OUTPUT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'output':str(OUTPUT),'cases':len(rows),'source_id_coverage_counts':dict(counts),'model_called':False}))


if __name__ == '__main__':
    main()
