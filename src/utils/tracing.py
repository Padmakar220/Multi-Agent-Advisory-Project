"""
ADOT Distributed Tracing utilities (Requirement 18 / Task 27).

Provides:
  - TracingContext: W3C TraceContext propagation helpers
  - WorkflowTracer: creates child spans for all 11 required workflow stages
  - Stage constants matching the 11 required OTEL span stages

Environment variables (set by ADOT Lambda layer):
  AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument
  OTEL_PROPAGATORS=xray,tracecontext
  OTEL_PYTHON_ID_GENERATOR=xray

Usage::

    from src.utils.tracing import WorkflowTracer, Stage

    tracer = WorkflowTracer(service_name="portfolio-analyzer")
    with tracer.span(Stage.LLM_INVOCATION, user_id="u1", session_id="s1") as span:
        span.set_attribute("model_id", "claude-3-5-sonnet")
        response = bedrock_client.invoke_model(...)
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try to import OpenTelemetry; fall back to no-op stubs if not installed
# ---------------------------------------------------------------------------

try:
    from opentelemetry import trace
    from opentelemetry.propagate import extract, inject
    from opentelemetry.trace import NonRecordingSpan, Span, StatusCode
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OTEL_AVAILABLE = False
    trace = None  # type: ignore[assignment]
    StatusCode = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Stage constants — the 11 required child span stages (Req 18.2)
# ---------------------------------------------------------------------------


class Stage:
    USER_INPUT_RECEIPT = "user_input_receipt"
    COMPLIANCE_SCREENING = "compliance_screening"
    RAG_RETRIEVAL = "rag_retrieval"
    LLM_PROMPT_CONSTRUCTION = "llm_prompt_construction"
    LLM_INVOCATION = "llm_invocation"
    LLM_OUTPUT_EVALUATION = "llm_output_evaluation"
    AGENT_DECISION = "agent_decision"
    MCP_TOOL_INVOCATION = "mcp_tool_invocation"
    STEP_FUNCTIONS_TRANSITION = "step_functions_transition"
    TRADE_EXECUTION = "trade_execution"
    PORTFOLIO_UPDATE = "portfolio_update"

    ALL_STAGES = [
        USER_INPUT_RECEIPT,
        COMPLIANCE_SCREENING,
        RAG_RETRIEVAL,
        LLM_PROMPT_CONSTRUCTION,
        LLM_INVOCATION,
        LLM_OUTPUT_EVALUATION,
        AGENT_DECISION,
        MCP_TOOL_INVOCATION,
        STEP_FUNCTIONS_TRANSITION,
        TRADE_EXECUTION,
        PORTFOLIO_UPDATE,
    ]


# ---------------------------------------------------------------------------
# W3C TraceContext propagation helpers (Req 18.6)
# ---------------------------------------------------------------------------


class TracingContext:
    """Helpers for W3C TraceContext header propagation across Lambda invocations."""

    @staticmethod
    def inject_headers(carrier: dict[str, str]) -> dict[str, str]:
        """Inject W3C traceparent/tracestate headers into a carrier dict.

        Args:
            carrier: Dict to inject headers into (e.g. Lambda invocation payload).

        Returns:
            The carrier dict with traceparent/tracestate headers added.
        """
        if not _OTEL_AVAILABLE:
            return carrier
        try:
            inject(carrier)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to inject trace context: %s", exc)
        return carrier

    @staticmethod
    def extract_context(carrier: dict[str, str]) -> Any:
        """Extract W3C trace context from a carrier dict.

        Args:
            carrier: Dict containing traceparent/tracestate headers.

        Returns:
            OpenTelemetry Context object, or None if unavailable.
        """
        if not _OTEL_AVAILABLE:
            return None
        try:
            return extract(carrier)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to extract trace context: %s", exc)
            return None

    @staticmethod
    def get_trace_id() -> str:
        """Return the current trace ID as a hex string, or empty string."""
        if not _OTEL_AVAILABLE:
            return ""
        try:
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx and ctx.is_valid:
                return format(ctx.trace_id, "032x")
        except Exception:  # noqa: BLE001
            pass
        return ""

    @staticmethod
    def get_span_id() -> str:
        """Return the current span ID as a hex string, or empty string."""
        if not _OTEL_AVAILABLE:
            return ""
        try:
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx and ctx.is_valid:
                return format(ctx.span_id, "016x")
        except Exception:  # noqa: BLE001
            pass
        return ""


# ---------------------------------------------------------------------------
# WorkflowTracer — creates child spans for workflow stages
# ---------------------------------------------------------------------------


class WorkflowTracer:
    """Creates and manages OTEL child spans for agentic workflow stages.

    Args:
        service_name: Name of the Lambda function / service (used as tracer name).
    """

    def __init__(self, service_name: str = "multi-agent-advisory") -> None:
        self.service_name = service_name
        self._tracer = self._get_tracer()

    def _get_tracer(self) -> Any:
        if not _OTEL_AVAILABLE:
            return _NoOpTracer()
        try:
            return trace.get_tracer(self.service_name)
        except Exception:  # noqa: BLE001
            return _NoOpTracer()

    @contextmanager
    def span(
        self,
        stage_name: str,
        user_id: str = "",
        session_id: str = "",
        agent_type: str = "",
        extra_attributes: Optional[dict[str, Any]] = None,
        parent_context: Any = None,
    ) -> Generator[Any, None, None]:
        """Context manager that creates a child span for a workflow stage.

        Sets all required standard attributes (Req 18.3):
          trace_id, span_id, user_id, session_id, agent_type,
          stage_name, status, compliance_flags.

        Args:
            stage_name:       One of the Stage.* constants.
            user_id:          User identifier.
            session_id:       Session identifier.
            agent_type:       Agent type (e.g. "supervisor", "portfolio_analyzer").
            extra_attributes: Additional span attributes to set.
            parent_context:   Optional parent OTEL context for propagation.

        Yields:
            The created span (or a no-op span if OTEL is unavailable).
        """
        if not _OTEL_AVAILABLE:
            yield _NoOpSpan()
            return

        kwargs: dict[str, Any] = {}
        if parent_context is not None:
            kwargs["context"] = parent_context

        try:
            with self._tracer.start_as_current_span(stage_name, **kwargs) as span:
                # Set required standard attributes
                span.set_attribute("stage_name", stage_name)
                span.set_attribute("user_id", user_id)
                span.set_attribute("session_id", session_id)
                span.set_attribute("agent_type", agent_type)
                span.set_attribute("service_name", self.service_name)
                span.set_attribute("compliance_flags", "[]")

                # Populate trace_id and span_id after span is started
                ctx = span.get_span_context()
                if ctx and ctx.is_valid:
                    span.set_attribute("trace_id", format(ctx.trace_id, "032x"))
                    span.set_attribute("span_id", format(ctx.span_id, "016x"))

                if extra_attributes:
                    for key, value in extra_attributes.items():
                        span.set_attribute(key, value)

                try:
                    yield span
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(StatusCode.ERROR, str(exc))
                    raise
        except Exception as exc:  # noqa: BLE001
            logger.debug("WorkflowTracer.span() failed: %s", exc)
            yield _NoOpSpan()

    def annotate_violation(self, span: Any, violation_details: dict[str, Any]) -> None:
        """Annotate a span with compliance violation details and set status to ERROR.

        Args:
            span:              The OTEL span to annotate.
            violation_details: Dict with violation info (rule_id, severity, etc.).
        """
        if span is None:
            return
        try:
            import json as _json
            span.set_attribute("compliance_violation", _json.dumps(violation_details))
            if _OTEL_AVAILABLE and StatusCode is not None:
                span.set_status(StatusCode.ERROR, "compliance_violation")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to annotate violation on span: %s", exc)


# ---------------------------------------------------------------------------
# No-op stubs for when OpenTelemetry is not installed
# ---------------------------------------------------------------------------


class _NoOpSpan:
    """No-op span used when OpenTelemetry is unavailable."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        pass

    def record_exception(self, exc: Exception) -> None:
        pass

    def get_span_context(self) -> None:
        return None

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _NoOpTracer:
    """No-op tracer used when OpenTelemetry is unavailable."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> "_NoOpSpan":
        return _NoOpSpan()
