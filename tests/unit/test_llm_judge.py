"""
Unit tests for LLM Judge Lambda handler (Task 28.5).

Tests:
  - Verdict parsing for all three verdict types
  - DynamoDB write-back with mocked client
  - CloudWatch metric emission
  - Error handling when Bedrock is unavailable
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bedrock_response(verdict: str, reasoning: str = "test", confidence: float = 0.9) -> dict:
    payload = json.dumps({"verdict": verdict, "reasoning": reasoning, "confidence": confidence})
    return {
        "body": MagicMock(read=lambda: json.dumps({"content": [{"text": payload}]}).encode())
    }


def _make_stream_record(new_image: dict, event_name: str = "INSERT") -> dict:
    return {"eventName": event_name, "dynamodb": {"NewImage": new_image}}


def _dynamo_image(violation_id: str = "v1", timestamp: str = "2024-01-01T00:00:00",
                  status: str = "pending") -> dict:
    return {
        "violation_id": {"S": violation_id},
        "timestamp": {"S": timestamp},
        "investigation_status": {"S": status},
        "rule_id": {"S": "FINRA-001"},
        "severity": {"S": "high"},
        "policy_domain": {"S": "FINRA"},
        "user_id": {"S": "user-123"},
        "session_id": {"S": "sess-456"},
        "stage": {"S": "input_screening"},
        "raw_content_hash": {"S": "a" * 64},
        "llm_judge_verdict": {"NULL": True},
        "trace_id": {"S": "trace-789"},
    }


# ---------------------------------------------------------------------------
# Tests: invoke_llm_judge
# ---------------------------------------------------------------------------

class TestInvokeLLMJudge:
    def test_confirm_violation_verdict(self):
        from lambda.llm_judge import handler

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = _make_bedrock_response("confirm_violation")

        with patch.object(handler, "_get_bedrock", return_value=mock_bedrock):
            result = handler.invoke_llm_judge({"rule_id": "FINRA-001", "severity": "high"})

        assert result["verdict"] == "confirm_violation"
        assert isinstance(result["reasoning"], str)
        assert 0.0 <= result["confidence"] <= 1.0

    def test_false_positive_verdict(self):
        from lambda.llm_judge import handler

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = _make_bedrock_response("false_positive", confidence=0.7)

        with patch.object(handler, "_get_bedrock", return_value=mock_bedrock):
            result = handler.invoke_llm_judge({"rule_id": "NIST-002"})

        assert result["verdict"] == "false_positive"
        assert result["confidence"] == pytest.approx(0.7)

    def test_escalate_verdict(self):
        from lambda.llm_judge import handler

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = _make_bedrock_response("escalate", confidence=0.5)

        with patch.object(handler, "_get_bedrock", return_value=mock_bedrock):
            result = handler.invoke_llm_judge({"rule_id": "PCI-001", "severity": "critical"})

        assert result["verdict"] == "escalate"

    def test_invalid_verdict_raises_value_error(self):
        from lambda.llm_judge import handler

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = _make_bedrock_response("unknown_verdict")

        with patch.object(handler, "_get_bedrock", return_value=mock_bedrock):
            with pytest.raises(ValueError, match="Invalid verdict"):
                handler.invoke_llm_judge({"rule_id": "FINRA-001"})

    def test_bedrock_unavailable_raises_exception(self):
        from lambda.llm_judge import handler

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.side_effect = Exception("Bedrock unavailable")

        with patch.object(handler, "_get_bedrock", return_value=mock_bedrock):
            with pytest.raises(Exception, match="Bedrock unavailable"):
                handler.invoke_llm_judge({"rule_id": "FINRA-001"})

    def test_malformed_json_response_raises_exception(self):
        from lambda.llm_judge import handler

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = {
            "body": MagicMock(
                read=lambda: json.dumps({"content": [{"text": "not json at all"}]}).encode()
            )
        }

        with patch.object(handler, "_get_bedrock", return_value=mock_bedrock):
            with pytest.raises(Exception):
                handler.invoke_llm_judge({"rule_id": "FINRA-001"})


# ---------------------------------------------------------------------------
# Tests: write_verdict
# ---------------------------------------------------------------------------

class TestWriteVerdict:
    def test_write_verdict_calls_update_item(self):
        from lambda.llm_judge import handler

        mock_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        verdict_data = {"verdict": "confirm_violation", "reasoning": "Genuine", "confidence": 0.95}

        with patch.object(handler, "_get_dynamodb", return_value=mock_dynamodb):
            handler.write_verdict("v-001", "2024-01-01T00:00:00", verdict_data)

        mock_dynamodb.Table.assert_called_once_with(handler.COMPLIANCE_VIOLATIONS_TABLE)
        mock_table.update_item.assert_called_once()

        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs["Key"] == {"violation_id": "v-001", "timestamp": "2024-01-01T00:00:00"}
        attrs = call_kwargs["ExpressionAttributeValues"]
        assert attrs[":v"] == "confirm_violation"
        assert attrs[":r"] == "Genuine"
        assert attrs[":s"] == "reviewed"

    def test_write_verdict_sets_reviewed_status(self):
        from lambda.llm_judge import handler

        mock_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        with patch.object(handler, "_get_dynamodb", return_value=mock_dynamodb):
            handler.write_verdict(
                "v-002", "2024-01-02T00:00:00",
                {"verdict": "false_positive", "reasoning": "FP", "confidence": 0.8}
            )

        attrs = mock_table.update_item.call_args[1]["ExpressionAttributeValues"]
        assert attrs[":s"] == "reviewed"

    def test_write_verdict_dynamodb_error_propagates(self):
        from lambda.llm_judge import handler

        mock_table = MagicMock()
        mock_table.update_item.side_effect = Exception("DynamoDB error")
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        with patch.object(handler, "_get_dynamodb", return_value=mock_dynamodb):
            with pytest.raises(Exception, match="DynamoDB error"):
                handler.write_verdict(
                    "v-003", "2024-01-03T00:00:00",
                    {"verdict": "escalate", "reasoning": "Unclear", "confidence": 0.5}
                )


# ---------------------------------------------------------------------------
# Tests: emit_verdict_metric
# ---------------------------------------------------------------------------

class TestEmitVerdictMetric:
    def test_emit_confirm_violation_metric(self):
        from lambda.llm_judge import handler

        mock_cw = MagicMock()

        with patch.object(handler, "_get_cloudwatch", return_value=mock_cw):
            handler.emit_verdict_metric("confirm_violation")

        mock_cw.put_metric_data.assert_called_once()
        call_kwargs = mock_cw.put_metric_data.call_args[1]
        assert call_kwargs["Namespace"] == "MultiAgentAdvisory/Compliance"
        metric = call_kwargs["MetricData"][0]
        assert metric["MetricName"] == "llm_judge_verdict"
        assert metric["Dimensions"][0]["Name"] == "verdict"
        assert metric["Dimensions"][0]["Value"] == "confirm_violation"
        assert metric["Value"] == 1
        assert metric["Unit"] == "Count"

    def test_emit_false_positive_metric(self):
        from lambda.llm_judge import handler

        mock_cw = MagicMock()

        with patch.object(handler, "_get_cloudwatch", return_value=mock_cw):
            handler.emit_verdict_metric("false_positive")

        metric = mock_cw.put_metric_data.call_args[1]["MetricData"][0]
        assert metric["Dimensions"][0]["Value"] == "false_positive"

    def test_emit_escalate_metric(self):
        from lambda.llm_judge import handler

        mock_cw = MagicMock()

        with patch.object(handler, "_get_cloudwatch", return_value=mock_cw):
            handler.emit_verdict_metric("escalate")

        metric = mock_cw.put_metric_data.call_args[1]["MetricData"][0]
        assert metric["Dimensions"][0]["Value"] == "escalate"


# ---------------------------------------------------------------------------
# Tests: process_record
# ---------------------------------------------------------------------------

class TestProcessRecord:
    def _setup_mocks(self, verdict: str = "confirm_violation"):
        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = _make_bedrock_response(verdict)
        mock_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_cw = MagicMock()
        return mock_bedrock, mock_dynamodb, mock_table, mock_cw

    def test_pending_record_is_processed(self):
        from lambda.llm_judge import handler

        mock_bedrock, mock_dynamodb, mock_table, mock_cw = self._setup_mocks()
        record = _make_stream_record(_dynamo_image(status="pending"))

        with (
            patch.object(handler, "_get_bedrock", return_value=mock_bedrock),
            patch.object(handler, "_get_dynamodb", return_value=mock_dynamodb),
            patch.object(handler, "_get_cloudwatch", return_value=mock_cw),
        ):
            handler.process_record(record)

        mock_bedrock.invoke_model.assert_called_once()
        mock_table.update_item.assert_called_once()
        mock_cw.put_metric_data.assert_called_once()

    def test_non_pending_record_is_skipped(self):
        from lambda.llm_judge import handler

        mock_bedrock, mock_dynamodb, mock_table, mock_cw = self._setup_mocks()
        record = _make_stream_record(_dynamo_image(status="reviewed"))

        with patch.object(handler, "_get_bedrock", return_value=mock_bedrock):
            handler.process_record(record)

        mock_bedrock.invoke_model.assert_not_called()

    def test_remove_event_is_skipped(self):
        from lambda.llm_judge import handler

        mock_bedrock, mock_dynamodb, mock_table, mock_cw = self._setup_mocks()
        record = _make_stream_record(_dynamo_image(), event_name="REMOVE")

        with patch.object(handler, "_get_bedrock", return_value=mock_bedrock):
            handler.process_record(record)

        mock_bedrock.invoke_model.assert_not_called()

    def test_bedrock_failure_does_not_raise(self):
        from lambda.llm_judge import handler

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.side_effect = Exception("Bedrock down")
        record = _make_stream_record(_dynamo_image(status="pending"))

        with patch.object(handler, "_get_bedrock", return_value=mock_bedrock):
            # Should not raise — errors are caught and logged
            handler.process_record(record)

    def test_dynamodb_write_failure_does_not_raise(self):
        from lambda.llm_judge import handler

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = _make_bedrock_response("confirm_violation")
        mock_table = MagicMock()
        mock_table.update_item.side_effect = Exception("DynamoDB write failed")
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_cw = MagicMock()

        record = _make_stream_record(_dynamo_image(status="pending"))

        with (
            patch.object(handler, "_get_bedrock", return_value=mock_bedrock),
            patch.object(handler, "_get_dynamodb", return_value=mock_dynamodb),
            patch.object(handler, "_get_cloudwatch", return_value=mock_cw),
        ):
            handler.process_record(record)

        # CloudWatch metric should NOT be emitted if DynamoDB write failed
        mock_cw.put_metric_data.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: lambda_handler
# ---------------------------------------------------------------------------

class TestLambdaHandler:
    def test_processes_multiple_records(self):
        from lambda.llm_judge import handler

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = _make_bedrock_response("confirm_violation")
        mock_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_cw = MagicMock()

        event = {
            "Records": [
                _make_stream_record(_dynamo_image("v1", status="pending")),
                _make_stream_record(_dynamo_image("v2", status="pending")),
            ]
        }

        with (
            patch.object(handler, "_get_bedrock", return_value=mock_bedrock),
            patch.object(handler, "_get_dynamodb", return_value=mock_dynamodb),
            patch.object(handler, "_get_cloudwatch", return_value=mock_cw),
        ):
            result = handler.lambda_handler(event, None)

        assert result["processed"] == 2
        assert result["errors"] == 0

    def test_empty_event_returns_zero_counts(self):
        from lambda.llm_judge import handler

        result = handler.lambda_handler({"Records": []}, None)
        assert result["processed"] == 0
        assert result["errors"] == 0
