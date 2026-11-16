"""Counterexamples to a declared exact-string functional dependency."""

from .core import AuditError, Limits, audit, audit_many

__all__ = ["AuditError", "Limits", "audit", "audit_many"]
__version__ = "0.3.2"
