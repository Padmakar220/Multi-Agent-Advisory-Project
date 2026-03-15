"""
PCI DSS compliance rules.

Each function is a pure rule with signature:
    (text: str, metadata: dict) -> Optional[ComplianceViolation]

Rules:
    PCI-001  PAN Detection (Luhn-validated card numbers)
    PCI-002  CVV Detection
    PCI-003  Expiry Detection
    PCI-004  Sensitive Auth Data
    PCI-005  Data Minimisation
"""

from __future__ import annotations

import re
from typing import Optional

from src.compliance.models import ComplianceViolation, Severity

# ---------------------------------------------------------------------------
# Luhn algorithm helper
# ---------------------------------------------------------------------------


def _luhn_check(number: str) -> bool:
    """Return True if the digit string passes the Luhn algorithm."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    total = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


# ---------------------------------------------------------------------------
# PCI-001: PAN Detection
# ---------------------------------------------------------------------------

# Matches 13–19 digit sequences, optionally separated by spaces or hyphens
_PAN_PATTERN = re.compile(
    r"\b(?:\d[ \-]?){12,18}\d\b"
)


def check_pan_detection(text: str, metadata: dict) -> Optional[ComplianceViolation]:
    """PCI-001: Detect payment card numbers (Luhn-validated).

    Scans for digit sequences of 13–19 digits (with optional separators)
    and validates each candidate with the Luhn algorithm.
    """
    if not text or not text.strip():
        return None

    for match in _PAN_PATTERN.finditer(text):
        raw = match.group(0)
        digits_only = re.sub(r"[ \-]", "", raw)
        if 13 <= len(digits_only) <= 19 and _luhn_check(digits_only):
            return ComplianceViolation(
                policy_domain="PCI_DSS",
                rule_id="PCI-001",
                rule_name="PAN Detection",
                severity=Severity.CRITICAL,
                description=(
                    "Primary Account Number (PAN) detected in text. "
                    "PCI DSS prohibits storing, processing, or transmitting "
                    "unmasked card numbers outside of the cardholder data environment."
                ),
                remediation_suggestion=(
                    "Immediately remove or mask the PAN. "
                    "Replace with a token or truncated representation (e.g., last 4 digits). "
                    "Ensure card numbers are never passed to AI systems."
                ),
            )
    return None


# ---------------------------------------------------------------------------
# PCI-002: CVV Detection
# ---------------------------------------------------------------------------

# CVV context: 3-4 digits near CVV/CVC/security code keywords
_CVV_PATTERN = re.compile(
    r"\b(cvv|cvc|cvv2|cvc2|card (verification|security) (value|code|number)|"
    r"security code)[:\s]*\d{3,4}\b",
    re.IGNORECASE,
)

# Also catch standalone 3-4 digit codes near card-related context
_CVV_CONTEXT_PATTERN = re.compile(
    r"\b\d{3,4}\b(?=.*\b(cvv|cvc|security code|verification)\b)"
    r"|\b(cvv|cvc|security code|verification)\b.*?\b\d{3,4}\b",
    re.IGNORECASE | re.DOTALL,
)


def check_cvv_detection(text: str, metadata: dict) -> Optional[ComplianceViolation]:
    """PCI-002: Detect 3-4 digit card verification values in context.

    Triggers when CVV/CVC keywords appear alongside 3-4 digit values.
    """
    if not text or not text.strip():
        return None

    if _CVV_PATTERN.search(text) or _CVV_CONTEXT_PATTERN.search(text):
        return ComplianceViolation(
            policy_domain="PCI_DSS",
            rule_id="PCI-002",
            rule_name="CVV Detection",
            severity=Severity.CRITICAL,
            description=(
                "Card Verification Value (CVV/CVC) detected in text. "
                "PCI DSS strictly prohibits storing CVV/CVC data after authorization, "
                "and it must never appear in AI inputs or outputs."
            ),
            remediation_suggestion=(
                "Remove CVV/CVC values immediately. "
                "CVV data must never be stored, logged, or transmitted to AI systems. "
                "Implement input sanitization to strip CVV patterns before processing."
            ),
        )
    return None


# ---------------------------------------------------------------------------
# PCI-003: Expiry Detection
# ---------------------------------------------------------------------------

# MM/YY and MM/YYYY patterns in card context
_EXPIRY_PATTERN = re.compile(
    r"\b(expir(y|ation|es?)|exp\.?|valid (thru|through|until))[:\s]*"
    r"(0[1-9]|1[0-2])[/\-](2[0-9]|20[2-9]\d)\b",
    re.IGNORECASE,
)

# Standalone MM/YY or MM/YYYY that looks like a card expiry
_EXPIRY_STANDALONE = re.compile(
    r"\b(0[1-9]|1[0-2])[/\-](2[0-9]|20[2-9]\d)\b"
)


def check_expiry_detection(text: str, metadata: dict) -> Optional[ComplianceViolation]:
    """PCI-003: Detect card expiry date patterns (MM/YY, MM/YYYY).

    Triggers on expiry keywords with date patterns, or standalone date
    patterns that match card expiry format.
    """
    if not text or not text.strip():
        return None

    if _EXPIRY_PATTERN.search(text):
        return ComplianceViolation(
            policy_domain="PCI_DSS",
            rule_id="PCI-003",
            rule_name="Expiry Detection",
            severity=Severity.HIGH,
            description=(
                "Card expiry date detected in text. "
                "PCI DSS requires that card expiry dates be protected and "
                "not exposed in AI inputs or outputs."
            ),
            remediation_suggestion=(
                "Remove card expiry date information. "
                "Expiry dates should not be passed to AI systems. "
                "Use tokenization to represent card data."
            ),
        )
    return None


# ---------------------------------------------------------------------------
# PCI-004: Sensitive Auth Data
# ---------------------------------------------------------------------------

_SENSITIVE_AUTH_PATTERNS = re.compile(
    r"\b(full (magnetic stripe|track [12] data|track data)|"
    r"pin (block|value|data)|"
    r"chip (data|contents)|"
    r"logging (card|payment|auth(entication)?) data|"
    r"store (cvv|cvc|pin|track data|magnetic stripe)|"
    r"auth(entication)? data (logged|stored|saved|recorded))\b",
    re.IGNORECASE,
)


def check_sensitive_auth_data(text: str, metadata: dict) -> Optional[ComplianceViolation]:
    """PCI-004: Flag logging or storage of sensitive authentication data.

    Detects references to full magnetic stripe data, PIN blocks, chip data,
    or explicit logging of authentication data.
    """
    if not text or not text.strip():
        return None

    if _SENSITIVE_AUTH_PATTERNS.search(text):
        return ComplianceViolation(
            policy_domain="PCI_DSS",
            rule_id="PCI-004",
            rule_name="Sensitive Auth Data",
            severity=Severity.CRITICAL,
            description=(
                "Sensitive authentication data (SAD) detected. "
                "PCI DSS prohibits storing sensitive authentication data "
                "such as full magnetic stripe, PIN blocks, or chip data "
                "after authorization, even if encrypted."
            ),
            remediation_suggestion=(
                "Immediately purge sensitive authentication data. "
                "Implement controls to prevent SAD from entering AI pipelines. "
                "Review logging configurations to ensure SAD is never written to logs."
            ),
        )
    return None


# ---------------------------------------------------------------------------
# PCI-005: Data Minimisation
# ---------------------------------------------------------------------------

_DATA_RETENTION_PATTERNS = re.compile(
    r"\b(retain(ing)?|keep(ing)?|store?|storing|saving|archiv(e|ing)) "
    r"(all |full |complete |entire )?"
    r"(cardholder|card holder|payment card|credit card|debit card) "
    r"(data|information|details|records?|history)\b",
    re.IGNORECASE,
)

_UNNECESSARY_FIELDS = re.compile(
    r"\b(full card number|complete pan|all card details|"
    r"entire cardholder record|full payment data)\b",
    re.IGNORECASE,
)


def check_data_minimisation(text: str, metadata: dict) -> Optional[ComplianceViolation]:
    """PCI-005: Flag unnecessary retention of cardholder data.

    Detects language indicating that full cardholder data is being retained
    beyond what is necessary for the transaction.
    """
    if not text or not text.strip():
        return None

    if _DATA_RETENTION_PATTERNS.search(text) or _UNNECESSARY_FIELDS.search(text):
        return ComplianceViolation(
            policy_domain="PCI_DSS",
            rule_id="PCI-005",
            rule_name="Data Minimisation",
            severity=Severity.MEDIUM,
            description=(
                "Unnecessary cardholder data retention detected. "
                "PCI DSS requires data minimisation: only retain cardholder data "
                "that is necessary for business, legal, or regulatory purposes."
            ),
            remediation_suggestion=(
                "Review data retention policies and purge unnecessary cardholder data. "
                "Implement a data retention schedule that limits storage to the minimum "
                "required period. Use tokenization to replace stored card data."
            ),
        )
    return None


# ---------------------------------------------------------------------------
# Public registry of all PCI DSS rules
# ---------------------------------------------------------------------------

PCI_DSS_RULES: list[tuple[str, object]] = [
    ("PCI-001", check_pan_detection),
    ("PCI-002", check_cvv_detection),
    ("PCI-003", check_expiry_detection),
    ("PCI-004", check_sensitive_auth_data),
    ("PCI-005", check_data_minimisation),
]
