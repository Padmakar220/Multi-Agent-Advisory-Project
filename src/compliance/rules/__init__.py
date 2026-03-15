"""
Compliance rule functions sub-package.

Each module exposes pure functions with the signature:
    (text: str, metadata: dict) -> Optional[ComplianceViolation]

No AWS dependencies are permitted in this sub-package.
"""
