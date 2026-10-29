"""Opt-in source-scope checks keep unresolved questions visible and blocked."""
from sqlalchemy import delete, select

from app.models import AuditRunModel, MemoryModel, MessageModel, TestCaseModel
from app.test_generator.scope_review import VERSION, scope_warning


def test_scope_advice_fails_closed_without_original_sources():
    assert scope_warning('Which language is used?', 'accuracy', [], source_complete=False)
    assert scope_warning('Which language is used?', 'accuracy', ['  '], source_complete=True)
    assert scope_warning('Which language is used?', 'freshness', ['A prior and current fact.'], source_complete=True)
    assert scope_warning("What is the user's recorded stored information for the user?", 'accuracy',
                         ['I live in Sydney.', 'I work at a school.'], source_complete=True)
    # A lack of a warning is not an acceptance or a validity judgement.
    assert scope_warning('Which language does Cedar use?', 'accuracy', ['Cedar uses Python.'], source_complete=True) is None
    assert scope_warning('What is the current deployment configuration?', 'accuracy',
                         ['Cedar requires North.', 'Cedar requires South.'], source_complete=True,
                         related_topic_count=2)
    assert scope_warning('For the current task, what is the recorded requirement about event venue?', 'accuracy',
                         ['The venue closure requires a text alert.'], source_complete=True)
    assert scope_warning("What is the user's recorded preference? State the relevant fact only.", 'accuracy',
                         ['I prefer paper maps.'], source_complete=True)
    assert scope_warning("What is the user's recorded communication style? State the relevant fact only.", 'accuracy',
                         ['I review notes in email.'], source_complete=True)


def test_multiple_same_topic_facts_flag_direct_accuracy_and_preserve_question(saved_suite):
    client, sessions, runs, _ = saved_suite
    with sessions() as db:
        audit = db.get(AuditRunModel, runs[0])
        memories = db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == audit.conversation_id)).all()
        old = next(m for m in memories if 'MySQL' in m.canonical_value)
        new = next(m for m in memories if 'PostgreSQL' in m.canonical_value)
        assert old.id != new.id
        question = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[0], TestCaseModel.dimension == 'accuracy'))
        question.prompt = 'What is the current backend database?'
        question.supporting_memory_ids = [new.id]
        question.quality_status = 'accepted'
        question.validation_notes = 'Generated.'
        question_id = question.id
        db.commit()
    response = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert response.status_code == 200, response.text
    result = next(q for q in response.json()['tests'] if q['test_id'] == question_id)
    assert result['quality_status'] == 'pending'
    assert 'Several confirmed memories share this topic' in result['validation_notes']
    assert result['prompt'] == 'What is the current backend database?'
    assert client.post(f'/api/v1/audits/{runs[0]}/execute').status_code == 409


def test_project_name_in_unrelated_message_does_not_ground_question(saved_suite, monkeypatch):
    from app.api import routes
    monkeypatch.setattr(routes.RuleBasedTestGenerator, '_topic', staticmethod(lambda memory: memory.id))
    client, sessions, runs, _ = saved_suite
    with sessions() as db:
        audit = db.get(AuditRunModel, runs[0])
        message = db.scalar(select(MessageModel).where(MessageModel.conversation_id == audit.conversation_id))
        message.content = 'The backend uses PostgreSQL.'
        db.add(MessageModel(id='unrelated-message', conversation_id=audit.conversation_id,
                            source_message_id='unrelated-source', sequence=99, role='user',
                            content='The Cedar project uses Python.', timestamp=message.timestamp,
                            original_timestamp=message.original_timestamp))
        memories = db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == audit.conversation_id)).all()
        for index, memory in enumerate(memories):
            memory.canonical_value = f'unique subject {index} value'
        supporting = memories[0]
        supporting.source_message_ids = [message.source_message_id]
        question = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[0], TestCaseModel.dimension == 'accuracy'))
        question.prompt = 'What is the database for the Cedar project?'
        question.supporting_memory_ids = [supporting.id]
        question.quality_status = 'accepted'
        question.validation_notes = 'Generated.'
        question_id = question.id
        db.commit()
    response = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert response.status_code == 200, response.text
    question = next(q for q in response.json()['tests'] if q['test_id'] == question_id)
    assert question['quality_status'] == 'pending'
    assert 'named project is not explicit' in question['validation_notes']


def test_project_name_in_any_cited_source_is_considered(saved_suite, monkeypatch):
    from app.api import routes
    monkeypatch.setattr(routes.RuleBasedTestGenerator, '_topic', staticmethod(lambda memory: memory.id))
    client, sessions, runs, _ = saved_suite
    with sessions() as db:
        audit = db.get(AuditRunModel, runs[0])
        message = db.scalar(select(MessageModel).where(MessageModel.conversation_id == audit.conversation_id))
        message.content = 'The backend uses PostgreSQL.'
        db.add(MessageModel(id='cited-message', conversation_id=audit.conversation_id,
                            source_message_id='cited-source', sequence=99, role='user',
                            content='The Cedar project uses PostgreSQL.', timestamp=message.timestamp,
                            original_timestamp=message.original_timestamp))
        supporting = db.scalar(select(MemoryModel).where(MemoryModel.conversation_id == audit.conversation_id))
        supporting.source_message_ids = [message.source_message_id, 'cited-source']
        question = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[0], TestCaseModel.dimension == 'accuracy'))
        question.prompt = 'What is the database for the Cedar project?'
        question.supporting_memory_ids = [supporting.id]
        question.quality_status = 'accepted'
        question.validation_notes = 'Generated.'
        question_id = question.id
        db.commit()
    response = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert response.status_code == 200, response.text
    question = next(q for q in response.json()['tests'] if q['test_id'] == question_id)
    assert question['quality_status'] == 'accepted'


def test_v1_missing_source_warning_remains_protected_after_v2_upgrade(saved_suite):
    client, sessions, runs, _ = saved_suite
    with sessions() as db:
        row = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[0]))
        question_id = row.id
        row.quality_status = 'pending'
        row.validation_notes = 'source-scope-review-v1: Original source messages are missing; check this question against its source before use.'
        audit = db.get(AuditRunModel, runs[0])
        db.execute(delete(MessageModel).where(MessageModel.conversation_id == audit.conversation_id))
        db.commit()
    response = client.patch(f'/api/v1/audits/{runs[0]}/tests/{question_id}/review', json={'quality_status': 'accepted'})
    assert response.status_code == 422


def test_v2_missing_source_warning_remains_protected_after_v3_upgrade(saved_suite):
    client, sessions, runs, _ = saved_suite
    with sessions() as db:
        row = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[0]))
        question_id = row.id
        row.quality_status = 'pending'
        row.validation_notes = 'source-scope-review-v2: Original source messages are missing; check this question against its source before use.'
        audit = db.get(AuditRunModel, runs[0])
        db.execute(delete(MessageModel).where(MessageModel.conversation_id == audit.conversation_id))
        db.commit()
    response = client.patch(f'/api/v1/audits/{runs[0]}/tests/{question_id}/review', json={'quality_status': 'accepted'})
    assert response.status_code == 422


def test_broad_requirement_is_kept_pending_and_syncs_to_shared_suite(saved_suite):
    client, sessions, runs, _ = saved_suite
    with sessions() as db:
        row = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[0], TestCaseModel.dimension == 'accuracy'))
        row.prompt = 'For the current task, what is the recorded requirement about event venue? State the relevant requirement only.'
        row.quality_status = 'accepted'
        row.validation_notes = 'Generated.'
        question_id = row.id
        db.commit()
    response = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert response.status_code == 200, response.text
    question = next(q for q in response.json()['tests'] if q['test_id'] == question_id)
    assert question['quality_status'] == 'pending'
    assert VERSION + ':' in question['validation_notes']
    assert client.post(f'/api/v1/audits/{runs[1]}/execute').status_code == 409


def test_opt_in_scope_review_keeps_questions_and_blocks_execution(saved_suite):
    client, sessions, runs, _ = saved_suite
    before = client.get(f'/api/v1/audits/{runs[0]}/test-review').json()['tests']
    assert all(t['quality_status'] == 'accepted' for t in before)
    response = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert response.status_code == 200, response.text
    after = response.json()['tests']
    assert {t['test_id'] for t in after} == {t['test_id'] for t in before}
    pending = [t for t in after if t['quality_status'] == 'pending']
    assert pending and all(VERSION in t['validation_notes'] for t in pending)
    with sessions() as db:
        peer = list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == runs[1])).all())
        assert sum(t.quality_status == 'pending' for t in peer) == len(pending)
    assert client.post(f'/api/v1/audits/{runs[1]}/execute').status_code == 409
    for test in pending:
        reviewed = client.patch(f"/api/v1/audits/{runs[0]}/tests/{test['test_id']}/review",
                                json={'quality_status': 'accepted', 'note': 'Reviewed the source.'})
        assert reviewed.status_code == 200, reviewed.text
    assert client.post(f'/api/v1/audits/{runs[1]}/execute').status_code == 200
    assert client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review').status_code == 409


def test_scope_review_does_not_overwrite_prior_manual_decision(saved_suite):
    client, _, runs, _ = saved_suite
    suite = client.get(f'/api/v1/audits/{runs[0]}/test-review').json()['tests']
    chosen = next(t for t in suite if t['dimension'] == 'freshness')
    result = client.patch(f"/api/v1/audits/{runs[0]}/tests/{chosen['test_id']}/review",
                          json={'quality_status': 'accepted', 'note': 'Prior human check.'})
    assert result.status_code == 200
    result = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert result.status_code == 200
    chosen = next(t for t in result.json()['tests'] if t['test_id'] == chosen['test_id'])
    assert chosen['quality_status'] == 'accepted'
    assert 'Prior human check' in chosen['validation_notes']


def test_missing_original_messages_are_not_treated_as_complete_evidence(saved_suite):
    client, sessions, runs, _ = saved_suite
    with sessions() as db:
        audit = db.get(AuditRunModel, runs[0])
        original = db.scalar(select(MessageModel).where(MessageModel.conversation_id == audit.conversation_id))
        restored = {key: getattr(original, key) for key in
                    ('id', 'conversation_id', 'source_message_id', 'sequence', 'role', 'content', 'timestamp', 'original_timestamp')}
        db.execute(delete(MessageModel).where(MessageModel.conversation_id == audit.conversation_id))
        db.commit()
    response = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert response.status_code == 200, response.text
    tests = response.json()['tests']
    assert tests and all(t['quality_status'] == 'pending' for t in tests)
    assert all('source messages are missing' in t['validation_notes'] for t in tests)
    blocked = client.patch(f"/api/v1/audits/{runs[0]}/tests/{tests[0]['test_id']}/review",
                           json={'quality_status': 'accepted', 'note': 'Tried to accept.'})
    assert blocked.status_code == 422
    assert 'Original source messages are unavailable' in blocked.json()['detail']
    rejected = client.patch(f"/api/v1/audits/{runs[0]}/tests/{tests[0]['test_id']}/review",
                            json={'quality_status': 'rejected', 'note': 'Missing source.'})
    assert rejected.status_code == 200
    assert client.patch(f"/api/v1/audits/{runs[0]}/tests/{tests[0]['test_id']}/review",
                        json={'quality_status': 'accepted'}).status_code == 422
    with sessions() as db:
        db.add(MessageModel(**restored)); db.commit()
    accepted = client.patch(f"/api/v1/audits/{runs[0]}/tests/{tests[0]['test_id']}/review",
                            json={'quality_status': 'accepted', 'note': 'Restored source checked.'})
    assert accepted.status_code == 200
