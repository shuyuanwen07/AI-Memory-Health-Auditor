"""Replaceable systems under test.

The Auditor evaluates a target system through this package rather than
coupling route handlers to one memory-store implementation.  Foundation ships
with the controlled local system; future adapters can wrap an authorised
external agent without changing the audit workflow contract.
"""

from app.target_systems.registry import get_target_system_adapter

__all__ = ["get_target_system_adapter"]
