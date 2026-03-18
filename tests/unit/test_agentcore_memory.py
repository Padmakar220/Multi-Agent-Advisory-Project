"""Unit tests for AgentCore Memory migration in ManageAgentStateTool."""

import time
import pytest
from unittest.mock import MagicMock, patch, call

from src.mcp_tools.manage_agent_state_tool import ManageAgentStateTool
from src.utils.agentcore_memory import session_namespace, user_namespace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(memory_returns=None, memory_raises=None):
    """
    Build a ManageAgentStateTool with mocked AgentCore Memory and DynamoDB.

    memory_returns: value returned by memory.get()
    memory_raises:  exception raised by memory.get() / memory.put()
    """
    tool = ManageAgentStateTool.__new__(ManageAgentStateTool)

    mock_memory = MagicMock()
    if memory_raises:
        mock_memory.get.side_effect = memory_raises
        mock_memory.put.side_effect = memory_raises
    else:
        mock_memory.get.return_value = memory_returns

    tool.memory = mock_memory

    # DynamoDB fallback table
    mock_table = MagicMock()
    tool.table = mock_table

    return tool, mock_memory, mock_table


STATE = {"current_step": "analyzing", "subtasks_completed": [], "user_preferences": {}}


# ---------------------------------------------------------------------------
# load_state — AgentCore Memory happy path
# ---------------------------------------------------------------------------

class TestLoadStateFromMemory:
    def test_returns_state_from_memory(self):
        payload = {"session_id": "s1", "user_id": "u1", "agent_type": "supervisor", "state": STATE}
        tool, mock_memory, mock_table = _make_tool(memory_returns=payload)

        result = tool.load_state("s1")

        assert result == STATE
        mock_memory.get.assert_called_once_with(session_namespace("s1"), "state")
        mock_table.get_item.assert_not_called()  # DynamoDB not touched

    def test_memory_miss_falls_back_to_dynamodb(self):
        """When AgentCore Memory returns None, DynamoDB is queried."""
        tool, mock_memory, mock_table = _make_tool(memory_returns=None)

        # DynamoDB returns a valid item
        from src.models.portfolio import AgentState
        from datetime import datetime

        agent_state = AgentState(
            session_id="s1",
            user_id="u1",
            agent_type="supervisor",
            state=STATE,
            last_updated=datetime.utcnow().isoformat(),
        )
        item = agent_state.to_dynamodb()
        # Ensure TTL is in the future
        item["ttl"] = int(time.time()) + 3600
        mock_table.get_item.return_value = {"Item": item}

        result = tool.load_state("s1")

        assert result == STATE
        mock_table.get_item.assert_called_once()

    def test_memory_error_falls_back_to_dynamodb(self):
        """When AgentCore Memory raises, DynamoDB is used as fallback."""
        tool, mock_memory, mock_table = _make_tool(memory_raises=RuntimeError("network"))

        from src.models.portfolio import AgentState
        from datetime import datetime

        agent_state = AgentState(
            session_id="s1",
            user_id="u1",
            agent_type="supervisor",
            state=STATE,
            last_updated=datetime.utcnow().isoformat(),
        )
        item = agent_state.to_dynamodb()
        item["ttl"] = int(time.time()) + 3600
        mock_table.get_item.return_value = {"Item": item}

        result = tool.load_state("s1")
        assert result == STATE

    def test_empty_session_id_raises(self):
        tool, _, _ = _make_tool()
        with pytest.raises(ValueError, match="session_id"):
            tool.load_state("")


# ---------------------------------------------------------------------------
# save_state — AgentCore Memory happy path
# ---------------------------------------------------------------------------

class TestSaveStateToMemory:
    def test_writes_to_memory_namespace(self):
        tool, mock_memory, mock_table = _make_tool()

        result = tool.save_state("s1", "u1", "supervisor", STATE)

        assert result is True
        mock_memory.put.assert_called_once()
        args = mock_memory.put.call_args
        assert args[0][0] == session_namespace("s1")
        assert args[0][1] == "state"
        payload = args[0][2]
        assert payload["state"] == STATE
        assert payload["user_id"] == "u1"
        mock_table.put_item.assert_not_called()  # DynamoDB not touched

    def test_memory_error_falls_back_to_dynamodb(self):
        tool, mock_memory, mock_table = _make_tool(memory_raises=RuntimeError("timeout"))

        result = tool.save_state("s1", "u1", "supervisor", STATE)

        assert result is True
        mock_table.put_item.assert_called_once()

    def test_end_of_session_writes_long_term_fields(self):
        tool, mock_memory, _ = _make_tool()
        state_with_lt = {**STATE, "risk_profile": "moderate", "trade_preferences": {"min_trade": 100}}

        tool.save_state("s1", "u1", "supervisor", state_with_lt, end_of_session=True)

        # Two put calls: session namespace + user namespace
        assert mock_memory.put.call_count == 2
        calls = mock_memory.put.call_args_list
        namespaces = [c[0][0] for c in calls]
        assert session_namespace("s1") in namespaces
        assert user_namespace("u1") in namespaces

    def test_end_of_session_no_long_term_fields_skips_user_write(self):
        tool, mock_memory, _ = _make_tool()

        tool.save_state("s1", "u1", "supervisor", STATE, end_of_session=True)

        # Only session namespace written (no long-term fields in STATE)
        assert mock_memory.put.call_count == 1

    def test_empty_user_id_raises(self):
        tool, _, _ = _make_tool()
        with pytest.raises(ValueError, match="user_id"):
            tool.save_state("s1", "", "supervisor", STATE)

    def test_none_state_raises(self):
        tool, _, _ = _make_tool()
        with pytest.raises(ValueError, match="state"):
            tool.save_state("s1", "u1", "supervisor", None)


# ---------------------------------------------------------------------------
# OTEL span attributes
# ---------------------------------------------------------------------------

class TestOTELSpanAttributes:
    def test_span_attributes_set_on_write(self):
        tool, mock_memory, _ = _make_tool()

        recorded = []

        class FakeSpan:
            def __init__(self):
                self.attrs = {}

            def set_attribute(self, k, v):
                self.attrs[k] = v
                recorded.append((k, v))

            def record_exception(self, exc):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        with patch.object(tool, "_otel_memory_span", return_value=FakeSpan()):
            tool.save_state("s1", "u1", "supervisor", STATE)

        attr_keys = [k for k, _ in recorded]
        assert "duration_ms" in attr_keys
        assert "status" in attr_keys

    def test_span_attributes_set_on_read(self):
        payload = {"session_id": "s1", "user_id": "u1", "agent_type": "supervisor", "state": STATE}
        tool, mock_memory, _ = _make_tool(memory_returns=payload)

        recorded = []

        class FakeSpan:
            def __init__(self):
                self.attrs = {}

            def set_attribute(self, k, v):
                self.attrs[k] = v
                recorded.append((k, v))

            def record_exception(self, exc):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        with patch.object(tool, "_otel_memory_span", return_value=FakeSpan()):
            tool.load_state("s1")

        attr_keys = [k for k, _ in recorded]
        assert "duration_ms" in attr_keys
        assert "status" in attr_keys
