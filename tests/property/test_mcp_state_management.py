"""Property-based tests for agent state management MCP tools.

Feature: multi-agent-advisory-ai-system
"""

import pytest
import time
from hypothesis import given, strategies as st, settings
from unittest.mock import Mock, MagicMock
from datetime import datetime

from src.mcp_tools import ManageAgentStateTool
from src.models.portfolio import AgentState


# Strategy for generating agent state
@st.composite
def agent_state_strategy(draw):
    """Generate valid agent state dictionaries."""
    state = {
        'current_step': draw(st.sampled_from(['analyzing', 'optimizing', 'rebalancing', 'waiting_approval'])),
        'subtasks_completed': draw(st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5)),
        'pending_subtasks': draw(st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5)),
        'conversation_history': draw(st.lists(st.text(min_size=1, max_size=200), min_size=0, max_size=10)),
        'user_preferences': draw(st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(st.text(), st.integers(), st.floats(allow_nan=False, allow_infinity=False)),
            min_size=0,
            max_size=5
        ))
    }
    return state


class TestManageAgentStateToolProperties:
    """Property-based tests for ManageAgentStateTool."""
    
    @settings(max_examples=100)
    @given(
        session_id=st.text(min_size=1, max_size=100),
        user_id=st.text(min_size=1, max_size=100),
        agent_type=st.sampled_from(['supervisor', 'portfolio_analyzer', 'tax_optimizer', 'rebalancing_agent']),
        state=agent_state_strategy()
    )
    def test_property_28_agent_state_round_trip_persistence(self, session_id, user_id, agent_type, state):
        """
        Property 28: Agent State Round-Trip Persistence
        
        For any agent session, saving the agent state and then retrieving it
        should produce an equivalent state with all session context preserved
        (user preferences, conversation history).
        
        **Validates: Requirements 7.1, 7.3, 7.5**
        """
        # Mock DynamoDB table
        mock_table = Mock()
        stored_item = {}
        
        def mock_put_item(Item):
            stored_item.update(Item)
        
        def mock_get_item(Key):
            if stored_item and stored_item.get('session_id') == Key['session_id']:
                return {'Item': stored_item}
            return {}
        
        mock_table.put_item = mock_put_item
        mock_table.get_item = mock_get_item
        
        # Create tool with mocked table
        tool = ManageAgentStateTool()
        tool.table = mock_table
        
        # Save state
        save_result = tool.save_state(session_id, user_id, agent_type, state)
        assert save_result is True
        
        # Load state
        loaded_state = tool.load_state(session_id)
        
        # Verify state is preserved
        assert loaded_state == state
        
        # Verify all context is preserved
        assert loaded_state['current_step'] == state['current_step']
        assert loaded_state['subtasks_completed'] == state['subtasks_completed']
        assert loaded_state['pending_subtasks'] == state['pending_subtasks']
        assert loaded_state['conversation_history'] == state['conversation_history']
        assert loaded_state['user_preferences'] == state['user_preferences']

    
    @settings(max_examples=100)
    @given(
        session_id=st.text(min_size=1, max_size=100),
        user_id=st.text(min_size=1, max_size=100),
        agent_type=st.sampled_from(['supervisor', 'portfolio_analyzer', 'tax_optimizer']),
        state=agent_state_strategy()
    )
    def test_property_ttl_calculation(self, session_id, user_id, agent_type, state):
        """
        Property: TTL should be set to 24 hours from save time.
        
        For any agent state save operation, the TTL should be calculated
        as 24 hours (86400 seconds) from the current time.
        
        **Validates: Requirements 7.5**
        """
        # Mock DynamoDB table
        mock_table = Mock()
        stored_item = {}
        
        def mock_put_item(Item):
            stored_item.update(Item)
        
        mock_table.put_item = mock_put_item
        
        # Create tool with mocked table
        tool = ManageAgentStateTool()
        tool.table = mock_table
        
        # Record current time
        current_time = int(datetime.utcnow().timestamp())
        
        # Save state
        tool.save_state(session_id, user_id, agent_type, state)
        
        # Verify TTL is set correctly (24 hours = 86400 seconds)
        ttl = stored_item['ttl']
        expected_ttl_min = current_time + 86399  # Allow 1 second tolerance
        expected_ttl_max = current_time + 86401
        
        assert expected_ttl_min <= ttl <= expected_ttl_max, \
            f"TTL should be 86400 seconds from now, got {ttl - current_time} seconds"
    
    @settings(max_examples=100)
    @given(
        session_id=st.text(min_size=1, max_size=100),
        user_id=st.text(min_size=1, max_size=100),
        agent_type=st.sampled_from(['supervisor', 'portfolio_analyzer']),
        state1=agent_state_strategy(),
        state2=agent_state_strategy()
    )
    def test_property_state_update_overwrites(self, session_id, user_id, agent_type, state1, state2):
        """
        Property: Saving state multiple times should overwrite previous state.
        
        For any session, saving a new state should replace the old state
        completely.
        """
        # Mock DynamoDB table
        mock_table = Mock()
        stored_item = {}
        
        def mock_put_item(Item):
            stored_item.clear()
            stored_item.update(Item)
        
        def mock_get_item(Key):
            if stored_item and stored_item.get('session_id') == Key['session_id']:
                return {'Item': stored_item}
            return {}
        
        mock_table.put_item = mock_put_item
        mock_table.get_item = mock_get_item
        
        # Create tool with mocked table
        tool = ManageAgentStateTool()
        tool.table = mock_table
        
        # Save first state
        tool.save_state(session_id, user_id, agent_type, state1)
        loaded_state1 = tool.load_state(session_id)
        assert loaded_state1 == state1
        
        # Save second state (should overwrite)
        tool.save_state(session_id, user_id, agent_type, state2)
        loaded_state2 = tool.load_state(session_id)
        assert loaded_state2 == state2
        
        # If states are different, verify they're not equal
        if state1 != state2:
            assert loaded_state2 != state1
    
    @settings(max_examples=50)
    @given(session_id=st.text(min_size=1, max_size=100))
    def test_property_expired_session_error(self, session_id):
        """
        Property: Loading expired session should raise ValueError.
        
        For any session that has expired (TTL in the past), loading the
        state should raise a ValueError.
        """
        # Mock DynamoDB table with expired session
        mock_table = Mock()
        
        expired_item = {
            'session_id': session_id,
            'user_id': 'user_123',
            'agent_type': 'supervisor',
            'state': {'test': 'data'},
            'created_at': '2024-01-01T00:00:00',
            'last_updated': '2024-01-01T00:00:00',
            'ttl': int(datetime(2024, 1, 1).timestamp())  # Expired TTL
        }
        
        mock_table.get_item.return_value = {'Item': expired_item}
        
        # Create tool with mocked table
        tool = ManageAgentStateTool()
        tool.table = mock_table
        
        # Should raise ValueError for expired session
        with pytest.raises(ValueError) as exc_info:
            tool.load_state(session_id)
        
        assert "expired" in str(exc_info.value).lower()


class TestStateManagementValidation:
    """Test input validation for state management."""
    
    def test_save_state_empty_session_id(self):
        """save_state should reject empty session_id."""
        tool = ManageAgentStateTool()
        
        with pytest.raises(ValueError) as exc_info:
            tool.save_state("", "user_123", "supervisor", {})
        
        assert "session_id" in str(exc_info.value).lower()
        assert "empty" in str(exc_info.value).lower()
    
    def test_save_state_empty_user_id(self):
        """save_state should reject empty user_id."""
        tool = ManageAgentStateTool()
        
        with pytest.raises(ValueError) as exc_info:
            tool.save_state("session_123", "", "supervisor", {})
        
        assert "user_id" in str(exc_info.value).lower()
        assert "empty" in str(exc_info.value).lower()
    
    def test_save_state_none_state(self):
        """save_state should reject None state."""
        tool = ManageAgentStateTool()
        
        with pytest.raises(ValueError) as exc_info:
            tool.save_state("session_123", "user_123", "supervisor", None)
        
        assert "state" in str(exc_info.value).lower()
    
    def test_load_state_empty_session_id(self):
        """load_state should reject empty session_id."""
        tool = ManageAgentStateTool()
        
        with pytest.raises(ValueError) as exc_info:
            tool.load_state("")
        
        assert "session_id" in str(exc_info.value).lower()
        assert "empty" in str(exc_info.value).lower()
    
    def test_load_state_not_found(self):
        """load_state should raise ValueError for non-existent session."""
        # Mock DynamoDB table returning no item
        mock_table = Mock()
        mock_table.get_item.return_value = {}
        
        tool = ManageAgentStateTool()
        tool.table = mock_table
        
        with pytest.raises(ValueError) as exc_info:
            tool.load_state("nonexistent_session")
        
        assert "not found" in str(exc_info.value).lower()
