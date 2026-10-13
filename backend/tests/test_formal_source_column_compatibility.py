"""Old-column projection is an engineering fixture, not independent research evidence."""
import pytest
from fastapi import HTTPException
from sqlalchemy import Table, select
from sqlalchemy.orm import DeclarativeBase

from app.models import AuditRunModel, MessageModel
from app.services import formal_freeze
from test_reviewed_acceptance import study as reviewed_study

study = reviewed_study


def test_nullable_source_offset_column_preserves_old_receipts_but_new_provenance_stays_frozen(study,monkeypatch):
    _,factory,run,_ = study
    with factory() as db:
        audit = db.get(AuditRunModel,run)
        messages = db.scalars(select(MessageModel).where(MessageModel.conversation_id==audit.conversation_id)).all()
        for message in messages:
            message.original_timestamp = None
        db.commit()
        # Reflect exactly the pre-0025 columns against the same stored rows.
        # This does not edit a schema or source file while tests are running.
        class LegacyBase(DeclarativeBase):
            pass
        class LegacyMessage(LegacyBase):
            __table__ = Table('messages',LegacyBase.metadata,autoload_with=db.get_bind(),
                include_columns=[column.name for column in MessageModel.__table__.columns if column.name!='original_timestamp'])
        with monkeypatch.context() as legacy:
            legacy.setattr(formal_freeze,'MessageModel',LegacyMessage)
            old_receipt = formal_freeze.formal_input_signature(db,audit)
        assert formal_freeze.formal_input_signature(db,audit) == old_receipt
        audit.reproducibility_metadata = {**audit.reproducibility_metadata,'formal_input_sha256':old_receipt}
        db.commit()
        formal_freeze.assert_formal_inputs_frozen(db,audit)
        messages[0].original_timestamp = messages[0].timestamp.isoformat()+'+00:00'
        db.commit()
        with pytest.raises(HTTPException) as changed:
            formal_freeze.assert_formal_inputs_frozen(db,audit)
        assert changed.value.status_code == 409
        new_receipt = formal_freeze.formal_input_signature(db,audit)
        audit.reproducibility_metadata = {**audit.reproducibility_metadata,'formal_input_sha256':new_receipt}
        db.commit()
        formal_freeze.assert_formal_inputs_frozen(db,audit)
        messages[0].original_timestamp = messages[0].timestamp.isoformat()+'+01:00'
        db.commit()
        with pytest.raises(HTTPException):
            formal_freeze.assert_formal_inputs_frozen(db,audit)
