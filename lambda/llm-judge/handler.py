"""
LLM Judge Lambda handler (Requirement 19 / Task 28.2).

Triggered by DynamoDB Streams on the ComplianceViolations table.
For each new record with investigation_status == "pending":
  1. Invokes Bedrock Claude 3.5 Sonnet with the violation record
  2. Parses a structured verdict: confirm_violation | false_positive | escalate
  3. Writes the verdict back to the ComplianceViolations table
  4. Emits a CloudWatch metric: llm_judge_verdict (dimension: verdict)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

COMPLIANCE_VIOLATIONS_TABLE = os.environ.get(
    "COMPLIANCE_VIOLATIONS_TABLE", "advisory-compliance-violations"
)
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"
)
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

VALID_VERDICTS = {"confirm_violation", "false_positive", "escalate"}

_JUDGE_PROMPT_TEMPLATE = """\
You are a compliance officer reviewing an AI system violation record.

Violation record:
{violation_json}

Based on the violation details, provide a structured verdict in JSON format:
{{
  "verdict": "<confirm_violation|false_positive|escalate>",
  "reasoning": "<brief explanation>",
  "confidence": <0.0-1.0>
}}

Rules:
- confirm_violation: The violation is genuine and should be actioned
- false_positive: The rule triggered incorrectly; no real violation
- escalate: Requires human review due to ambiguity or high severity

Respond ONLY with the JSON object, no other text.
"""


# ---------------------------------------------------------------------------
# AWS clients (lazy-initialised for testability)
# ---------------------------------------------------------------------------

_bedrock_client: Any = None
_dynamodb_resource: Any = None
_cloudwatch_client: Any = None


def _get_bedrock() -> Any:
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _bedrock_client


def _get_dynamodb() -> Any:
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb_resource


def _get_cloudwatch() -> Any:
    global _cloudwatch_client
    if _cloudwatch_client is None:
        _cloudwatch_client = boto3.client("cloudwatch", region_name=AWS_REGION)
    return _cloudwatch_client


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def invoke_llm_judge(violation_record: dict[str, Any]) -> dict[str, Any]:
    """Invoke Bedrock Claude 3.5 Sonnet to judge a compliance violation.

    Args:
        violation_record: The violation item from DynamoDB.

    Returns:
        Dict with keys: verdict, reasoning, confidence.

    Raises:
        ValueError: If the model returns an unparseable or invalid verdict.
    """
    prompt = _JUDGE_PROMPT_TEMPLATE.format(
        violation_json=json.dumps(violation_record, indent=2, default=str)
    )

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        "messages": [{"role": "user", "content": prompt}],
    }

    response = _get_bedrock().invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    raw = json.loads(response["body"].read())
    text = raw["content"][0]["text"].strip()

    parsed = json.loads(text)
    verdict = parsed.get("verdict", "")
    if verdict not in VALID_VERDICTS:
        raise ValueError(f"Invalid verdict from LLM Judge: {verdict!r}")

    return {
        "verdict": verdict,
        "reasoning": parsed.get("reasoning", ""),
        "confidence": float(parsed.get("confidence", 0.0)),
    }


def write_verdict(violation_id: str, timestamp: str, verdict_data: dict[str, Any]) -> None:
    """Write the LLM Judge verdict back to the ComplianceViolations table."""
    table = _get_dynamodb().Table(COMPLIANCE_VIOLATIONS_TABLE)
    table.update_item(
        Key={"violation_id": violation_id, "timestamp": timestamp},
        UpdateExpression=(
            "SET llm_judge_verdict = :v, "
            "llm_judge_reasoning = :r, "
            "llm_judge_confidence = :c, "
            "investigation_status = :s, "
            "llm_judge_timestamp = :t"
        ),
        ExpressionAttributeValues={
            ":v": verdict_data["verdict"],
            ":r": verdict_data["reasoning"],
            ":c": str(verdict_data["confidence"]),
            ":s": "reviewed",
            ":t": datetime.now(timezone.utc).isoformat(),
        },
    )


def emit_verdict_metric(verdict: str) -> None:
    """Emit a CloudWatch metric for the LLM Judge verdict."""
    _get_cloudwatch().put_metric_data(
        Namespace="MultiAgentAdvisory/Compliance",
        MetricData=[
            {
                "MetricName": "llm_judge_verdict",
                "Dimensions": [{"Name": "verdict", "Value": verdict}],
                "Value": 1,
                "Unit": "Count",
            }
        ],
    )


def process_record(record: dict[str, Any]) -> None:
    """Process a single DynamoDB Streams record."""
    if record.get("eventName") not in ("INSERT", "MODIFY"):
        return

    new_image = record.get("dynamodb", {}).get("NewImage", {})
    if not new_image:
        return

    # Only process records with investigation_status == "pending"
    status = new_image.get("investigation_status", {}).get("S", "")
    if status != "pending":
        return

    violation_id = new_image.get("violation_id", {}).get("S", "")
    timestamp = new_image.get("timestamp", {}).get("S", "")

    if not violation_id or not timestamp:
        logger.warning("Skipping record with missing violation_id or timestamp")
        return

    # Deserialise the DynamoDB image to a plain dict for the prompt
    violation_record = {
        k: list(v.values())[0] for k, v in new_image.items()
    }

    logger.info(
        "Processing violation for LLM Judge",
        extra={"violation_id": violation_id, "timestamp": timestamp},
    )

    try:
        verdict_data = invoke_llm_judge(violation_record)
    except Exception as exc:
        logger.error(
            "LLM Judge invocation failed",
            extra={"violation_id": violation_id, "error": str(exc)},
        )
        return

    try:
        write_verdict(violation_id, timestamp, verdict_data)
    except Exception as exc:
        logger.error(
            "Failed to write verdict to DynamoDB",
            extra={"violation_id": violation_id, "error": str(exc)},
        )
        return

    try:
        emit_verdict_metric(verdict_data["verdict"])
    except Exception as exc:
        logger.warning(
            "Failed to emit CloudWatch metric",
            extra={"verdict": verdict_data["verdict"], "error": str(exc)},
        )

    logger.info(
        "LLM Judge verdict recorded",
        extra={
            "violation_id": violation_id,
            "verdict": verdict_data["verdict"],
            "confidence": verdict_data["confidence"],
        },
    )


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """DynamoDB Streams triggered Lambda handler for LLM Judge."""
    records = event.get("Records", [])
    processed = 0
    errors = 0

    for record in records:
        try:
            process_record(record)
            processed += 1
        except Exception as exc:
            logger.error("Unhandled error processing record: %s", exc)
            errors += 1

    return {"processed": processed, "errors": errors}
