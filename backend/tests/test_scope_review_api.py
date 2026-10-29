"""Opt-in source-scope checks keep unresolved questions visible and blocked."""
from sqlalchemy import delete, select
import pytest

from app.models import AuditRunModel, MemoryModel, MessageModel, TestCaseModel
from app.test_generator.scope_review import VERSION, later_explicit_time_update_advice, scope_warning


def test_second_person_past_statement_requires_subject_review():
    source = ['I have a little time to work on this today.']
    assert 'user or the answering assistant' in scope_warning(
        'How much time did you say you have available to work on this today?',
        'accuracy', source, source_complete=True)
    assert 'user or the answering assistant' in scope_warning(
        'What did you mention earlier?', 'accuracy', source, source_complete=True)
    assert scope_warning('How much time did the user say they had?', 'accuracy', source, source_complete=True) is None


def test_work_arrangement_question_flags_unrelated_office_source():
    question = "What is the user's recorded working arrangement? State the relevant fact only."
    source = ['The transport office replaced the final stop with the hill stop.']
    assert 'does not explicitly describe' in scope_warning(question, 'accuracy', source, source_complete=True)
    assert scope_warning(question, 'accuracy', ['I work remotely.'], source_complete=True) is None
    assert scope_warning(question, 'accuracy', ['The team uses hybrid work.'], source_complete=True) is None
    # A missing warning is not a validity judgment, and relationship questions still require review.
    assert scope_warning(question, 'freshness', ['I work remotely.'], source_complete=True)


def test_scope_v6_snapshot_is_preserved():
    import hashlib
    from pathlib import Path
    from app.test_generator import frozen_scope_review_v6
    assert frozen_scope_review_v6.VERSION == 'source-scope-review-v6'
    assert hashlib.sha256(Path(frozen_scope_review_v6.__file__).read_bytes()).hexdigest() == '9ba60b4d9330cca73fa888ea56c4a309921957cb1f43d1a90f6c3b06d56570de'


def test_scope_v7_snapshot_is_preserved():
    import hashlib
    from pathlib import Path
    from app.test_generator import frozen_scope_review_v7
    assert frozen_scope_review_v7.VERSION == 'source-scope-review-v7'
    assert hashlib.sha256(Path(frozen_scope_review_v7.__file__).read_bytes()).hexdigest() == '37b43c1b36bf602b952939118a9b18b1c883494c38055b63e6a20b48f5d15292'


def test_scope_v8_snapshot_is_preserved():
    import hashlib
    from pathlib import Path
    from app.test_generator import frozen_scope_review_v8
    assert frozen_scope_review_v8.VERSION == 'source-scope-review-v8'
    assert hashlib.sha256(Path(frozen_scope_review_v8.__file__).read_bytes()).hexdigest() == 'a5d946e991dbd8c64ad4834af49e12b0da922d0d83b36ad95a96aae5081f86e6'


def test_later_time_replacement_warns_but_does_not_assert_event_identity():
    messages = [{'source_id':'old','sequence':1,'text':'My dog eats breakfast at 7 a.m.'},
                {'source_id':'new','sequence':2,'text':'Breakfast moved to 8 a.m., replacing the 7 a.m. time.'}]
    assert 'same event' in later_explicit_time_update_advice({'old'}, messages)
    assert later_explicit_time_update_advice({'new'}, messages) is None
    assert later_explicit_time_update_advice({'old'}, [messages[0],{**messages[1],'sequence':1}]) is None
    assert later_explicit_time_update_advice({'missing'}, messages) is None
    unrelated = [messages[0],{**messages[1],'text':'A meeting moved to 8 a.m., replacing 7 a.m.'}]
    assert 'same event' in later_explicit_time_update_advice({'old'}, unrelated)
    rescheduled = [messages[0],{**messages[1],'text':'Dog breakfast was rescheduled from 7 a.m. to 8 a.m.'}]
    assert 'same event' in later_explicit_time_update_advice({'old'}, rescheduled)
    unrelated_no_replacement = [messages[0],{**messages[1],'text':'The meeting ends at 8 a.m.'}]
    assert later_explicit_time_update_advice({'old'}, unrelated_no_replacement) is None


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


def test_second_person_warning_marks_saved_question_pending(saved_suite):
    client, sessions, runs, _ = saved_suite
    with sessions() as db:
        question = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[0], TestCaseModel.dimension == 'accuracy'))
        question.prompt = 'How much time did you say you have available?'
        question.quality_status = 'accepted'
        question.validation_notes = 'Generated.'
        question_id = question.id
        db.commit()
    response = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert response.status_code == 200, response.text
    reviewed = next(q for q in response.json()['tests'] if q['test_id'] == question_id)
    assert reviewed['quality_status'] == 'pending'
    assert 'user or the answering assistant' in reviewed['validation_notes']
    assert reviewed['prompt'] == 'How much time did you say you have available?'
    assert client.post(f'/api/v1/audits/{runs[0]}/execute').status_code == 409


def test_work_arrangement_warning_marks_unrelated_source_pending(saved_suite):
    client, sessions, runs, _ = saved_suite
    with sessions() as db:
        audit = db.get(AuditRunModel, runs[0])
        question = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[0], TestCaseModel.dimension == 'accuracy'))
        for message in db.scalars(select(MessageModel).where(MessageModel.conversation_id == audit.conversation_id)):
            message.content = 'The transport office replaced the final stop with the hill stop.'
        question.prompt = "What is the user's recorded working arrangement? State the relevant fact only."
        question.quality_status = 'accepted'
        question.validation_notes = 'Generated.'
        question_id = question.id
        db.commit()
    response = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert response.status_code == 200, response.text
    reviewed = next(q for q in response.json()['tests'] if q['test_id'] == question_id)
    assert reviewed['quality_status'] == 'pending'
    assert 'does not explicitly describe' in reviewed['validation_notes']
    assert client.post(f'/api/v1/audits/{runs[0]}/execute').status_code == 409


@pytest.mark.parametrize('later_text', [
    'We moved her breakfast to 8 a.m. permanently, replacing the 7 a.m. time.',
    'Dog breakfast was rescheduled from 7 a.m. to 8 a.m.',
])
def test_later_explicit_time_replacement_marks_question_pending(saved_suite, monkeypatch, later_text):
    from app.api import routes
    monkeypatch.setattr(routes.ConflictAwareRuleBasedTestGenerator, '_topic', staticmethod(lambda memory: memory.id))
    client, sessions, runs, _ = saved_suite
    with sessions() as db:
        audit = db.get(AuditRunModel, runs[0])
        messages = db.scalars(select(MessageModel).where(MessageModel.conversation_id == audit.conversation_id).order_by(MessageModel.id)).all()
        for i, message in enumerate(messages):
            message.sequence = i
        source = messages[0]
        source.role = 'user'; source.content = 'My dog eats breakfast at 7 a.m.'
        db.add(MessageModel(id='later-time-message', conversation_id=audit.conversation_id,
                            source_message_id='later-time-source', sequence=len(messages), role='user',
                            content=later_text,
                            timestamp=source.timestamp, original_timestamp=source.original_timestamp))
        memory = db.scalar(select(MemoryModel).where(MemoryModel.conversation_id == audit.conversation_id))
        memory.source_message_ids = [source.source_message_id]
        question = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[0], TestCaseModel.dimension == 'accuracy'))
        question.prompt = "What time does the user's dog eat breakfast?"
        question.supporting_memory_ids = [memory.id]
        question.quality_status = 'accepted'; question.validation_notes = 'Generated.'
        question_id = question.id
        db.commit()
    response = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert response.status_code == 200, response.text
    question = next(q for q in response.json()['tests'] if q['test_id'] == question_id)
    assert question['quality_status'] == 'pending'
    assert 'same event' in question['validation_notes']
    assert client.post(f'/api/v1/audits/{runs[0]}/execute').status_code == 409
    accepted = client.patch(f'/api/v1/audits/{runs[0]}/tests/{question_id}/review',
                            json={'quality_status':'accepted','note':'Checked both source statements.'})
    assert accepted.status_code == 200, accepted.text
    again = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert again.status_code == 200, again.text
    preserved = next(q for q in again.json()['tests'] if q['test_id'] == question_id)
    assert preserved['quality_status'] == 'accepted'
    assert 'Checked both source statements.' in preserved['validation_notes']


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
    monkeypatch.setattr(routes.ConflictAwareRuleBasedTestGenerator, '_topic', staticmethod(lambda memory: memory.id))
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
    monkeypatch.setattr(routes.ConflictAwareRuleBasedTestGenerator, '_topic', staticmethod(lambda memory: memory.id))
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


def test_v5_aligns_work_topics_with_current_generator_on_same_c11_suite(saved_suite, monkeypatch):
    from app.api import routes
    from app.test_generator.rule_based import RuleBasedTestGenerator

    client, sessions, runs, _ = saved_suite
    with sessions() as db:
        audit = db.get(AuditRunModel, runs[0])
        memories = list(db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == audit.conversation_id)).all())
        assert len(memories) >= 3
        for index, memory in enumerate(memories):
            memory.canonical_value = f'Unrelated miscellaneous fact {index}.'
        regular, workshop = memories[:2]
        regular.canonical_value = 'My regular work location is the office.'
        workshop.canonical_value = 'For the quarterly workshop only, I will work at the office.'
        message = db.scalar(select(MessageModel).where(MessageModel.conversation_id == audit.conversation_id))
        message.content = regular.canonical_value + ' ' + workshop.canonical_value
        regular.source_message_ids = workshop.source_message_ids = [message.source_message_id]
        question = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[0], TestCaseModel.dimension == 'accuracy'))
        question.prompt = "What is the user's recorded working arrangement? State the relevant fact only."
        question.supporting_memory_ids = [workshop.id]
        question.quality_status = 'accepted'
        question.validation_notes = 'Generated.'
        question_id = question.id
        db.commit()

    # Reconstruct the old route's topic function against the exact same saved
    # suite in a disposable database; no historical run is modified.
    with monkeypatch.context() as v4:
        v4.setattr(routes.ConflictAwareRuleBasedTestGenerator, '_topic', staticmethod(RuleBasedTestGenerator._topic))
        v4.setattr(routes, 'SCOPE_REVIEW_VERSION', 'source-scope-review-v4')
        old = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert old.status_code == 200, old.text
    before = next(q for q in old.json()['tests'] if q['test_id'] == question_id)
    assert before['quality_status'] == 'accepted'

    with sessions() as db:
        test = db.get(TestCaseModel, question_id)
        test.quality_status = 'accepted'
        test.validation_notes = 'Generated.'
        db.commit()
    new = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert new.status_code == 200, new.text
    after = next(q for q in new.json()['tests'] if q['test_id'] == question_id)
    assert after['quality_status'] == 'pending'
    assert 'Several confirmed memories share this topic' in after['validation_notes']
    for field in ('prompt', 'expected_behavior', 'supporting_memory_ids', 'dimension'):
        assert after[field] == before[field]


def test_frozen_v4_files_match_prior_development_protocol():
    import hashlib
    from pathlib import Path
    from app.test_generator import frozen_scope_review_v4
    assert frozen_scope_review_v4.VERSION == 'source-scope-review-v4'
    assert hashlib.sha256(Path(frozen_scope_review_v4.__file__).read_bytes()).hexdigest() == '3528b1864295ac269c919369d5952fb97933668e7139ce2769d311707243f790'


def test_broad_subject_and_task_warning_has_bounded_scope():
    class_prompt = 'What is recorded about The class? State the relevant fact only.'
    single = ['The class uses a shared whiteboard.']
    multiple = ['The class uses a shared whiteboard. The class has twelve students.']
    warning = scope_warning(class_prompt, 'accuracy', single, source_complete=True, conversation_source_texts=multiple)
    assert warning and 'Several source statements' in warning
    assert scope_warning(class_prompt, 'accuracy', single, source_complete=True, conversation_source_texts=single) is None
    assert scope_warning('How many students are in the class?', 'accuracy', multiple, source_complete=True, conversation_source_texts=multiple) is None

    task_prompt = "What is the user's recorded current task? State the relevant fact only."
    requirement = ['For the architecture assignment only, use the 35 mm lens.']
    assert 'requirement' in scope_warning(task_prompt, 'accuracy', requirement, source_complete=True)
    explicit = ['My current task is preparing a poster. It requires Java.']
    assert scope_warning(task_prompt, 'accuracy', explicit, source_complete=True) is None
    assert scope_warning('Which lens is required for the architecture assignment?', 'accuracy', requirement, source_complete=True) is None


@pytest.mark.parametrize(('prompt', 'source', 'warning_text'), [
    ('What is recorded about The class? State the relevant fact only.',
     'The class uses a shared whiteboard. The class has twelve students.', 'Several source statements'),
    ("What is the user's recorded current task? State the relevant fact only.",
     'For the architecture assignment only, use the 35 mm lens.', 'describes a requirement'),
])
def test_v6_flags_broad_subject_and_task_on_real_api(saved_suite, monkeypatch, prompt, source, warning_text):
    from app.api import routes
    from app.test_generator import frozen_scope_review_v5

    client, sessions, runs, _ = saved_suite
    # This isolates the new source-based checks from the separate topic-count
    # heuristic, so the comparison actually exercises the new rule.
    monkeypatch.setattr(routes.ConflictAwareRuleBasedTestGenerator, '_topic', staticmethod(lambda memory: memory.id))
    with sessions() as db:
        audit = db.get(AuditRunModel, runs[0])
        message = db.scalar(select(MessageModel).where(MessageModel.conversation_id == audit.conversation_id))
        message.content = source
        memory = db.scalar(select(MemoryModel).where(MemoryModel.conversation_id == audit.conversation_id))
        memory.source_message_ids = [message.source_message_id]
        question = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[0], TestCaseModel.dimension == 'accuracy'))
        question.prompt = prompt
        question.supporting_memory_ids = [memory.id]
        question.quality_status = 'accepted'
        question.validation_notes = 'Generated.'
        question_id = question.id
        db.commit()

    def v5_warning(prompt, dimension, source_texts, *, source_complete, related_topic_count, conversation_source_texts):
        return frozen_scope_review_v5.scope_warning(prompt, dimension, source_texts,
            source_complete=source_complete, related_topic_count=related_topic_count)

    # Old and new implementations inspect the same saved question in a
    # disposable fixture; no frozen study record is edited.
    with monkeypatch.context() as old:
        old.setattr(routes, 'scope_warning', v5_warning)
        old.setattr(routes, 'SCOPE_REVIEW_VERSION', 'source-scope-review-v5')
        response = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert response.status_code == 200, response.text
    before = next(q for q in response.json()['tests'] if q['test_id'] == question_id)
    assert before['quality_status'] == 'accepted'
    with sessions() as db:
        question = db.get(TestCaseModel, question_id)
        question.quality_status = 'accepted'
        question.validation_notes = 'Generated.'
        db.commit()
    response = client.post(f'/api/v1/audits/{runs[0]}/tests/scope-review')
    assert response.status_code == 200, response.text
    after = next(q for q in response.json()['tests'] if q['test_id'] == question_id)
    assert after['quality_status'] == 'pending'
    assert warning_text in after['validation_notes']
    for field in ('prompt', 'expected_behavior', 'supporting_memory_ids', 'dimension'):
        assert after[field] == before[field]


def test_frozen_v5_scope_matches_original_diagnostic():
    import hashlib
    from pathlib import Path
    from app.test_generator import frozen_scope_review_v5
    assert frozen_scope_review_v5.VERSION == 'source-scope-review-v5'
    assert hashlib.sha256(Path(frozen_scope_review_v5.__file__).read_bytes()).hexdigest() == '726a2bea660ccf13004cf931495b9a1d69bee1015e340addb237bb66fd5132e9'


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
