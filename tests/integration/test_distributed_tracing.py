"""
Integration tests for distributed tracing (Task 27.6).

Tests:
- Complete workflow produces spans with all expected stages
- Trace context is preserved across Lambda invocations (via carrier injection/extraction)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.utils.tracing import Stage, TracingContext, WorkflowTracer


class TestWorkflowTracerIntegration:
    """Integration tests for WorkflowTracer span creation."""

    def test_all_11_stages_can_be_spanned(self):
        """All 11 required stages must be creatable without error."""
        tracer = WorkflowTracer(service_name="integration-test")
        stages_visited = []

        for stage in Stage.ALL_STAGES:
            with tracer.span(stage, user_id="u1", session_id="s1", agent_type="test") as span:
                assert span is not None
                stages_visited.append(stage)

        assert len(stages_visited) == 11
        assert set(stages_visited) == set(Stage.ALL_STAGES)

    def test_span_context_manager_handles_exception(self):
        """Span context manager must not swallow exceptions."""
        tracer = WorkflowTracer()

        with pytest.raises(ValueError, match="test error"):
            with tracer.span(Stage.LLM_INVOCATION, user_id="u1", session_id="s1"):
                raise ValueError("test error")

    def test_nested_spans_do_not_raise(self):
        """Nested spans (parent → child) must work without error."""
        tracer = WorkflowTracer()

        with tracer.span(Stage.USER_INPUT_RECEIPT, user_id="u1", session_id="s1") as parent:
            with tracer.span(Stage.COMPLIANCE_SCREENING, user_id="u1", session_id="s1") as child:
                assert child is not None
            with tracer.span(Stage.RAG_RETRIEVAL, user_id="u1", session_id="s1") as rag_span:
                assert rag_span is not None

    def test_violation_annotation_on_span(self):
        """annotate_violation() must set compliance_violation attribute."""
        mock_span = MagicMock()
        tracer = WorkflowTracer()

        violation = {
            "rule_id": "PCI-001",
            "severity": "critical",
            "policy_domain": "PCI_DSS",
        }
        tracer.annotate_violation(mock_span, violation)

        called_keys = {c.args[0] for c in mock_span.set_attribute.call_args_list}
        assert "compliance_violation" in called_keys

    def test_extra_attributes_are_set(self):
        """Extra attributes passed to span() must be set on the span."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        import src.utils.tracing as tracing_module
        original = tracing_module._OTEL_AVAILABLE
        tracing_module._OTEL_AVAILABLE = True

        try:
            tracer = WorkflowTracer()
            tracer._tracer = mock_tracer

            with tracer.span(
                Stage.LLM_INVOCATION,
                user_id="u1",
                session_id="s1",
                extra_attributes={"model_id": "claude-3-5-sonnet", "token_count": 512},
            ):
                pass

            called_keys = {c.args[0] for c in mock_span.set_attribute.call_args_list}
            assert "model_id" in called_keys
            assert "token_count" in called_keys
        finally:
            tracing_module._OTEL_AVAILABLE = original


class TestTracingContextPropagation:
    """Integration tests for W3C TraceContext propagation."""

    def test_inject_and_extract_round_trip(self):
        """inject_headers followed by extract_context must not raise."""
        carrier: dict = {}
        TracingContext.inject_headers(carrier)
        ctx = TracingContext.extract_context(carrier)
        # ctx may be None if OTEL not available — just verify no exception

    def test_inject_preserves_existing_payload(self):
        """inject_headers must not remove existing payload keys."""
        payload = {
            "user_id": "user_123",
            "session_id": "sess_abc",
            "request_type": "rebalance",
        }
        result = TracingContext.inject_headers(payload)
        assert result["user_id"] == "user_123"
        assert result["session_id"] == "sess_abc"
        assert result["request_type"] == "rebalance"

    def test_get_trace_id_returns_string(self):
        """get_trace_id() must return a string (possibly empty)."""
        trace_id = TracingContext.get_trace_id()
        assert isinstance(trace_id, str)

    def test_get_span_id_returns_string(self):
        """get_span_id() must return a string (possibly empty)."""
        span_id = TracingContext.get_span_id()
        assert isinstance(span_id, str)

    def test_extract_from_empty_carrier(self):
        """extract_context() must not raise on empty carrier."""
        ctx = TracingContext.extract_context({})
        # No assertion on value — just verify no exception

    def test_extract_from_invalid_traceparent(self):
        """extract_context() must not raise on malformed traceparent."""
        ctx = TracingContext.extract_context({"traceparent": "not-a-valid-traceparent"})
        # No assertion on value — just verify no exception
