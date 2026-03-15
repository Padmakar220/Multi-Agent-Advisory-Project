"""
NIST AI Risk Management Framework compliance rules.

Each function is a pure rule with signature:
    (text: str, metadata: dict) -> Optional[ComplianceViolation]

Rules:
    NIST-001  Bias and Fairness
    NIST-002  Transparency Marker
    NIST-003  Robustness Indicator
    NIST-004  Privacy Risk
"""

from __future__ import annotations

import re
from typing import Optional

from src.compliance.models import ComplianceViolation, Severity

# ---------------------------------------------------------------------------
# NIST-001: Bias and Fairness
# ---------------------------------------------------------------------------

# Demographic / protected-class terms that may indicate bias
_DEMOGRAPHIC_TERMS = re.compile(
    r"\b(race|racial|ethnicity|ethnic|gender|sex|age|religion|religious|"
    r"national origin|disability|sexual orientation|marital status|"
    r"african american|hispanic|latino|asian|white|black|female|male|"
    r"elderly|young|christian|muslim|jewish|hindu)\b",
    re.IGNORECASE,
)

# Differential treatment language
_DIFFERENTIAL_TREATMENT = re.compile(
    r"\b(because (they are|of their|he is|she is)|"
    r"(men|women|minorities|elderly people|young people) (tend to|are more|are less|should)|"
    r"(avoid|prefer|exclude) (clients?|customers?|investors?) (who are|based on))\b",
    re.IGNORECASE,
)


def check_bias_and_fairness(text: str, metadata: dict) -> Optional[ComplianceViolation]:
    """NIST-001: Detect demographic or protected-class bias indicators.

    Triggers when demographic terms appear alongside differential treatment
    language, or when metadata flags a bias score above threshold.
    """
    if not text or not text.strip():
        return None

    has_demographic = bool(_DEMOGRAPHIC_TERMS.search(text))
    has_differential = bool(_DIFFERENTIAL_TREATMENT.search(text))

    # Check metadata bias score
    bias_score = metadata.get("bias_score", 0.0)
    bias_threshold = metadata.get("bias_threshold", 0.7)

    if (has_demographic and has_differential) or bias_score >= bias_threshold:
        return ComplianceViolation(
            policy_domain="NIST",
            rule_id="NIST-001",
            rule_name="Bias and Fairness",
            severity=Severity.HIGH,
            description=(
                "Potential demographic bias detected in AI output. "
                "NIST AI RMF requires AI systems to be evaluated for bias "
                "against protected classes and demographic groups."
            ),
            remediation_suggestion=(
                "Review the output for differential treatment based on protected "
                "characteristics. Ensure recommendations are based solely on "
                "financial factors and not demographic attributes. "
                "Run bias evaluation metrics before deployment."
            ),
        )
    return None


# ---------------------------------------------------------------------------
# NIST-002: Transparency Marker
# ---------------------------------------------------------------------------

# Explainability markers that indicate the model is transparent about its reasoning
_EXPLAINABILITY_MARKERS = re.compile(
    r"\b(because|due to|based on|the reason (is|being)|"
    r"this (is|was) (calculated|determined|derived) (by|from|using)|"
    r"the (model|algorithm|system) (determined|calculated|estimated)|"
    r"confidence (level|score|interval)|"
    r"(high|low|medium) confidence|"
    r"uncertainty|margin of error|"
    r"the (key|main|primary) factor(s?)|"
    r"driven by|influenced by|weighted by)\b",
    re.IGNORECASE,
)

# Contexts where explainability is expected
_DECISION_LANGUAGE = re.compile(
    r"\b(recommend|advise|suggest|decision|conclusion|assessment|"
    r"analysis (shows|indicates|reveals)|result(s?) (show|indicate)|"
    r"the (best|optimal|recommended) (option|choice|action|strategy))\b",
    re.IGNORECASE,
)


def check_transparency_marker(text: str, metadata: dict) -> Optional[ComplianceViolation]:
    """NIST-002: Flag outputs lacking explainability markers.

    When a decision or recommendation is made, the output should include
    reasoning or confidence indicators.
    """
    if not text or not text.strip():
        return None

    has_decision = bool(_DECISION_LANGUAGE.search(text))
    if not has_decision:
        return None

    has_explainability = bool(_EXPLAINABILITY_MARKERS.search(text))
    if not has_explainability and not metadata.get("explainability_provided", False):
        return ComplianceViolation(
            policy_domain="NIST",
            rule_id="NIST-002",
            rule_name="Transparency Marker",
            severity=Severity.MEDIUM,
            description=(
                "AI decision or recommendation output lacks explainability markers. "
                "NIST AI RMF requires AI systems to provide transparency about "
                "how decisions are made."
            ),
            remediation_suggestion=(
                "Add reasoning or confidence indicators to the output, such as "
                "'Based on [factors], the recommendation is...' or include a "
                "confidence score and the key factors driving the decision."
            ),
        )
    return None


# ---------------------------------------------------------------------------
# NIST-003: Robustness Indicator
# ---------------------------------------------------------------------------

# Adversarial / out-of-distribution input patterns
_ADVERSARIAL_PATTERNS = re.compile(
    r"(ignore (previous|all|prior) instructions?|"
    r"disregard (your|the) (system|previous|prior) (prompt|instructions?)|"
    r"you are now|pretend (you are|to be)|act as (if you are|a different)|"
    r"jailbreak|bypass (safety|filter|restriction|guardrail)|"
    r"<\|.*?\|>|"                          # token injection patterns
    r"\[INST\]|\[/INST\]|"                 # instruction injection
    r"###\s*(Human|Assistant|System):|"    # role injection
    r"<system>|</system>|<user>|</user>)", # XML injection
    re.IGNORECASE | re.DOTALL,
)

# Out-of-distribution: extreme or nonsensical financial values
_OOD_FINANCIAL = re.compile(
    r"\b(\d{15,}%|"                        # absurdly large percentages
    r"return of \d{4,}%|"                  # 1000%+ returns
    r"price of \$\d{8,})\b",              # $100M+ single asset price
    re.IGNORECASE,
)


def check_robustness_indicator(text: str, metadata: dict) -> Optional[ComplianceViolation]:
    """NIST-003: Detect adversarial or out-of-distribution inputs.

    Triggers on prompt injection attempts, instruction override patterns,
    or extreme out-of-distribution financial values.
    """
    if not text or not text.strip():
        return None

    if _ADVERSARIAL_PATTERNS.search(text) or _OOD_FINANCIAL.search(text):
        return ComplianceViolation(
            policy_domain="NIST",
            rule_id="NIST-003",
            rule_name="Robustness Indicator",
            severity=Severity.CRITICAL,
            description=(
                "Adversarial or out-of-distribution input detected. "
                "The input contains patterns consistent with prompt injection, "
                "instruction override attempts, or extreme out-of-distribution values."
            ),
            remediation_suggestion=(
                "Reject or sanitize the input before processing. "
                "Log the attempt for security review. "
                "Implement input validation and prompt injection defenses."
            ),
        )
    return None


# ---------------------------------------------------------------------------
# NIST-004: Privacy Risk
# ---------------------------------------------------------------------------

# PII patterns (non-financial — financial card data is handled by PCI_DSS rules)
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

_SSN_PATTERN = re.compile(
    r"\b(?!000|666|9\d{2})\d{3}[- ](?!00)\d{2}[- ](?!0000)\d{4}\b"
)

_PHONE_PATTERN = re.compile(
    r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"
)

_DOB_PATTERN = re.compile(
    r"\b(date of birth|dob|born on|birthday)[:\s]+\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b",
    re.IGNORECASE,
)

_ADDRESS_PATTERN = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9\s]{3,50}\s+(street|st|avenue|ave|road|rd|"
    r"boulevard|blvd|drive|dr|lane|ln|court|ct|way|place|pl)\b",
    re.IGNORECASE,
)


def check_privacy_risk(text: str, metadata: dict) -> Optional[ComplianceViolation]:
    """NIST-004: Flag PII exposure risk in inputs or outputs.

    Detects email addresses, SSNs, phone numbers, dates of birth, and
    physical addresses that should not appear in AI inputs/outputs.
    """
    if not text or not text.strip():
        return None

    pii_found = []
    if _EMAIL_PATTERN.search(text):
        pii_found.append("email address")
    if _SSN_PATTERN.search(text):
        pii_found.append("Social Security Number")
    if _PHONE_PATTERN.search(text):
        pii_found.append("phone number")
    if _DOB_PATTERN.search(text):
        pii_found.append("date of birth")
    if _ADDRESS_PATTERN.search(text):
        pii_found.append("physical address")

    if pii_found:
        pii_list = ", ".join(pii_found)
        return ComplianceViolation(
            policy_domain="NIST",
            rule_id="NIST-004",
            rule_name="Privacy Risk",
            severity=Severity.HIGH,
            description=(
                f"Personally Identifiable Information (PII) detected: {pii_list}. "
                "NIST AI RMF requires AI systems to protect individual privacy "
                "and minimize PII exposure."
            ),
            remediation_suggestion=(
                "Remove or redact PII before passing data to AI systems. "
                "Use tokenization or pseudonymization for sensitive identifiers. "
                "Ensure PII is not logged or stored in AI inputs/outputs."
            ),
        )
    return None


# ---------------------------------------------------------------------------
# Public registry of all NIST rules
# ---------------------------------------------------------------------------

NIST_RULES: list[tuple[str, object]] = [
    ("NIST-001", check_bias_and_fairness),
    ("NIST-002", check_transparency_marker),
    ("NIST-003", check_robustness_indicator),
    ("NIST-004", check_privacy_risk),
]
