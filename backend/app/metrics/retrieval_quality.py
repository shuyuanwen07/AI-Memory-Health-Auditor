"""Transparent source-evidence retrieval quality metrics."""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MemoryModel, TargetAgentMemoryModel, TargetAgentRetrievalModel, TestCaseModel
from app.schemas import Dimension, RetrievalQualityScores


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values) * 100, 1) if values else None


class RetrievalQualityService:
    """Measure retrieved source evidence against each test's supporting memory.

    Ground-truth and target-store records intentionally use different IDs.  We
    therefore compare the source-message evidence attached to both sides.  It
    is a transparent evidence proxy, not a claim of semantic retrieval recall.
    """

    def calculate(self, run_id: str, db: Session) -> RetrievalQualityScores:
        tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id)).all()
        memory_ids = {memory_id for test in tests for memory_id in (test.supporting_memory_ids or [])}
        ground_truth = {
            row.id: set(row.source_message_ids or [])
            for row in db.scalars(select(MemoryModel).where(MemoryModel.id.in_(memory_ids))).all()
        }
        target_records = {
            row.id: set(row.source_message_ids or [])
            for row in db.scalars(select(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id == run_id)).all()
        }
        retrievals_by_test: dict[str, list[TargetAgentRetrievalModel]] = defaultdict(list)
        for row in db.scalars(select(TargetAgentRetrievalModel).where(TargetAgentRetrievalModel.run_id == run_id)).all():
            retrievals_by_test[row.test_id].append(row)

        recalls: list[float] = []
        precisions: list[float] = []
        freshness_recalls: list[float] = []
        conflict_recalls: list[float] = []
        for test in tests:
            rows = retrievals_by_test.get(test.id, [])
            # A failed cloud call can create a trace before a response exists.
            # Only the trace linked to the durable final response is eligible
            # for scoring. Pre-0016 rows retain a deterministic fallback so
            # historical audits remain readable.
            final_rows = [row for row in rows if row.final_response_id]
            if final_rows:
                rows = final_rows
            elif rows:
                rows = [max(rows, key=lambda row: (row.created_at, row.id))]
            if not rows:
                continue
            expected = set().union(*(ground_truth.get(item, set()) for item in (test.supporting_memory_ids or [])))
            selected = set().union(*(
                target_records.get(memory_id, set())
                for row in rows for memory_id in (row.selected_memory_ids or [])
            ))
            if not expected:
                continue
            overlap = expected & selected
            recall = len(overlap) / len(expected)
            recalls.append(recall)
            if selected:
                precisions.append(len(overlap) / len(selected))
            if test.dimension == Dimension.FRESHNESS.value:
                freshness_recalls.append(recall)
            elif test.dimension == Dimension.CONFLICT_RESOLUTION.value:
                conflict_recalls.append(recall)
        return RetrievalQualityScores(
            tests_measured=len(recalls),
            evidence_recall_at_k=_average(recalls),
            evidence_precision_at_k=_average(precisions),
            update_evidence_recall=_average(freshness_recalls),
            conflict_evidence_coverage=_average(conflict_recalls),
            unnecessary_memory_retrieval_rate=(
                round(100 - sum(precisions) / len(precisions) * 100, 1) if precisions else None
            ),
        )
