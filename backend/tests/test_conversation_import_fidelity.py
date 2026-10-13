from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base, get_db
from app.main import app


def test_offset_import_roundtrip_and_extraction_keep_actual_chronology(tmp_path,monkeypatch):
    from app.models import MessageModel
    from sqlalchemy import select
    monkeypatch.setenv('PIPELINE_PROVIDER','rule_based')
    engine = create_engine(f"sqlite:///{tmp_path / 'offsets.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    def test_db():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = test_db
    payload = {'authorised':True,'source_origin':'deidentified','messages':[
        {'message_id':'old','role':'user','content':'The Lyra project previously used MySQL.','timestamp':'2026-01-01T14:00:00+11:00'},
        {'message_id':'new','role':'user','content':'The Lyra project now uses PostgreSQL.','timestamp':'2026-01-01T05:00:00Z'},
    ]}
    try:
        with TestClient(app) as client:
            created = client.post('/api/v1/conversations',json=payload)
            assert created.status_code == 201,created.text
            conversation = created.json()
            assert conversation['source_origin'] == 'deidentified'
            stamps = [datetime.fromisoformat(message['timestamp']) for message in conversation['messages']]
            assert stamps[0] == datetime(2026,1,1,3,tzinfo=timezone.utc)
            assert stamps[1] == datetime(2026,1,1,5,tzinfo=timezone.utc)
            assert conversation['messages'][0]['original_timestamp'] == '2026-01-01T14:00:00+11:00'
            memories = client.post(f"/api/v1/conversations/{conversation['conversation_id']}/extract").json()
            old = next(memory for memory in memories if 'MySQL' in memory['canonical_value'])
            new = next(memory for memory in memories if 'PostgreSQL' in memory['canonical_value'])
            assert any(edge['type']=='UPDATE' and edge['target_memory_id']==old['memory_id'] for edge in new['relationships'])
            export_data = client.get(f"/api/v1/conversations/{conversation['conversation_id']}/export").json()
            exported = export_data['conversation']
            assert export_data['source_origin_notice'].startswith('De-identified source origin')
            again = client.post('/api/v1/conversations',json={'authorised':True,'source_origin':exported['source_origin'],'messages':exported['messages']})
            assert again.status_code == 201,again.text
            assert again.json()['messages'] == conversation['messages']
            assert again.json()['source_origin'] == 'deidentified'
            with sessions() as db:
                rows = db.scalars(select(MessageModel).where(MessageModel.conversation_id==conversation['conversation_id']).order_by(MessageModel.sequence)).all()
                assert rows[0].timestamp == datetime(2026,1,1,3)
            mismatch = exported['messages'][0] | {'original_timestamp':'2026-01-01T15:00:00+11:00'}
            rejected = client.post('/api/v1/conversations',json={'authorised':True,'messages':[mismatch]})
            assert rejected.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_missing_historical_offset_is_not_invented_and_mixed_times_do_not_crash():
    from app.models import MessageModel
    from app.schemas import Conversation, ConversationMessage
    from app.extraction.rule_based import RuleBasedMemoryExtractor
    legacy = MessageModel(timestamp=datetime(2026,1,1,14),original_timestamp=None)
    assert legacy.observation_timestamp.tzinfo is None
    history = Conversation(conversation_id='C',authorised=True,created_at=datetime.now(timezone.utc),messages=[
        ConversationMessage(message_id='old',role='user',content='I previously used MySQL.',timestamp=datetime(2026,1,1,14)),
        ConversationMessage(message_id='new',role='user',content='I now use PostgreSQL.',timestamp=datetime(2026,1,1,5,tzinfo=timezone.utc)),
    ])
    records = RuleBasedMemoryExtractor().extract(history)
    assert records[0].source_message_ids == ['old']
    assert records[1].source_message_ids == ['new']


def test_structured_import_preserves_source_ids_timestamps_and_reused_export_ids(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fidelity.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_db
    stamp = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc).isoformat()
    payload = {"authorised": True, "messages": [
        {"message_id": "MSG001", "role": "user", "content": "I used MySQL before.", "timestamp": stamp},
        {"message_id": "MSG002", "role": "user", "content": "I now use PostgreSQL.", "timestamp": "2025-01-03T03:04:00Z"},
    ]}
    try:
        with TestClient(app) as client:
            first = client.post("/api/v1/conversations", json=payload)
            assert first.status_code == 201
            assert [message["message_id"] for message in first.json()["messages"]] == ["MSG001", "MSG002"]
            assert first.json()["messages"][0]["timestamp"].startswith("2025-01-02T03:04:00")

            # Typical provider exports restart numbering in every conversation.
            second = client.post("/api/v1/conversations", json=payload)
            assert second.status_code == 201
            assert [message["message_id"] for message in second.json()["messages"]] == ["MSG001", "MSG002"]
    finally:
        app.dependency_overrides.clear()


def test_conversation_source_origin_defaults_to_unknown_and_rejects_unlisted_values(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'source-origin.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            base = {"authorised": True, "messages": [{"role": "user", "content": "A synthetic source fact."}]}
            created = client.post("/api/v1/conversations", json=base)
            assert created.status_code == 201
            assert created.json()["source_origin"] == "unknown"
            synthetic = client.post("/api/v1/conversations", json={**base, "source_origin": "synthetic"})
            assert synthetic.status_code == 201
            synthetic_export = client.get(f"/api/v1/conversations/{synthetic.json()['conversation_id']}/export").json()
            assert synthetic_export["conversation"]["source_origin"] == "synthetic"
            assert "not participant evidence" in synthetic_export["source_origin_notice"]
            invalid = client.post("/api/v1/conversations", json={**base, "source_origin": "participant"})
            assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_pasted_text_creates_one_ordered_record_per_non_empty_line(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pasted.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/conversations", json={
                "authorised": True,
                "pasted_text": "[User] I prefer Python.\n\n[Assistant] Understood.\n[User] This assignment requires Java.",
            })
            assert response.status_code == 201
            messages = response.json()["messages"]
            assert [(item["message_id"], item["role"], item["content"]) for item in messages] == [
                ("MSG001", "User", "I prefer Python."),
                ("MSG002", "Assistant", "Understood."),
                ("MSG003", "User", "This assignment requires Java."),
            ]
    finally:
        app.dependency_overrides.clear()
