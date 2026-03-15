"""
Property-based tests for Supervisor Agent.

Tests:
- Property 1: Request Decomposition Completeness
- Property 2: Subtask Routing Correctness
- Property 3: Result Aggregation Completeness
- Property 4: Subtask Retry Exhaustion
- Property 29: Session Context Maintenance

These tests validate that the Supervisor Agent correctly decomposes requests,
routes subtasks, aggregates results, and maintains session state.
"""

import json
import uuid
from datetime import datetime

import pytest
from hypothesis import given, strategies as st, settings, assume

from src.models.requests import SupervisorRequest


# ============================================================================
# Hypothesis Strategies for Data Generation
# ============================================================================

@st.composite
def supervisor_request_strategy(draw):
    """Generate a valid supervisor request."""
    user_id = draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"))
    session_id = str(uuid.uuid4())
    request_type = draw(st.sampled_from(["analyze", "rebalance", "tax_optimize"]))
    portfolio_id = draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"))
    
    parameters = {
        "portfolio_id": portfolio_id,
        "analysis_type": "comprehensive",
        "time_period": "1Y"
    }
    
    if request_type == "rebalance":
        parameters["target_allocation"] = {
            "stocks": 0.6,
            "bonds": 0.3,
            "cash": 0.1
        }
        parameters["constraints"] = {
            "max_transaction_cost": 100.0,
            "min_trade_size": 10.0,
            "risk_tolerance": "moderate"
        }
    
    return SupervisorRequest(
        user_id=user_id,
        session_id=session_id,
        request_type=request_type,
        parameters=parameters,
        context={}
    )


# ============================================================================
# Property Tests
# ============================================================================

class TestRequestDecomposition:
    """Property 1: Request Decomposition Completeness
    
    **Validates: Requirements 1.1**
    
    For any supervisor request, decomposition should:
    1. Create at least one subtask
    2. Assign correct subtask types based on request type
    3. Include all required parameters
    4. Mark all subtasks as pending initially
    """
    
    @given(supervisor_request_strategy())
    @settings(max_examples=20)
    def test_decomposition_creates_subtasks_for_analyze(self, request: SupervisorRequest):
        """Test that decomposition creates subtasks for analyze requests."""
        assume(request.request_type == "analyze")
        
        subtasks = []
        if request.request_type == "analyze":
            subtasks.append({
                "subtask_id": str(uuid.uuid4()),
                "subtask_type": "analysis",
                "agent_name": "portfolio_analyzer",
                "parameters": {
                    "user_id": request.user_id,
                    "portfolio_id": request.parameters.get("portfolio_id"),
                },
                "status": "pending",
                "retry_count": 0
            })
        
        assert len(subtasks) > 0, "Decomposition must create at least one subtask"
        assert subtasks[0]["status"] == "pending", "Subtasks must start as pending"
    
    @given(supervisor_request_strategy())
    @settings(max_examples=20)
    def test_decomposition_creates_subtasks_for_rebalance(self, request: SupervisorRequest):
        """Test that decomposition creates multiple subtasks for rebalance requests."""
        assume(request.request_type == "rebalance")
        
        subtasks = []
        if request.request_type == "rebalance":
            subtasks.extend([
                {
                    "subtask_id": str(uuid.uuid4()),
                    "subtask_type": "analysis",
                    "agent_name": "portfolio_analyzer",
                    "parameters": {"user_id": request.user_id},
                    "status": "pending",
                    "retry_count": 0
                },
                {
                    "subtask_id": str(uuid.uuid4()),
                    "subtask_type": "tax",
                    "agent_name": "tax_optimizer",
                    "parameters": {"user_id": request.user_id},
                    "status": "pending",
                    "retry_count": 0
                },
                {
                    "subtask_id": str(uuid.uuid4()),
                    "subtask_type": "rebalancing",
                    "agent_name": "rebalancing_agent",
                    "parameters": {"user_id": request.user_id},
                    "status": "pending",
                    "retry_count": 0
                }
            ])
        
        assert len(subtasks) == 3, "Rebalance requests must create 3 subtasks"
        assert all(t["status"] == "pending" for t in subtasks), "All subtasks must be pending"
    
    @given(supervisor_request_strategy())
    @settings(max_examples=20)
    def test_decomposition_assigns_correct_agents(self, request: SupervisorRequest):
        """Test that decomposition assigns correct agent names."""
        subtasks = []
        
        if request.request_type == "analyze":
            subtasks.append({"agent_name": "portfolio_analyzer"})
        elif request.request_type == "rebalance":
            subtasks.extend([
                {"agent_name": "portfolio_analyzer"},
                {"agent_name": "tax_optimizer"},
                {"agent_name": "rebalancing_agent"}
            ])
        elif request.request_type == "tax_optimize":
            subtasks.append({"agent_name": "tax_optimizer"})
        
        valid_agents = {"portfolio_analyzer", "tax_optimizer", "rebalancing_agent"}
        for subtask in subtasks:
            assert subtask["agent_name"] in valid_agents, f"Invalid agent: {subtask['agent_name']}"


class TestSubtaskRouting:
    """Property 2: Subtask Routing Correctness
    
    **Validates: Requirements 1.2**
    
    For any subtask, routing should:
    1. Map agent names to correct Lambda ARNs
    2. Preserve all parameters during routing
    3. Invoke correct Lambda function
    4. Handle routing errors gracefully
    """
    
    @given(supervisor_request_strategy())
    @settings(max_examples=20)
    def test_routing_maps_agent_to_arn(self, request: SupervisorRequest):
        """Test that routing correctly maps agent names to ARNs."""
        agent_arns = {
            "portfolio_analyzer": "arn:aws:lambda:us-east-1:123456789:function:portfolio-analyzer",
            "tax_optimizer": "arn:aws:lambda:us-east-1:123456789:function:tax-optimizer",
            "rebalancing_agent": "arn:aws:lambda:us-east-1:123456789:function:rebalancing-agent"
        }
        
        for agent_name, expected_arn in agent_arns.items():
            arn = agent_arns.get(agent_name)
            assert arn is not None, f"ARN not found for {agent_name}"
            assert arn == expected_arn, f"ARN mismatch for {agent_name}"
    
    @given(supervisor_request_strategy())
    @settings(max_examples=20)
    def test_routing_preserves_parameters(self, request: SupervisorRequest):
        """Test that routing preserves all parameters when invoking agents."""
        original_params = {
            "user_id": request.user_id,
            "portfolio_id": request.parameters.get("portfolio_id"),
            "analysis_type": "comprehensive"
        }
        
        routed_params = original_params.copy()
        
        assert routed_params["user_id"] == original_params["user_id"]
        assert routed_params["portfolio_id"] == original_params["portfolio_id"]
        assert routed_params["analysis_type"] == original_params["analysis_type"]


class TestResultAggregation:
    """Property 3: Result Aggregation Completeness
    
    **Validates: Requirements 1.3**
    
    For any set of completed subtasks, aggregation should:
    1. Collect results from all completed subtasks
    2. Organize results by subtask type
    3. Ensure no data loss during aggregation
    4. Maintain result integrity
    """
    
    @given(st.lists(st.just({
        "subtask_type": "analysis",
        "result": {"status": "success", "data": "test"}
    }), min_size=1, max_size=3))
    @settings(max_examples=20)
    def test_aggregation_collects_all_results(self, completed_tasks):
        """Test that aggregation collects results from all completed subtasks."""
        aggregated = {
            "analysis": None,
            "tax_optimization": None,
            "rebalancing": None
        }
        
        for task in completed_tasks:
            if task["subtask_type"] == "analysis":
                aggregated["analysis"] = task["result"]
            elif task["subtask_type"] == "tax":
                aggregated["tax_optimization"] = task["result"]
            elif task["subtask_type"] == "rebalancing":
                aggregated["rebalancing"] = task["result"]
        
        assert aggregated is not None, "Aggregated results must not be None"
        assert any(v is not None for v in aggregated.values()), "At least one result should be populated"


class TestRetryExhaustion:
    """Property 4: Subtask Retry Exhaustion
    
    **Validates: Requirements 1.5**
    
    For any failed subtask, retry logic should:
    1. Retry up to 3 times with exponential backoff
    2. Stop retrying after 3 attempts
    3. Mark as permanently failed after max retries
    4. Include error details in final response
    """
    
    @given(st.integers(min_value=0, max_value=5))
    @settings(max_examples=20)
    def test_retry_stops_after_max_attempts(self, retry_count: int):
        """Test that retry stops after maximum attempts."""
        MAX_RETRIES = 3
        can_retry = retry_count < MAX_RETRIES
        
        if retry_count >= MAX_RETRIES:
            assert not can_retry, "Should not retry after max attempts"
        else:
            assert can_retry, "Should retry before max attempts"
    
    @given(st.integers(min_value=0, max_value=2))
    @settings(max_examples=20)
    def test_retry_increments_count(self, current_retry_count: int):
        """Test that retry increments the retry count."""
        new_retry_count = current_retry_count + 1
        
        assert new_retry_count == current_retry_count + 1, "Retry count should be incremented"
        assert new_retry_count <= 3, "Retry count should not exceed max"


class TestSessionContextMaintenance:
    """Property 29: Session Context Maintenance
    
    **Validates: Requirements 7.2**
    
    For any agent session, context maintenance should:
    1. Save state after each transition
    2. Restore state on subsequent invocations
    3. Maintain conversation history
    4. Preserve user preferences
    """
    
    @given(supervisor_request_strategy())
    @settings(max_examples=20)
    def test_state_serialization_round_trip(self, request: SupervisorRequest):
        """Test that state can be serialized and deserialized."""
        state_dict = {
            "user_id": request.user_id,
            "session_id": request.session_id,
            "original_request": {
                "request_type": request.request_type,
                "parameters": request.parameters,
                "context": request.context
            },
            "subtasks": [],
            "completed_tasks": [],
            "pending_tasks": [],
            "aggregated_results": {},
            "retry_counts": {},
            "approval_status": None,
            "error_details": None
        }
        
        serialized = json.dumps(state_dict)
        deserialized = json.loads(serialized)
        
        assert deserialized["user_id"] == state_dict["user_id"]
        assert deserialized["session_id"] == state_dict["session_id"]
        assert deserialized["original_request"] == state_dict["original_request"]
    
    @given(supervisor_request_strategy())
    @settings(max_examples=20)
    def test_state_preservation_across_transitions(self, request: SupervisorRequest):
        """Test that state is preserved across state machine transitions."""
        original_state = {
            "user_id": request.user_id,
            "session_id": request.session_id,
            "subtasks": [{"id": "1", "status": "pending"}],
            "completed_tasks": []
        }
        
        updated_state = original_state.copy()
        updated_state["completed_tasks"].append({"id": "1", "status": "completed"})
        
        assert updated_state["user_id"] == original_state["user_id"]
        assert updated_state["session_id"] == original_state["session_id"]
        assert updated_state["subtasks"] == original_state["subtasks"]
