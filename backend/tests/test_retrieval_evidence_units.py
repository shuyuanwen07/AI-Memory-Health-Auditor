"""Same-message updates must not inflate recorded-evidence recall."""
from datetime import datetime, timezone
from types import SimpleNamespace as Row

import pytest

from app.metrics.retrieval_quality import RetrievalQualityService


@pytest.mark.parametrize("target_text,expected_recall", [
    ("I used MySQL before", 0.0),
    ("the backend now uses PostgreSQL", 100.0),
    ("THE backend now uses PostgreSQL!", 100.0),
])
def test_same_source_different_fact_is_not_retrieval(target_text, expected_recall):
    batches = iter([
        [Row(id="T1", supporting_memory_ids=["G1"], dimension="freshness")],
        [Row(id="G1", canonical_value="the backend now uses PostgreSQL", source_message_ids=["MSG1"])],
        [Row(id="TM1", canonical_value=target_text, source_message_ids=["MSG1"])],
        [Row(id="RET1", test_id="T1", selected_memory_ids=["TM1"],
             final_response_id="R1", created_at=datetime.now(timezone.utc))],
    ])
    db = Row(scalars=lambda query: Row(all=lambda: next(batches)))
    score = RetrievalQualityService().calculate("RUN1", db)
    assert score.evidence_recall_at_k == expected_recall
    assert score.update_evidence_recall == expected_recall
    assert score.evidence_precision_at_k == expected_recall


def test_same_fact_from_unrelated_source_is_not_gold_evidence():
    batches = iter([
        [Row(id="T1", supporting_memory_ids=["G1"], dimension="conflict_resolution")],
        [Row(id="G1", canonical_value="Use Go", source_message_ids=["MSG1"])],
        [Row(id="TM1", canonical_value="Use Go", source_message_ids=["MSG2"])],
        [Row(id="RET1", test_id="T1", selected_memory_ids=["TM1"],
             final_response_id="R1", created_at=datetime.now(timezone.utc))],
    ])
    score = RetrievalQualityService().calculate("RUN1", Row(scalars=lambda query: Row(all=lambda: next(batches))))
    assert score.conflict_evidence_coverage == 0


@pytest.mark.parametrize('saved_answer', [False, True])
def test_unlinked_attempts_never_inflate_completed_answer_evidence(saved_answer):
    now = datetime.now(timezone.utc)
    traces = [Row(id='FAILED', test_id='T1', selected_memory_ids=['TM_GOOD'],
                  final_response_id=None, created_at=now)]
    if saved_answer:
        # A saved answer used the wrong evidence; a later failed attempt found
        # the right evidence. Only the saved answer's trace is measurable.
        traces.append(Row(id='SAVED', test_id='T1', selected_memory_ids=['TM_BAD'],
                          final_response_id='R1', created_at=now))
    batches = iter([
        [Row(id='T1', supporting_memory_ids=['G1'], dimension='accuracy')],
        [Row(id='G1', canonical_value='Use Java', source_message_ids=['MSG1'])],
        [Row(id='TM_GOOD', canonical_value='Use Java', source_message_ids=['MSG1']),
         Row(id='TM_BAD', canonical_value='Use Python', source_message_ids=['MSG2'])],
        traces,
    ])
    score = RetrievalQualityService().calculate('RUN1', Row(scalars=lambda query: Row(all=lambda: next(batches))))
    assert score.unlinked_attempts_excluded == 1
    assert score.tests_measured == int(saved_answer)
    assert score.evidence_recall_at_k == (0 if saved_answer else None)
    assert score.evidence_precision_at_k == (0 if saved_answer else None)
