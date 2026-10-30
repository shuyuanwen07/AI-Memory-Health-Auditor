"""Keep newly prepared audits on one installed software implementation.

Legacy audits have no source snapshot: reading or resuming them does not imply
that their original implementation can be verified. This guard covers application
source, not installed dependencies or a provider's upstream model revisions.
"""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select

from app.services.formal_freeze import formal_runtime_signature
from app.test_generator.topic_scoped_v41 import TopicScopedRuleBasedTestGenerator


def audit_runtime_signature() -> dict[str, str]:
    return {**formal_runtime_signature(),
            "protocol": "audit-runtime-v1",
            "generator": TopicScopedRuleBasedTestGenerator.VERSION}


def assert_audit_runtime_frozen(audit) -> None:
    metadata = audit.reproducibility_metadata or {}
    if getattr(audit, 'status', None) == 'RESEARCH_STAGED' or metadata.get('ac3_staged_suite') or metadata.get('ac3_paired_retest'):
        raise HTTPException(409, 'This research suite is staged only. Live execution is disabled until a verified budget guard and release path are implemented.')
    if "audit_runtime_signature" not in metadata:
        return  # Legacy provenance is unknown; do not invent a snapshot.
    if metadata["audit_runtime_signature"] != audit_runtime_signature():
        raise HTTPException(409,
            "The audit software has changed since this audit was prepared. "
            "Start a new audit with the current software or restore its original version. "
            "Existing questions, answers and results have been preserved.")


def refresh_failed_preexecution_generation(db, audit) -> bool:
    """Permit a failed, unsaved first generation to retry under current code.

    This narrow exception preserves the old runtime signature in metadata and
    is available only while the audit is still CREATED with no saved questions
    or target answers. Once any test or answer exists, the freeze stays strict.
    """
    metadata = dict(audit.reproducibility_metadata or {})
    previous = metadata.get("audit_runtime_signature")
    current = audit_runtime_signature()
    if not previous or previous == current or audit.status != "CREATED":
        return False

    from app.models import TargetResponseModel, TestCaseModel
    if db.scalar(select(TestCaseModel.id).where(TestCaseModel.run_id == audit.id).limit(1)):
        return False
    if db.scalar(select(TargetResponseModel.id).where(TargetResponseModel.run_id == audit.id).limit(1)):
        return False
    observations = metadata.get("generation_observations") or []
    if not observations or observations[-1].get("status") != "failed":
        return False

    refreshes = list(metadata.get("audit_runtime_refreshes") or [])
    refreshes.append({
        "previous_signature": previous,
        "current_signature": current,
        "reason": "Retry after test generation failed before questions or answers were saved.",
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    })
    metadata["audit_runtime_signature"] = current
    metadata["audit_runtime_refreshes"] = refreshes
    audit.reproducibility_metadata = metadata
    db.commit()
    db.refresh(audit)
    return True


def inherit_preexecution_runtime_refresh(target, source) -> None:
    """Carry a source's safe pre-execution retry provenance to suite peers."""
    source_metadata = source.reproducibility_metadata or {}
    current = source_metadata.get("audit_runtime_signature")
    source_refreshes = source_metadata.get("audit_runtime_refreshes") or []
    if not current or not source_refreshes:
        return
    metadata = dict(target.reproducibility_metadata or {})
    previous = metadata.get("audit_runtime_signature")
    if not previous or previous == current:
        return
    refreshes = list(metadata.get("audit_runtime_refreshes") or [])
    refreshes.append({
        "previous_signature": previous,
        "current_signature": current,
        "reason": "Received the shared test suite generated after a safe pre-execution retry.",
        "source_run_id": source.id,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    })
    metadata["audit_runtime_signature"] = current
    metadata["audit_runtime_refreshes"] = refreshes
    target.reproducibility_metadata = metadata
