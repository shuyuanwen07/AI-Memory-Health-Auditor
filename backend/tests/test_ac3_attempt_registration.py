"""Registration cannot write before the frozen-review verifier succeeds."""
from unittest.mock import MagicMock, patch
import pytest
from app.services.ac3_attempt_ledger import AttemptLedger


def test_failed_frozen_review_cannot_open_a_ledger_transaction():
    engine = MagicMock()
    engine.dialect.name = 'postgresql'
    ledger = AttemptLedger(engine)
    with patch('scripts.ac3_fixed_suite_adapter.compile_mock', side_effect=ValueError('review missing')):
        with pytest.raises(ValueError, match='review missing'):
            ledger.register_reviewed_scope('scope', '/unavailable', 'a' * 64, '0')
    engine.begin.assert_not_called()
