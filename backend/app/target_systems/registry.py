"""Registry kept intentionally small until an external system is authorised."""
from sqlalchemy.orm import Session

from app.schemas import AuditRun
from app.target_systems.controlled import ControlledTargetSystemAdapter
from app.target_systems.interfaces import TargetSystemAdapter


def get_target_system_adapter(db: Session, audit: AuditRun) -> TargetSystemAdapter:
    """Return the configured system under test.

    The adapter identity is frozen in audit reproducibility metadata.  Only the
    local controlled adapter is registered in Foundation; external adapters
    are an explicit future integration rather than a silent provider switch.
    """
    return ControlledTargetSystemAdapter(db, audit)
