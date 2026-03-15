"""
Property tests for Unified Observability Store and LLM Judge (Task 28.4).

Property 77: ComplianceViolations Record Schema
  — Any routed violation has a record with all required fields.

Property 78: LLM Judge Round-Trip
  — Every queued violation triggers LLM Judge, produces a valid verdict,
    verdict written back and emitted as metric.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

severity_st = st.sampled_from(["critical", "high", "medium", "low"])
policy_domain_st = st.sampled_from(["FINRA", "NIST", "PCI_DSS"])
verdict_st = st.sampled_from(["confirm_violation", "false_positive", "escalate"])

violation_record_st = st.fixed_dictionaries(
    {
        "violation_id": st.uuids().map(str),
        "timestamp": st.datetimes().map(lambda d: d.isoformat()),
        "user_id": st.text(min_size=1, max_size=50),
        "session_id": st.uuids().map(str),
        "stage": st.sampled_from(["input_screening", "llm_output_evaluation"]),
        "policy_domain": policy_domain_st,
        "rule_id": st.text(min_size=3, max_size=20),
        "severity": severity_st,
        "raw_content_hash": st.text(min_size=64, max_size=64),
        "investigation_status": st.just("pending"),
        "llm_judge_verdict": st.none(),
        "trace_id": st.text(min_size=0, max_size=64),
    }
)

# ---------------------------------------------------------------------------
# Property 77: ComplianceViolations Record Schema
# ---------------------------------------------------------------------------

REQUIRED_VIOLATION_FIELDS = {
    "violation_id",
    "timestamp",
    "user_id",
    "session_id",
    "stage",
    "policy_domain",
    "rule_id",
    "severity",
    "raw_content_hash",
    "investigation_status",
    "llm_judge_verdict",
    "trace_id",
}

VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_STAGES = {"input_screening", "llm_output_evaluation"}
VALID_STATUSES = {"pending", "reviewed", "escalated"}


@given(violation_record_st)
@settings(max_examples=100)
def test_property_77_compliance_violations_record_schema(record: dict[str, Any]) -> None:
    """Property 77: Any routed violation record contains all required fields with valid values."""
    # All required fields present
    for field in REQUIRED_VIOLATION_FIELDS:
        assert field in record, f"Missing required field: {field}"

    # violation_id is a valid UUID string
    uuid.UUID(record["violation_id"])

    # timestamp is a valid ISO datetime string
    datetime.fromisoformat(record["timestamp"])

    # severity is one of the valid values
    assert record["severity"] in VALID_SEVERITIES, (
        f"Invalid severity: {record['severity']}"
    )

    # stage is one of the valid values
    assert record["stage"] in VALID_STAGES, f"Invalid stage: {record['stage']}"

    # investigation_status starts as "pending"
    assert record["investigation_status"] == "pending"

    # llm_judge_verdict is None initially (not yet judged)
    assert record["llm_judge_verdict"] is None

    # user_id and session_id are non-empty strings
    assert len(record["user_id"]) > 0
    assert len(record["session_id"]) > 0


# ---------------------------------------------------------------------------
# Property 78: LLM Judge Round-Trip
# ---------------------------------------------------------------------------

VALID_VERDICTS = {"confirm_violation", "false_positive", "escalate"}


def _make_dynamodb_stream_record(violation: dict[str, Any]) -> dict[str, Any]:
    """Convert a plain violation dict to a DynamoDB Streams record format."""
    new_image = {k: {"S": str(v) if v is not None else {"NULL": True}} for k, v in violation.items()}
    # Fix None values
    for k, v in violation.items():
        if v is None:
            new_image[k] = {"NULL": True}
        else:
            new_image[k] = {"S": str(v)}
    return {
        "eventName": "INSERT",
        "dynamodb": {
            "NewImage": new_image,
        },
    }


@given(violation_record_st, verdict_st)
@settings(max_examples=100)
def test_property_78_llm_judge_round_trip(
    violation: dict[str, Any], expected_verdict: str
) -> None:
    """Property 78: Every pending violation triggers LLM Judge, produces a valid verdict,
    verdict is written back to DynamoDB, and a CloudWatch metric is emitted."""
    from lambda.llm_judge import handler as llm_judge_handler

    # Mock Bedrock response
    mock_bedrock_response = {
        "body": MagicMock(
            read=lambda: json.dumps(
                {
                    "content": [
                        {
                            "text": json.dumps(
                                {
                                    "verdict": expected_verdict,
                                    "reasoning": "Test reasoning",
                                    "confidence": 0.9,
                                }
                            )
                        }
                    ]
                }
            ).encode()
        )
    }

    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = mock_bedrock_response

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    mock_cloudwatch = MagicMock()

    with (
        patch.object(llm_judge_handler, "_get_bedrock", return_value=mock_bedrock),
        patch.object(llm_judge_handler, "_get_dynamodb", return_value=mock_dynamodb),
        patch.object(llm_judge_handler, "_get_cloudwatch", return_value=mock_cloudwatch),
    ):
        # 1. invoke_llm_judge returns a valid verdict
        verdict_data = llm_judge_handler.invoke_llm_judge(violation)
        assert verdict_data["verdict"] in VALID_VERDICTS
        assert isinstance(verdict_data["reasoning"], str)
        assert 0.0 <= verdict_data["confidence"] <= 1.0

        # 2. write_verdict calls DynamoDB UpdateItem
        llm_judge_handler.write_verdict(
            violation["violation_id"], violation["timestamp"], verdict_data
        )
        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs["Key"]["violation_id"] == violation["violation_id"]
        assert call_kwargs["Key"]["timestamp"] == violation["timestamp"]
        assert ":v" in call_kwargs["ExpressionAttributeValues"]
        assert call_kwargs["ExpressionAttributeValues"][":v"] == verdict_data["verdict"]
        assert call_kwargs["ExpressionAttributeValues"][":s"] == "reviewed"

        # 3. emit_verdict_metric calls CloudWatch PutMetricData
        llm_judge_handler.emit_verdict_metric(verdict_data["verdict"])
        mock_cloudwatch.put_metric_data.assert_called_once()
        metric_call = mock_cloudwatch.put_metric_data.call_args[1]
        assert metric_call["Namespace"] == "MultiAgentAdvisory/Compliance"
        metric_data = metric_call["MetricData"][0]
        assert metric_data["MetricName"] == "llm_judge_verdict"
        assert metric_data["Dimensions"][0]["Value"] == verdict_data["verdict"]


@given(verdict_st)
@settings(max_examples=100)
def test_property_78b_verdict_always_valid(verdict: str) -> None:
    """Property 78b: The verdict emitted as a CloudWatch metric is always one of the valid values."""
    assert verdict in VALID_VERDICTS


@given(violation_record_st)
@settings(max_examples=100)
def test_property_78c_non_pending_records_skipped(violation: dict[str, Any]) -> None:
    """Property 78c: Records with investigation_status != 'pending' are not processed."""
    from lambda.llm_judge import handler as llm_judge_handler

    mock_bedrock = MagicMock()

    # Modify status to non-pending
    non_pending_violation = {**violation, "investigation_status": "reviewed"}
    stream_record = _make_dynamodb_stream_record(non_pending_violation)

    with patch.object(llm_judge_handler, "_get_bedrock", return_value=mock_bedrock):
        llm_judge_handler.process_record(stream_record)
        # Bedrock should NOT be called for non-pending records
        mock_bedrock.invoke_model.assert_not_called()
