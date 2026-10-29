"""Import synthetic reviewed source into a disposable PostgreSQL only."""
from unittest.mock import patch
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import ConversationModel
from app.services.ac3_reviewed_source_import import import_reviewed_ac3_sources
from test_ac3_atomic_settlement_postgres import prepared as prepared, pytestmark as pytestmark
from test_ac3_reviewed_source_import import fixture_plan as fixture_plan


def test_postgres_import_preserves_existing_data_and_revalidates(prepared, fixture_plan):
    engine, _, _ = prepared
    frozen, digest, compile_fake = fixture_plan
    with Session(engine) as db: before = set(db.scalars(select(ConversationModel.id)).all())
    with patch('app.services.ac3_reviewed_source_import.compile_mock', side_effect=compile_fake), patch('scripts.ac3_database_mapping.compile_mock', side_effect=compile_fake):
        result = import_reviewed_ac3_sources(engine, frozen_path=frozen, frozen_sha256=digest, reservation='0')
        assert result['status']=='imported' and result['memory_count']==56
        assert import_reviewed_ac3_sources(engine, frozen_path=frozen, frozen_sha256=digest, reservation='0')['status']=='already_imported'
    with Session(engine) as db:
        after = set(db.scalars(select(ConversationModel.id)).all())
        assert before < after and len(after-before)==8
