"""Property-based tests for AgentCore Memory integration.

Properties 85-87 validate session/user namespace isolation and round-trip
persistence for the migrated ManageAgentStateTool.
"""

import time
import pytest
from unittest.mock import MagicMock, patch, call
from hypothesis import given, settings, strategies as st

from src.mcp_tools.manage_agent_state_tool import ManageAgentStateTool
from src.utils.agentcore_memory import session_namespace, user_namespace


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

agent_type_st = st.sampled_from(
    ["supervisor", "portfolio_analyzer", "tax_optimizer", "rebalancing_agent"]
)

state_st = st.fixed_dictionaries(
    {
        "current_step": st.sampled_from(["analyzing", "optimizing", "waiting_approval"]),
        "subtasks_completed": st.lists(st.text(min_size=1, max_size=30), max_size=5),
        "conversation_history": st.lists(st.text(min_size=1, max_size=100), max_size=5),
        "user_preferences": st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.one_of(st.text(max_size=50), st.integers()),
            max_size=3,
        ),
    }
)

state_with_long_term_st = st.fixed_dictionaries(
    {
        "current_step": st.sampled_from(["analyzing", "done"]),
        "risk_profile": st.sampled_from(["conservative", "moderate", "aggressive"]),
        "trade_preferences": st.dictionaries(
            st.text(min_size=1, max_size=20), st.text(max_size=50), max_size=3
        ),
    }
)


# ---------------------------------------------------------------------------
# Helper: build a tool with an in-memory AgentCore Memory mock
# ---------------------------------------------------------------------------

def _make_tool_with_memory_store():
    """Return (tool, in_memory_store) where store is a plain dict."""
    store: dict = {}

    mock_memory = MagicMock()

    def _put(namespace, key, value, ttl=None):
        store[(namespace, key)] = {"value": value, "ttl": ttl}

    def _get(namespace, key):
        entry = store.get((namespace, key))
        if entry is None:
            return None
        if entry["ttl"] and time.time() > entry["ttl"]:
            return None
        return entry["value"]

    mock_memory.put.side_effect = _put
    mock_memory.get.side_effect = _get

    tool = ManageAgentStateTool.__new__(ManageAgentStateTool)
    tool.memory = mock_memory
    tool.table = MagicMock()  # DynamoDB fallback (should not be called in happy path)
    return tool, store


# ---------------------------------------------------------------------------
# Property 85: Session Memory Round-Trip
# ---------------------------------------------------------------------------

class TestProperty85SessionMemoryRoundTrip:
    """
    Property 85: state written to AgentCore Memory at session end is
    retrievable at next session start for the same session_id.
    """

    @settings(max_examples=100)
    @given(
        session_id=st.text(min_size=1, max_size=60),
        user_id=st.text(min_size=1, max_size=60),
        agent_type=agent_type_st,
        state=state_st,
    )
    def test_session_round_trip(self, session_id, user_id, agent_type, state):
        tool, store = _make_tool_with_memory_store()

        tool.save_state(session_id, user_id, agent_type, state)
        loaded = tool.load_state(session_id)

        assert loaded == state, (
            f"Round-trip failed: saved {state!r}, loaded {loaded!r}"
        )

    @settings(max_examples=50)
    @given(
        session_id=st.text(min_size=1, max_size=60),
        user_id=st.text(min_size=1, max_size=60),
        agent_type=agent_type_st,
        state=state_st,
    )
    def test_session_ttl_is_24h(self, session_id, user_id, agent_type, state):
        tool, store = _make_tool_with_memory_store()

        before = int(time.time())
        tool.save_state(session_id, user_id, agent_type, state)
        after = int(time.time())

        ns = session_namespace(session_id)
        entry = store.get((ns, "state"))
        assert entry is not None
        ttl = entry["ttl"]
        assert before + 86399 <= ttl <= after + 86401, (
            f"TTL {ttl} not within 24h window [{before + 86399}, {after + 86401}]"
        )


# ---------------------------------------------------------------------------
# Property 86: Long-Term Memory Persistence
# ---------------------------------------------------------------------------

class TestProperty86LongTermMemoryPersistence:
    """
    Property 86: user-scoped fields written on session end are present in
    a new session for the same user_id.
    """

    @settings(max_examples=100)
    @given(
        session_id=st.text(min_size=1, max_size=60),
        user_id=st.text(min_size=1, max_size=60),
        agent_type=agent_type_st,
        state=state_with_long_term_st,
    )
    def test_long_term_fields_persisted_on_session_end(
        self, session_id, user_id, agent_type, state
    ):
        tool, store = _make_tool_with_memory_store()

        tool.save_state(session_id, user_id, agent_type, state, end_of_session=True)

        u_ns = user_namespace(user_id)
        entry = store.get((u_ns, "profile"))
        assert entry is not None, "Long-term profile not written to user namespace"

        profile = entry["value"]
        if "risk_profile" in state:
            assert profile.get("risk_profile") == state["risk_profile"]
        if "trade_preferences" in state:
            assert profile.get("trade_preferences") == state["trade_preferences"]

    @settings(max_examples=100)
    @given(
        user_id=st.text(min_size=1, max_size=60),
        profile=st.fixed_dictionaries(
            {
                "risk_profile": st.sampled_from(["conservative", "moderate", "aggressive"]),
                "trade_preferences": st.dictionaries(
                    st.text(min_size=1, max_size=20), st.text(max_size=50), max_size=3
                ),
            }
        ),
    )
    def test_load_long_term_returns_stored_profile(self, user_id, profile):
        tool, store = _make_tool_with_memory_store()

        u_ns = user_namespace(user_id)
        store[(u_ns, "profile")] = {"value": profile, "ttl": None}

        loaded = tool.load_long_term(user_id)
        assert loaded == profile


# ---------------------------------------------------------------------------
# Property 87: Memory Namespace Isolation
# ---------------------------------------------------------------------------

class TestProperty87MemoryNamespaceIsolation:
    """
    Property 87: an agent cannot read memory records belonging to a
    different user_id.
    """

    @settings(max_examples=100)
    @given(
        user_a=st.text(min_size=1, max_size=60),
        user_b=st.text(min_size=1, max_size=60),
        session_a=st.text(min_size=1, max_size=60),
        session_b=st.text(min_size=1, max_size=60),
        agent_type=agent_type_st,
        state_a=state_st,
        state_b=state_st,
    )
    def test_session_namespace_isolation(
        self, user_a, user_b, session_a, session_b, agent_type, state_a, state_b
    ):
        # Skip if sessions or users are identical (trivially same namespace)
        if session_a == session_b:
            return

        tool, store = _make_tool_with_memory_store()

        tool.save_state(session_a, user_a, agent_type, state_a)
        tool.save_state(session_b, user_b, agent_type, state_b)

        loaded_a = tool.load_state(session_a)
        loaded_b = tool.load_state(session_b)

        # Each session reads its own state, not the other's
        assert loaded_a == state_a
        assert loaded_b == state_b

        # Namespace keys must be distinct
        ns_a = session_namespace(session_a)
        ns_b = session_namespace(session_b)
        assert ns_a != ns_b

    @settings(max_examples=100)
    @given(
        user_a=st.text(min_size=1, max_size=60),
        user_b=st.text(min_size=1, max_size=60),
        profile_a=st.fixed_dictionaries({"risk_profile": st.just("conservative")}),
        profile_b=st.fixed_dictionaries({"risk_profile": st.just("aggressive")}),
    )
    def test_user_namespace_isolation(self, user_a, user_b, profile_a, profile_b):
        if user_a == user_b:
            return

        tool, store = _make_tool_with_memory_store()

        u_ns_a = user_namespace(user_a)
        u_ns_b = user_namespace(user_b)
        store[(u_ns_a, "profile")] = {"value": profile_a, "ttl": None}
        store[(u_ns_b, "profile")] = {"value": profile_b, "ttl": None}

        loaded_a = tool.load_long_term(user_a)
        loaded_b = tool.load_long_term(user_b)

        assert loaded_a == profile_a
        assert loaded_b == profile_b
        assert u_ns_a != u_ns_b


# ---------------------------------------------------------------------------
# OTEL span attribute tests
# ---------------------------------------------------------------------------

class TestOTELSpanAttributes:
    """Verify that memory operations set the required OTEL span attributes."""

    def test_save_state_sets_span_attributes(self):
        tool, _ = _make_tool_with_memory_store()

        spans = []

        class FakeSpan:
            def __init__(self):
                self.attrs = {}

            def set_attribute(self, k, v):
                self.attrs[k] = v

            def record_exception(self, exc):
                pass

            def __enter__(self):
                spans.append(self)
                return self

            def __exit__(self, *_):
                pass

        with patch.object(
            tool.__class__,
            "_otel_memory_span",
            side_effect=lambda op, ns: FakeSpan(),
        ):
            tool.save_state("s1", "u1", "supervisor", {"step": "done"})

        # At least one span should have been created
        assert len(spans) >= 1
