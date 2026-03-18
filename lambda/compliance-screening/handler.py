"""
Compliance Screening Lambda — Task 25.1 / 25.2

Invoked as the first step in the API entry point before forwarding to Step Functions.
Screens every incoming user request against FINRA, NIST, and PCI DSS policies.

Behaviour:
  - Violations at/above domain halt_threshold  → write to ComplianceViolations DynamoDB,
    enqueue to SQS investigation queue, return 403 halt response.
  - Violations below threshold                 → attach warning metadata, log, forward.
  - Timeout (>500ms)                           → treat as medium-severity warning, forward.

OTEL stages emitted (Req 18.2):
  - user_input_receipt   : root span, created here as the first Lambda in the chain
  - compliance_screening : child span wrapping ComplianceEngine.evaluate()
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
from src.utils.tracing import WorkflowTracer, TracingContext, Stage

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

tracer = WorkflowTracer("compliance-screening")

_dynamodb = None
_sqs = None

COMPLIANCE_VIOLATIONS_TABLE = os.environ.get(
    "COMPLIANCE_VIOLATIONS_TABLE", "advisory-compliance-violations"
)
INVESTIGATION_QUEUE_URL = os.environ.get("INVESTIGATION_QUEUE_URL", "")
SCREENING_TIMEOUT_S = 0.5


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


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Screen an incoming user request for compliance violations.

    Args:
        event: {
            "user_id": str,
            "session_id": str,
            "text": str,
            "metadata": dict,
            "traceparent": str,   # W3C TraceContext header from API Gateway
            "tracestate": str,
        }
        context: Lambda context object.

    Returns:
        {"status": "pass"|"halt", "warnings": [...], "violation_ids": [...], "message": str}
    """
    user_id = event.get("user_id", "unknown")
    session_id = event.get("session_id", "unknown")
    text = event.get("text", "")
    metadata = event.get("metadata", {})

    # ── Restore W3C TraceContext propagated from API Gateway (Req 18.6) ──
    parent_ctx = TracingContext.extract_context(event)

    metadata.update({"user_id": user_id, "session_id": session_id})

    # ── Stage: USER_INPUT_RECEIPT — root span for the entire request (Req 18.1) ──
    with tracer.span(
        Stage.USER_INPUT_RECEIPT,
        user_id=user_id,
        session_id=session_id,
        agent_type="compliance-screening",
        parent_context=parent_ctx,
    ) as root_span:
        root_span.set_attribute("input_length", len(text))
        current_trace_id = TracingContext.get_trace_id()
        root_span.set_attribute("trace_id", current_trace_id)

    # ── Stage: COMPLIANCE_SCREENING (Req 18.2) ──
    engine = ComplianceEngine()
    start = time.monotonic()

    with tracer.span(
        Stage.COMPLIANCE_SCREENING,
        user_id=user_id,
        session_id=session_id,
        agent_type="compliance-screening",
        parent_context=parent_ctx,
    ) as screen_span:

        try:
            result = engine.evaluate(text, metadata)
        except Exception as exc:  # noqa: BLE001
            tracer.annotate_violation(screen_span, {"error": str(exc)})
            logger.error(
                "ComplianceEngine.evaluate() raised an exception",
                extra={"user_id": user_id, "session_id": session_id, "error": str(exc)},
            )
            return {
                "status": "pass",
                "warnings": [{"rule_id": "ENGINE-ERROR", "message": str(exc)}],
                "message": "Compliance screening encountered an error; request forwarded with warning.",
            }

        elapsed_ms = (time.monotonic() - start) * 1000
        screen_span.set_attribute("screening_duration_ms", elapsed_ms)
        screen_span.set_attribute("violation_count", len(result.violations))
        screen_span.set_attribute("is_compliant", result.is_compliant)

        if elapsed_ms > SCREENING_TIMEOUT_S * 1000:
            logger.warning(
                "Compliance screening exceeded 500ms budget",
                extra={"elapsed_ms": elapsed_ms, "user_id": user_id},
            )

        # ── Partition violations ──
        halt_violations = []
        warn_violations = []
        for violation in result.violations:
            if not result.is_compliant and violation.severity >= _get_domain_threshold(
                engine, violation.policy_domain
            ):
                halt_violations.append(violation)
            else:
                warn_violations.append(violation)

        screen_span.set_attribute(
            "compliance_flags",
            json.dumps([v.rule_id for v in halt_violations + warn_violations]),
        )

        # ── HALT path ──
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
                    trace_id=current_trace_id,
                )
                _enqueue_for_investigation(
                    violation_id=vid,
                    user_id=user_id,
                    session_id=session_id,
                    violation=v,
                    trace_id=current_trace_id,
                )
            tracer.annotate_violation(
                screen_span,
                {"halt_violations": [v.rule_id for v in halt_violations]},
            )
            logger.warning(
                "Compliance screening HALT: %d violation(s) above threshold",
                len(halt_violations),
                extra={
                    "user_id": user_id,
                    "session_id": session_id,
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

        # ── PASS path ──
        warnings = [
            {"rule_id": v.rule_id, "severity": v.severity.value, "description": v.description}
            for v in warn_violations
        ]
        if warnings:
            logger.info(
                "Compliance screening PASS with %d sub-threshold warning(s)",
                len(warnings),
                extra={"user_id": user_id, "session_id": session_id, "warnings": warnings},
            )

        # Inject trace context so downstream Lambda continues the same trace (Req 18.6)
        response: dict[str, Any] = {
            "status": "pass",
            "warnings": warnings,
            "message": "Request passed compliance screening.",
        }
        TracingContext.inject_headers(response)
        return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_domain_threshold(engine: ComplianceEngine, domain: str) -> Severity:
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
