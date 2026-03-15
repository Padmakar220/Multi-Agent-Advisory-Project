"""
Data models for the Compliance-as-a-Code library.

Defines:
    Severity           - ordered enum of violation severity levels
    ComplianceViolation - a single detected policy breach
    ComplianceResult    - aggregate result returned by ComplianceEngine.evaluate()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """Severity levels in descending order of criticality."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    # Allow ordered comparison: CRITICAL > HIGH > MEDIUM > LOW
    _order = ["critical", "high", "medium", "low"]

    def __lt__(self, other: "Severity") -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self._order.index(self.value) > other._order.index(other.value)

    def __le__(self, other: "Severity") -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self._order.index(self.value) >= other._order.index(other.value)

    def __gt__(self, other: "Severity") -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self._order.index(self.value) < other._order.index(other.value)

    def __ge__(self, other: "Severity") -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self._order.index(self.value) <= other._order.index(other.value)


@dataclass
class ComplianceViolation:
    """A single detected breach of a compliance policy rule."""

    policy_domain: str          # "FINRA", "NIST", "PCI_DSS"
    rule_id: str                # e.g. "FINRA-001"
    rule_name: str
    severity: Severity
    description: str
    remediation_suggestion: str


@dataclass
class ComplianceResult:
    """Aggregate result returned by ComplianceEngine.evaluate()."""

    violations: list[ComplianceViolation] = field(default_factory=list)
    is_compliant: bool = True   # False if any violation is present
