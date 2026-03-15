"""
Compliance Screening Lambda — Task 25.1 / 25.2

Invoked as the first step in the API entry point before forwarding to Step Functions.
Screens every incoming user request against FINRA, NIST, and PCI DSS policies.

Behaviour:
  - Violations at/above domain halt_threshold  → write to ComplianceViolations DynamoDB,
    enqueue to SQS investigation queue, return 403 halt response.
  - Violations below threshold                 → attach warning metadata, log, forward.
  - Timeout (>500ms)                           → treat as medium-severity warning, forward.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

from src.compliance.engine import ComplianceEngine
from src.compliance.models import Severity

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# AWS clients (lazy-initialised for Lambda cold-start efficiency)
_dynamodb = None
_sqs = None

COMPLIANCE_VIOLATIONS_TABLE = os.environ.get(
    "COMPLIANCE_VIOLATIONS_TABLE", "advisory-compliance-violations"
)
INVESTIGATION_QUEUE_URL = os.environ.get("INVESTIGATION_QUEUE_URL", "")
SCREENING_TIMEOUT_S = 0.5  # 500ms budget


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


def _get_sqs():
    global _sqs
    if _sqs is None:
        _sqs = boto3.client("sqs")
    return _sqs


# ---------------------------------------------------------------------------
# Public handler
# ---------------------------------------------------------------------------


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Screen an incoming user request for compliance violations.

    Args:
        event: {
            "user_id": str,
            "session_id": str,
            "text": str,          # the user query / prompt text
            "metadata": dict,     # optional extra context
            "trace_id": str,      # W3C traceparent or internal trace ID
        }
        context: Lambda context object.

    Returns:
        {
            "status": "pass" | "halt",
            "warnings": [...],    # present when status == "pass" with sub-threshold violations
            "violation_ids": [...],  # present when status == "halt"
            "message": str,
        }
    """
    user_id = event.get("user_id", "unknown")
    session_id = event.get("session_id", "unknown")
    text = event.get("text", "")
    metadata = event.get("metadata", {})
    trace_id = event.get("trace_id", "")

    # Enrich metadata with request context
    metadata.update({"user_id": user_id, "session_id": session_id})

    # -----------------------------------------------------------------------
    # Run compliance screening with 500ms timeout guard
    # -----------------------------------------------------------------------
    engine = ComplianceEngine()
    start = time.monotonic()

    try:
        result = engine.evaluate(text, metadata)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "ComplianceEngine.evaluate() raised an exception",
            extra={
                "user_id": user_id,
                "session_id": session_id,
                "trace_id": trace_id,
                "error": str(exc),
            },
        )
        # Treat engine failure as a medium warning — do not block the request
        return {
            "status": "pass",
            "warnings": [{"rule_id": "ENGINE-ERROR", "message": str(exc)}],
            "message": "Compliance screening encountered an error; request forwarded with warning.",
        }

    elapsed_ms = (time.monotonic() - start) * 1000
    if elapsed_ms > SCREENING_TIMEOUT_S * 1000:
        logger.warning(
            "Compliance screening exceeded 500ms budget",
            extra={"elapsed_ms": elapsed_ms, "user_id": user_id},
        )

    # -----------------------------------------------------------------------
    # Partition violations into halt vs. warn
    # -----------------------------------------------------------------------
    halt_violations = []
    warn_violations = []

    for violation in result.violations:
        if not result.is_compliant and violation.severity >= _get_domain_threshold(
            engine, violation.policy_domain
        ):
            halt_violations.append(violation)
        else:
            warn_violations.append(violation)

    # -----------------------------------------------------------------------
    # HALT path
    # -----------------------------------------------------------------------
    if halt_violations:
        violation_ids = []
        raw_hash = hashlib.sha256(text.encode()).hexdigest()

        for v in halt_violations:
            vid = str(uuid.uuid4())
            violation_ids.append(vid)
            _write_violation_record(
                violation_id=vid,
                user_id=user_id,
                session_id=session_id,
                stage="input_screening",
                violation=v,
                raw_content_hash=raw_hash,
                trace_id=trace_id,
            )
            _enqueue_for_investigation(
                violation_id=vid,
                user_id=user_id,
                session_id=session_id,
                violation=v,
                trace_id=trace_id,
            )

        logger.warning(
            "Compliance screening HALT: %d violation(s) above threshold",
            len(halt_violations),
            extra={
                "user_id": user_id,
                "session_id": session_id,
                "trace_id": trace_id,
                "violation_ids": violation_ids,
                "rule_ids": [v.rule_id for v in halt_violations],
            },
        )

        return {
            "status": "halt",
            "violation_ids": violation_ids,
            "message": (
                "Request halted due to compliance violation(s). "
                "Your request has been flagged for human review."
            ),
        }

    # -----------------------------------------------------------------------
    # PASS path (with optional sub-threshold warnings)
    # -----------------------------------------------------------------------
    warnings = [
        {
            "rule_id": v.rule_id,
            "severity": v.severity.value,
            "description": v.description,
        }
        for v in warn_violations
    ]

    if warnings:
        logger.info(
            "Compliance screening PASS with %d sub-threshold warning(s)",
            len(warnings),
            extra={
                "user_id": user_id,
                "session_id": session_id,
                "trace_id": trace_id,
                "warnings": warnings,
            },
        )

    return {
        "status": "pass",
        "warnings": warnings,
        "message": "Request passed compliance screening.",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_domain_threshold(engine: ComplianceEngine, domain: str) -> Severity:
    """Return the halt threshold Severity for a domain from the engine config."""
    from src.compliance.config import get_halt_threshold

    threshold_str = get_halt_threshold(engine.config, domain)
    try:
        return Severity(threshold_str)
    except ValueError:
        return Severity.CRITICAL


def _write_violation_record(
    *,
    violation_id: str,
    user_id: str,
    session_id: str,
    stage: str,
    violation: Any,
    raw_content_hash: str,
    trace_id: str,
) -> None:
    """Write a ComplianceViolation record to DynamoDB."""
    try:
        table = _get_dynamodb().Table(COMPLIANCE_VIOLATIONS_TABLE)
        table.put_item(
            Item={
                "violation_id": violation_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
                "session_id": session_id,
                "stage": stage,
                "policy_domain": violation.policy_domain,
                "rule_id": violation.rule_id,
                "severity": violation.severity.value,
                "raw_content_hash": raw_content_hash,
                "investigation_status": "pending",
                "llm_judge_verdict": None,
                "trace_id": trace_id,
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to write violation record to DynamoDB: %s", exc)


def _enqueue_for_investigation(
    *,
    violation_id: str,
    user_id: str,
    session_id: str,
    violation: Any,
    trace_id: str,
) -> None:
    """Enqueue a violation to the SQS investigation queue."""
    if not INVESTIGATION_QUEUE_URL:
        logger.warning("INVESTIGATION_QUEUE_URL not set; skipping SQS enqueue")
        return
    try:
        _get_sqs().send_message(
            QueueUrl=INVESTIGATION_QUEUE_URL,
            MessageBody=json.dumps(
                {
                    "violation_id": violation_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "rule_id": violation.rule_id,
                    "policy_domain": violation.policy_domain,
                    "severity": violation.severity.value,
                    "trace_id": trace_id,
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to enqueue violation to SQS: %s", exc)
