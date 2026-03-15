"""Unit tests for Supervisor Agent.

Tests:
- Supervisor Agent initialization
- Request decomposition logic
- Subtask routing logic
- Result aggregation logic
- Retry logic with exponential backoff
- State persistence and restoration
- Error handling
"""

import json
import uuid
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda/supervisor-agent'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from handler import SupervisorAgent, SupervisorAgentState
from src.models.requests import SupervisorRequest
from src.models.responses import SupervisorResponse


class TestSupervisorAgentInitialization:
    """Test Supervisor Agent initialization."""
    
    def test_supervisor_agent_initializes(self):
        """Test that Supervisor Agent initializes correctly."""
        with patch('lambda.supervisor_agent.handler.dynamodb'):
            agent = SupervisorAgent()
            assert agent is not None
            assert agent.graph is not None
    
    def test_supervisor_agent_state_creation(self):
        """Test that SupervisorAgentState can be created."""
        state = SupervisorAgentState(
            user_id="user_123",
            session_id="session_456",
            original_request={"request_type": "analyze"}
        )
        
        assert state.user_id == "user_123"
        assert state.session_id == "session_456"
        assert state.original_request["request_type"] == "analyze"


class TestRequestDecomposition:
    """Test request decomposition logic."""
    
    def test_decompose_analyze_request(self):
        """Test decomposition of analyze request."""
        with patch('lambda.supervisor_agent.handler.dynamodb'):
            agent = SupervisorAgent()
            state = SupervisorAgentState(
                user_id="user_123",
                session_id="session_456",
                original_request={
                    "request_type": "analyze",
                    "parameters": {"portfolio_id": "port_789"}
                }
            )
            
            result = agent._decompose_task(state)
            
            assert len(result.subtasks) == 1
            assert result.subtasks[0]["subtask_type"] == "analysis"
            assert result.subtasks[0]["agent_name"] == "portfolio_analyzer"
    
    def test_decompose_rebalance_request(self):
        """Test decomposition of rebalance request."""
        with patch('lambda.supervisor_agent.handler.dynamodb'):
            agent = SupervisorAgent()
            state = SupervisorAgentState(
                user_id="user_123",
                session_id="session_456",
                original_request={
                    "request_type": "rebalance",
                    "parameters": {
                        "portfolio_id": "port_789",
                        "target_allocation": {"stocks": 0.6, "bonds": 0.4}
                    }
                }
            )
            
            result = agent._decompose_task(state)
            
            assert len(result.subtasks) == 3
            agent_names = {t["agent_name"] for t in result.subtasks}
            assert agent_names == {"portfolio_analyzer", "tax_optimizer", "rebalancing_agent"}
    
    def test_decompose_tax_optimize_request(self):
        """Test decomposition of tax optimization request."""
        with patch('lambda.supervisor_agent.handler.dynamodb'):
            agent = SupervisorAgent()
            state = SupervisorAgentState(
                user_id="user_123",
                session_id="session_456",
                original_request={
                    "request_type": "tax_optimize",
                    "parameters": {"portfolio_id": "port_789"}
                }
            )
            
            result = agent._decompose_task(state)
            
            assert len(result.subtasks) == 1
            assert result.subtasks[0]["subtask_type"] == "tax"
            assert result.subtasks[0]["agent_name"] == "tax_optimizer"


class TestSubtaskRouting:
    """Test subtask routing logic."""
    
    @patch('lambda.supervisor_agent.handler.lambda_client')
    def test_route_to_portfolio_analyzer(self, mock_lambda):
        """Test routing to portfolio analyzer."""
        with patch('lambda.supervisor_agent.handler.dynamodb'):
            agent = SupervisorAgent()
            
            mock_lambda.invoke.return_value = {
                "Payload": MagicMock(read=lambda: json.dumps({"status": "success"}))
            }
            
            state = SupervisorAgentState(
                user_id="user_123",
                session_id="session_456",
                original_request={"request_type": "analyze"},
                pending_tasks=[{
                    "subtask_id": "task_1",
                    "agent_name": "portfolio_analyzer",
                    "parameters": {"user_id": "user_123"},
                    "status": "pending"
                }]
            )
            
            result = agent._route_to_agents(state)
            
            assert result.pending_tasks[0]["status"] == "completed"
            mock_lambda.invoke.assert_called_once()


class TestResultAggregation:
    """Test result aggregation logic."""
    
    def test_aggregate_analysis_results(self):
        """Test aggregation of analysis results."""
        with patch('lambda.supervisor_agent.handler.dynamodb'):
            agent = SupervisorAgent()
            state = SupervisorAgentState(
                user_id="user_123",
                session_id="session_456",
                original_request={"request_type": "analyze"},
                completed_tasks=[{
                    "subtask_id": "task_1",
                    "subtask_type": "analysis",
                    "agent_name": "portfolio_analyzer",
                    "result": {"performance": "good"}
                }]
            )
            
            result = agent._aggregate_results(state)
            
            assert result.aggregated_results["analysis"] is not None
            assert result.aggregated_results["analysis"]["performance"] == "good"


class TestRetryLogic:
    """Test retry logic with exponential backoff."""
    
    def test_retry_increments_count(self):
        """Test that retry increments the retry count."""
        with patch('lambda.supervisor_agent.handler.dynamodb'):
            agent = SupervisorAgent()
            state = SupervisorAgentState(
                user_id="user_123",
                session_id="session_456",
                original_request={"request_type": "analyze"},
                pending_tasks=[{
                    "subtask_id": "task_1",
                    "status": "failed",
                    "retry_count": 0
                }]
            )
            
            result = agent._retry_task(state)
            
            assert result.pending_tasks[0]["retry_count"] == 1
            assert result.pending_tasks[0]["status"] == "pending"
    
    def test_retry_stops_after_max_attempts(self):
        """Test that retry stops after maximum attempts."""
        with patch('lambda.supervisor_agent.handler.dynamodb'):
            agent = SupervisorAgent()
            state = SupervisorAgentState(
                user_id="user_123",
                session_id="session_456",
                original_request={"request_type": "analyze"},
                pending_tasks=[{
                    "subtask_id": "task_1",
                    "status": "failed",
                    "retry_count": 3
                }]
            )
            
            result = agent._retry_task(state)
            
            # After max retries, status should remain failed
            assert result.pending_tasks[0]["status"] == "failed"


class TestStatePersistence:
    """Test state persistence and restoration."""
    
    def test_state_serialization(self):
        """Test that state can be serialized."""
        state = SupervisorAgentState(
            user_id="user_123",
            session_id="session_456",
            original_request={"request_type": "analyze"}
        )
        
        state_dict = state.to_dict()
        
        assert state_dict["user_id"] == "user_123"
        assert state_dict["session_id"] == "session_456"
    
    def test_state_deserialization(self):
        """Test that state can be deserialized."""
        state_dict = {
            "user_id": "user_123",
            "session_id": "session_456",
            "original_request": {"request_type": "analyze"},
            "subtasks": [],
            "completed_tasks": [],
            "pending_tasks": [],
            "aggregated_results": {},
            "retry_counts": {},
            "approval_status": None,
            "error_details": None
        }
        
        state = SupervisorAgentState.from_dict(state_dict)
        
        assert state.user_id == "user_123"
        assert state.session_id == "session_456"


class TestErrorHandling:
    """Test error handling."""
    
    def test_error_notification_on_permanent_failure(self):
        """Test error notification on permanent failure."""
        with patch('lambda.supervisor_agent.handler.dynamodb'):
            agent = SupervisorAgent()
            state = SupervisorAgentState(
                user_id="user_123",
                session_id="session_456",
                original_request={"request_type": "analyze"},
                pending_tasks=[{
                    "subtask_id": "task_1",
                    "agent_name": "portfolio_analyzer",
                    "status": "failed",
                    "error": "Connection timeout"
                }]
            )
            
            result = agent._error_notification(state)
            
            assert result.error_details is not None
            assert result.error_details["error_code"] == "AGENT_ERROR"
            assert len(result.error_details["failed_tasks"]) == 1
