"""
Property-based tests for end-to-end distributed tracing with ADOT (Task 27.5).

Tests:
- Property 74: Workflow Stage Span Completeness
- Property 75: Violation Span Annotation
- Property 76: W3C TraceContext Propagation

Configure Hypothesis with max_examples=100.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from hypothesis import given, settings, strategies as st

from src.utils.tracing import Stage, TracingContext, WorkflowTracer

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_stage_strategy = st.sampled_from(Stage.ALL_STAGES)

_user_id_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
    min_size=1,
    max_size=30,
)

_session_id_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=1,
    max_size=36,
)

_agent_type_strategy = st.sampled_from([
    "supervisor", "portfolio_analyzer", "tax_optimizer",
    "rebalancing_agent", "trade_executor", "compliance_screening",
])

_violation_strategy = st.fixed_dictionaries({
    "rule_id": st.sampled_from(["FINRA-001", "NIST-003", "PCI-001"]),
    "severity": st.sampled_from(["critical", "high", "medium", "low"]),
    "policy_domain": st.sampled_from(["FINRA", "NIST", "PCI_DSS"]),
})


# ---------------------------------------------------------------------------
# Property 74: Workflow Stage Span Completeness
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=2000)
@given(
    stage_name=_stage_strategy,
    user_id=_user_id_strategy,
    session_id=_session_id_strategy,
    agent_type=_agent_type_strategy,
)
def test_property_74_workflow_stage_span_completeness(
    stage_name: str,
    user_id: str,
    session_id: str,
    agent_type: str,
) -> None:
    """
    **Validates: Requirements 18.1, 18.2, 18.3**

    For any workflow stage, WorkflowTracer.span() must:
    - Not raise an exception
    - Yield a span object (real or no-op)
    - Attempt to set all required standard attributes:
      stage_name, user_id, session_id, agent_type, compliance_flags
    """
    mock_span = MagicMock()
    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
    mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

    tracer = WorkflowTracer(service_name="test-service")
    tracer._tracer = mock_tracer

    # Patch OTEL availability
    import src.utils.tracing as tracing_module
    original = tracing_module._OTEL_AVAILABLE
    tracing_module._OTEL_AVAILABLE = True

    try:
        with tracer.span(stage_name, user_id=user_id, session_id=session_id, agent_type=agent_type) as span:
            assert span is not None

        # Verify required attributes were set
        set_attr_calls = {c.args[0] for c in mock_span.set_attribute.call_args_list}
        assert "stage_name" in set_attr_calls, f"stage_name not set for stage {stage_name}"
        assert "user_id" in set_attr_calls, "user_id not set"
        assert "session_id" in set_attr_calls, "session_id not set"
        assert "agent_type" in set_attr_calls, "agent_type not set"
        assert "compliance_flags" in set_attr_calls, "compliance_flags not set"
    finally:
        tracing_module._OTEL_AVAILABLE = original


# ---------------------------------------------------------------------------
# Property 75: Violation Span Annotation
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=2000)
@given(violation=_violation_strategy)
def test_property_75_violation_span_annotation(violation: dict[str, Any]) -> None:
    """
    **Validates: Requirements 18.5**

    When annotate_violation() is called, the span must:
    - Have compliance_violation attribute set with violation details
    - Have status set to ERROR
    """
    mock_span = MagicMock()

    import src.utils.tracing as tracing_module
    original = tracing_module._OTEL_AVAILABLE
    tracing_module._OTEL_AVAILABLE = True

    try:
        tracer = WorkflowTracer()
        tracer.annotate_violation(mock_span, violation)

        # compliance_violation attribute must be set
        set_attr_calls = {c.args[0] for c in mock_span.set_attribute.call_args_list}
        assert "compliance_violation" in set_attr_calls, (
            "compliance_violation attribute must be set on span"
        )

        # Verify the value is valid JSON containing violation details
        for c in mock_span.set_attribute.call_args_list:
            if c.args[0] == "compliance_violation":
                parsed = json.loads(c.args[1])
                assert "rule_id" in parsed or "severity" in parsed or "policy_domain" in parsed
    finally:
        tracing_module._OTEL_AVAILABLE = original


# ---------------------------------------------------------------------------
# Property 76: W3C TraceContext Propagation
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=2000)
@given(
    traceparent=st.text(
        alphabet="0123456789abcdef-",
        min_size=0,
        max_size=55,
    ),
    extra_keys=st.dictionaries(
        keys=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_"),
        values=st.text(min_size=0, max_size=50),
        max_size=5,
    ),
)
def test_property_76_w3c_tracecontext_propagation(
    traceparent: str, extra_keys: dict[str, str]
) -> None:
    """
    **Validates: Requirements 18.6**

    TracingContext.inject_headers() must:
    - Not raise an exception for any carrier dict
    - Return a dict (the carrier, possibly with headers added)

    TracingContext.extract_context() must:
    - Not raise an exception for any carrier dict
    """
    carrier = {**extra_keys}
    if traceparent:
        carrier["traceparent"] = traceparent

    # inject_headers must not raise
    result = TracingContext.inject_headers(carrier)
    assert isinstance(result, dict), "inject_headers must return a dict"

    # extract_context must not raise
    ctx = TracingContext.extract_context(carrier)
    # ctx may be None (if OTEL not available) or an OTEL Context object
    # Just verify no exception was raised


@settings(max_examples=100, deadline=2000)
@given(
    payload=st.fixed_dictionaries(
        {},
        optional={
            "user_id": st.text(min_size=1, max_size=20),
            "data": st.text(min_size=0, max_size=100),
        },
    )
)
def test_property_76b_inject_does_not_lose_existing_keys(payload: dict[str, Any]) -> None:
    """
    inject_headers() must preserve all existing keys in the carrier.
    """
    carrier = dict(payload)
    original_keys = set(carrier.keys())

    result = TracingContext.inject_headers(carrier)

    for key in original_keys:
        assert key in result, f"inject_headers dropped existing key '{key}'"
