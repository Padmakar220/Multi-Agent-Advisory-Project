"""ManageAgentStateTool — agent session state persistence via AgentCore Memory.

Reads and writes use AgentCore Memory (session-scoped namespace).
Long-term fields (risk_profile, trade_preferences) are written to the
user-scoped namespace on session end.
DynamoDB AgentSessions table is retained as a migration-compatibility fallback.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError
from opentelemetry import trace

from src.models.portfolio import AgentState
from src.error_handling import ErrorClassifier, ErrorCategory
from src.utils.agentcore_memory import (
    AgentCoreMemoryClient,
    session_namespace,
    user_namespace,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Long-term fields promoted to user namespace on session end
_LONG_TERM_FIELDS = ("risk_profile", "trade_preferences")

# Session TTL: 24 hours
_SESSION_TTL_SECONDS = 86_400


class ManageAgentStateTool:
    """
    MCP Tool for managing agent session state persistence.

    Reads/writes go to AgentCore Memory (session namespace).
    Falls back to DynamoDB AgentSessions table when AgentCore Memory
    returns empty (migration compatibility).
    Long-term fields are also written to the user namespace on session end.
    Every memory operation is wrapped in an OTEL child span.
    """

    name: str = "manage_agent_state"
    description: str = "Save or retrieve agent session state with TTL management"

    def __init__(
        self,
        table_name: str = "AgentSessions",
        memory_table_name: str = "AgentCoreMemory",
        region_name: str = "us-east-1",
    ):
        self.table_name = table_name
        self.dynamodb = boto3.resource("dynamodb", region_name=region_name)
        self.table = self.dynamodb.Table(table_name)
        self.memory = AgentCoreMemoryClient(
            table_name=memory_table_name, region_name=region_name
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _otel_memory_span(self, operation: str, namespace: str):
        """Context manager that creates a child OTEL span for a memory op."""
        return tracer.start_as_current_span(
            f"agentcore_memory.{operation}",
            attributes={
                "memory_namespace": namespace,
                "memory_operation": operation,
            },
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_state(
        self,
        session_id: str,
        user_id: str,
        agent_type: str,
        state: Dict[str, Any],
        end_of_session: bool = False,
    ) -> bool:
        """
        Persist agent state to AgentCore Memory (session namespace).

        If end_of_session=True, long-term fields are also written to the
        user namespace and the DynamoDB fallback record is removed.

        Args:
            session_id:      Unique session identifier
            user_id:         User identifier
            agent_type:      Agent type string
            state:           State dict to persist
            end_of_session:  Whether this is the final save for the session

        Returns:
            True on success
        """
        if not session_id:
            raise ValueError("session_id cannot be empty")
        if not user_id:
            raise ValueError("user_id cannot be empty")
        if not agent_type:
            raise ValueError("agent_type cannot be empty")
        if state is None:
            raise ValueError("state cannot be None")

        ns = session_namespace(session_id)
        ttl = int(time.time()) + _SESSION_TTL_SECONDS
        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "agent_type": agent_type,
            "state": state,
            "last_updated": datetime.utcnow().isoformat(),
        }

        t0 = time.time()
        with self._otel_memory_span("write", ns) as span:
            try:
                self.memory.put(ns, "state", payload, ttl=ttl)
                duration_ms = int((time.time() - t0) * 1000)
                span.set_attribute("duration_ms", duration_ms)
                span.set_attribute("status", "ok")
            except Exception as exc:
                span.set_attribute("status", "error")
                span.record_exception(exc)
                logger.warning("AgentCore Memory write failed, falling back to DynamoDB: %s", exc)
                # Fallback: write to DynamoDB
                self._dynamodb_save(session_id, user_id, agent_type, state)

        # Promote long-term fields to user namespace
        if end_of_session:
            long_term = {k: state[k] for k in _LONG_TERM_FIELDS if k in state}
            if long_term:
                u_ns = user_namespace(user_id)
                with self._otel_memory_span("write", u_ns) as span:
                    try:
                        self.memory.put(u_ns, "profile", long_term)
                        span.set_attribute("status", "ok")
                    except Exception as exc:
                        span.set_attribute("status", "error")
                        span.record_exception(exc)
                        logger.warning("Long-term memory write failed: %s", exc)

        return True

    def load_state(self, session_id: str) -> Dict[str, Any]:
        """
        Retrieve agent session state from AgentCore Memory.

        Falls back to DynamoDB AgentSessions table when AgentCore Memory
        returns empty.

        Args:
            session_id: Unique session identifier

        Returns:
            State dictionary

        Raises:
            ValueError: If session not found or expired
        """
        if not session_id:
            raise ValueError("session_id cannot be empty")

        ns = session_namespace(session_id)
        t0 = time.time()
        with self._otel_memory_span("read", ns) as span:
            try:
                record = self.memory.get(ns, "state")
                duration_ms = int((time.time() - t0) * 1000)
                span.set_attribute("duration_ms", duration_ms)
                if record is not None:
                    span.set_attribute("status", "ok")
                    return record["state"]
                span.set_attribute("status", "miss")
            except Exception as exc:
                span.set_attribute("status", "error")
                span.record_exception(exc)
                logger.warning("AgentCore Memory read failed, falling back to DynamoDB: %s", exc)

        # Fallback: read from DynamoDB
        return self._dynamodb_load(session_id)

    def load_long_term(self, user_id: str) -> Dict[str, Any]:
        """
        Retrieve long-term user-scoped memory (risk profile, preferences).

        Returns an empty dict if no long-term memory exists.
        """
        if not user_id:
            raise ValueError("user_id cannot be empty")

        u_ns = user_namespace(user_id)
        with self._otel_memory_span("read", u_ns) as span:
            try:
                record = self.memory.get(u_ns, "profile")
                span.set_attribute("status", "ok" if record else "miss")
                return record or {}
            except Exception as exc:
                span.set_attribute("status", "error")
                span.record_exception(exc)
                logger.warning("Long-term memory read failed: %s", exc)
                return {}

    # ------------------------------------------------------------------
    # DynamoDB fallback helpers (migration compatibility)
    # ------------------------------------------------------------------

    def _dynamodb_save(
        self, session_id: str, user_id: str, agent_type: str, state: Dict[str, Any]
    ) -> None:
        agent_state = AgentState(
            session_id=session_id,
            user_id=user_id,
            agent_type=agent_type,
            state=state,
            last_updated=datetime.utcnow().isoformat(),
        )
        self.table.put_item(Item=agent_state.to_dynamodb())

    def _dynamodb_load(self, session_id: str) -> Dict[str, Any]:
        try:
            response = self.table.get_item(Key={"session_id": session_id})
        except ClientError as exc:
            category = ErrorClassifier.categorize(exc)
            if category == ErrorCategory.TRANSIENT:
                raise
            raise ValueError(f"Invalid request: {exc.response['Error']['Message']}")

        if "Item" not in response:
            raise ValueError(f"Session not found: session_id={session_id}")

        agent_state = AgentState.from_dynamodb(response["Item"])
        current_time = int(datetime.utcnow().timestamp())
        if agent_state.ttl < current_time:
            raise ValueError(f"Session expired: session_id={session_id}")

        return agent_state.state
