"""
Compliance-as-a-Code Library

Standalone Python package encoding FINRA AI framework, NIST AI RMF, and PCI DSS
compliance policies as executable, testable functions.

Public API:
    ComplianceEngine  - main entry point for evaluating text against all active rules
    PolicyRegistry    - runtime rule registration
    ComplianceResult  - result container returned by ComplianceEngine.evaluate()
    ComplianceViolation - individual policy violation
    Severity          - severity enum (critical, high, medium, low)
"""

from src.compliance.models import ComplianceResult, ComplianceViolation, Severity
from src.compliance.registry import PolicyRegistry
from src.compliance.engine import ComplianceEngine

__all__ = [
    "ComplianceEngine",
    "PolicyRegistry",
    "ComplianceResult",
    "ComplianceViolation",
    "Severity",
]
