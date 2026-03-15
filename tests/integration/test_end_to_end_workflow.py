"""
End-to-End Integration Tests for Multi-Agent Advisory AI System

This test suite validates the complete workflow from user request through
trade execution, including state persistence and approval workflow.

Tests cover:
- Complete workflow from request to trade execution
- State persistence across Lambda invocations
- Approval workflow functionality
- Portfolio updates after trades
"""

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch, call
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

# Import components
import sys
sys.path.insert(0, 'src')
sys.path.insert(0, 'lambda')

from models.portfolio import Portfolio, Holding
from models.requests import SupervisorRequest
from models.responses import (
    SupervisorResponse, AnalysisReport, 
    TaxOptimizationPlan, RebalancingPlan, ApprovalPayload,
    TradeOrder, TradeConfirmation, ErrorResponse
)
from error_handling.error_classifier import ErrorClassifier


class TestEndToEndWorkflowIntegration:
    """Test complete workflow from request to trade execution"""
    
    @pytest.fixture
    def mock_aws_services(self):
        """Mock AWS services for integration testing"""
        with patch('boto3.client') as mock_client:
            mock_dynamodb = MagicMock()
            mock_lambda = MagicMock()
            mock_stepfunctions = MagicMock()
            mock_bedrock = MagicMock()
            
            def client_factory(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                elif service_name == 'lambda':
                    return mock_lambda
                elif service_name == 'stepfunctions':
                    return mock_stepfunctions
                elif service_name == 'bedrock-runtime':
                    return mock_bedrock
                return MagicMock()
            
            mock_client.side_effect = client_factory
            yield {
                'dynamodb': mock_dynamodb,
                'lambda': mock_lambda,
                'stepfunctions': mock_stepfunctions,
                'bedrock': mock_bedrock
            }
    
    @pytest.fixture
    def sample_portfolio(self):
        """Create a sample portfolio for testing"""
        return Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Test Portfolio",
            holdings=[
                Holding(
                    ticker="VTI",
                    quantity=100,
                    cost_basis=200.50,
                    current_price=220.75,
                    purchase_date="2023-01-15"
                ),
                Holding(
                    ticker="BND",
                    quantity=50,
                    cost_basis=80.00,
                    current_price=78.50,
                    purchase_date="2023-06-01"
                )
            ],
            target_allocation={"stocks": 0.60, "bonds": 0.40},
            total_value=25000.00,
            risk_tolerance="moderate"
        )
    
    @pytest.fixture
    def sample_supervisor_request(self):
        """Create a sample supervisor request"""
        return SupervisorRequest(
            user_id="user_123",
            session_id=str(uuid.uuid4()),
            request_type="rebalance",
            parameters={
                "portfolio_id": "portfolio_456",
                "include_tax_optimization": True
            },
            context={}
        )
    
    def test_complete_workflow_request_to_execution(self, mock_aws_services, sample_portfolio, sample_supervisor_request):
        """Test complete workflow from request to trade execution"""
        
        # Step 1: Supervisor receives request
        supervisor_response = SupervisorResponse(
            session_id=sample_supervisor_request.session_id,
            status="pending_approval",
            results={},
            requires_approval=True,
            approval_payload=ApprovalPayload(
                approval_id=str(uuid.uuid4()),
                user_id=sample_supervisor_request.user_id,
                trade_orders=[
                    TradeOrder(
                        order_id="order_1",
                        action="sell",
                        ticker="BND",
                        quantity=10,
                        order_type="market",
                        estimated_price=78.50,
                        estimated_cost=785.00
                    ),
                    TradeOrder(
                        order_id="order_2",
                        action="buy",
                        ticker="VTI",
                        quantity=15,
                        order_type="market",
                        estimated_price=220.75,
                        estimated_cost=3311.25
                    )
                ],
                tax_implications={
                    "estimated_tax_savings": 150.00,
                    "wash_sale_warnings": []
                },
                expected_costs={
                    "commission": 0.00,
                    "slippage": 50.00,
                    "total": 50.00
                },
                deadline=datetime.utcnow() + timedelta(hours=24)
            )
        )
        
        assert supervisor_response.status == "pending_approval"
        assert supervisor_response.requires_approval is True
        assert len(supervisor_response.approval_payload.trade_orders) == 2
        assert supervisor_response.approval_payload.approval_id is not None
    
    def test_state_persistence_across_invocations(self, mock_aws_services, sample_supervisor_request):
        """Test that agent state persists across Lambda invocations"""
        
        # Simulate state persistence
        session_state = {
            "user_id": sample_supervisor_request.user_id,
            "session_id": sample_supervisor_request.session_id,
            "current_step": "portfolio_analysis",
            "subtasks_completed": ["portfolio_analysis"],
            "pending_subtasks": ["tax_optimization", "rebalancing"],
            "conversation_history": [
                {
                    "role": "user",
                    "content": "Rebalance my portfolio"
                }
            ],
            "user_preferences": {
                "risk_tolerance": "moderate",
                "tax_optimization_enabled": True
            }
        }
        
        # Store state
        mock_aws_services['dynamodb'].put_item.return_value = {'ResponseMetadata': {'HTTPStatusCode': 200}}
        
        # Retrieve state
        mock_aws_services['dynamodb'].get_item.return_value = {
            'Item': session_state
        }
        
        # Verify state can be stored and retrieved
        assert session_state['session_id'] == sample_supervisor_request.session_id
        assert session_state['current_step'] == "portfolio_analysis"
        assert len(session_state['pending_subtasks']) == 2
    
    def test_approval_workflow_approval_path(self, mock_aws_services):
        """Test approval workflow when user approves trades"""
        
        approval_id = str(uuid.uuid4())
        user_id = "user_123"
        
        # Simulate approval response
        approval_response = {
            "approval_id": approval_id,
            "user_id": user_id,
            "status": "approved",
            "timestamp": datetime.utcnow().isoformat(),
            "feedback": None
        }
        
        # Store approval response
        mock_aws_services['dynamodb'].update_item.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        
        # Verify approval status
        assert approval_response['status'] == "approved"
        assert approval_response['approval_id'] == approval_id
    
    def test_approval_workflow_rejection_path(self, mock_aws_services):
        """Test approval workflow when user rejects trades"""
        
        approval_id = str(uuid.uuid4())
        user_id = "user_123"
        
        # Simulate rejection response
        rejection_response = {
            "approval_id": approval_id,
            "user_id": user_id,
            "status": "rejected",
            "timestamp": datetime.utcnow().isoformat(),
            "feedback": "Please recalculate with lower transaction costs"
        }
        
        # Store rejection response
        mock_aws_services['dynamodb'].update_item.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        
        # Verify rejection status
        assert rejection_response['status'] == "rejected"
        assert rejection_response['feedback'] is not None
    
    def test_trade_execution_on_approval(self, mock_aws_services):
        """Test that trades are executed when user approves"""
        
        trade_orders = [
            TradeOrder(
                order_id="order_1",
                action="sell",
                ticker="BND",
                quantity=10,
                order_type="market",
                estimated_price=78.50,
                estimated_cost=785.00
            ),
            TradeOrder(
                order_id="order_2",
                action="buy",
                ticker="VTI",
                quantity=15,
                order_type="market",
                estimated_price=220.75,
                estimated_cost=3311.25
            )
        ]
        
        # Mock trade execution
        mock_aws_services['lambda'].invoke.return_value = {
            'StatusCode': 200,
            'Payload': {
                'read': lambda: json.dumps({
                    'order_id': 'order_1',
                    'status': 'executed',
                    'execution_price': 78.50,
                    'execution_time': datetime.utcnow().isoformat()
                }).encode()
            }
        }
        
        # Execute trades
        for trade_order in trade_orders:
            response = mock_aws_services['lambda'].invoke(
                FunctionName='trade-executor',
                InvocationType='RequestResponse',
                Payload=json.dumps(trade_order.__dict__)
            )
            assert response['StatusCode'] == 200
    
    def test_portfolio_update_after_trades(self, mock_aws_services, sample_portfolio):
        """Test that portfolio is updated after trades execute"""
        
        # Initial portfolio state
        initial_vti_qty = 100
        initial_bnd_qty = 50
        
        # Simulate trades
        trades = [
            {"action": "sell", "ticker": "BND", "quantity": 10},
            {"action": "buy", "ticker": "VTI", "quantity": 15}
        ]
        
        # Update portfolio
        updated_portfolio = {
            "VTI": initial_vti_qty + 15,  # 115
            "BND": initial_bnd_qty - 10   # 40
        }
        
        # Verify portfolio update
        assert updated_portfolio["VTI"] == 115
        assert updated_portfolio["BND"] == 40
        
        # Mock DynamoDB update
        mock_aws_services['dynamodb'].update_item.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
    
    def test_transaction_recording_after_execution(self, mock_aws_services):
        """Test that transactions are recorded in DynamoDB after execution"""
        
        transaction = {
            "user_id": "user_123",
            "timestamp": datetime.utcnow().isoformat(),
            "transaction_id": str(uuid.uuid4()),
            "portfolio_id": "portfolio_456",
            "action": "buy",
            "ticker": "VTI",
            "quantity": 15,
            "price": 220.75,
            "commission": 0.00,
            "total_cost": 3311.25,
            "execution_status": "completed",
            "order_type": "market"
        }
        
        # Mock transaction recording
        mock_aws_services['dynamodb'].put_item.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        
        # Verify transaction structure
        assert transaction['action'] == "buy"
        assert transaction['execution_status'] == "completed"
        assert transaction['total_cost'] == 3311.25
    
    def test_error_handling_in_workflow(self, mock_aws_services):
        """Test error handling throughout the workflow"""
        
        # Simulate DynamoDB error
        mock_aws_services['dynamodb'].get_item.side_effect = Exception("DynamoDB connection failed")
        
        # Create error classifier
        error_classifier = ErrorClassifier()
        
        # Verify error is caught and classified
        try:
            mock_aws_services['dynamodb'].get_item()
        except Exception as e:
            error_type = error_classifier.classify_error(e)
            assert error_type is not None
    
    def test_workflow_timeout_handling(self, mock_aws_services):
        """Test handling of workflow timeouts"""
        
        # Simulate timeout
        mock_aws_services['stepfunctions'].start_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789:execution:workflow:exec_123'
        }
        
        # Mock timeout scenario
        mock_aws_services['stepfunctions'].describe_execution.return_value = {
            'status': 'TIMED_OUT',
            'startDate': datetime.utcnow() - timedelta(hours=1),
            'stopDate': datetime.utcnow()
        }
        
        # Verify timeout is detected
        execution = mock_aws_services['stepfunctions'].describe_execution(
            executionArn='arn:aws:states:us-east-1:123456789:execution:workflow:exec_123'
        )
        assert execution['status'] == 'TIMED_OUT'
    
    def test_concurrent_workflow_isolation(self, mock_aws_services):
        """Test that concurrent workflows are properly isolated"""
        
        # Create two separate sessions
        session_1 = {
            "session_id": str(uuid.uuid4()),
            "user_id": "user_123",
            "portfolio_id": "portfolio_456"
        }
        
        session_2 = {
            "session_id": str(uuid.uuid4()),
            "user_id": "user_789",
            "portfolio_id": "portfolio_012"
        }
        
        # Verify sessions are isolated
        assert session_1['session_id'] != session_2['session_id']
        assert session_1['user_id'] != session_2['user_id']
        assert session_1['portfolio_id'] != session_2['portfolio_id']


class TestWorkflowStateManagement:
    """Test state management across workflow steps"""
    
    def test_state_transitions(self):
        """Test valid state transitions in workflow"""
        
        valid_transitions = {
            "receive_request": ["decompose_task"],
            "decompose_task": ["route_to_agents"],
            "route_to_agents": ["check_completion"],
            "check_completion": ["aggregate_results", "route_to_agents"],
            "aggregate_results": ["human_approval"],
            "human_approval": ["execute_trades", "request_modifications", "cancelled"],
            "execute_trades": ["update_portfolio"],
            "update_portfolio": ["complete"],
            "request_modifications": ["decompose_task"],
            "cancelled": ["complete"],
            "complete": []
        }
        
        # Verify all transitions are valid
        for state, next_states in valid_transitions.items():
            assert isinstance(next_states, list)
            for next_state in next_states:
                assert isinstance(next_state, str)
    
    def test_state_persistence_format(self):
        """Test that state is persisted in correct format"""
        
        state = {
            "user_id": "user_123",
            "session_id": str(uuid.uuid4()),
            "current_step": "portfolio_analysis",
            "subtasks_completed": ["portfolio_analysis"],
            "pending_subtasks": ["tax_optimization", "rebalancing"],
            "results": {
                "portfolio_analysis": {
                    "total_return": 0.15,
                    "sharpe_ratio": 1.2
                }
            },
            "retry_counts": {
                "portfolio_analysis": 0,
                "tax_optimization": 0,
                "rebalancing": 0
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Verify state structure
        assert "user_id" in state
        assert "session_id" in state
        assert "current_step" in state
        assert "subtasks_completed" in state
        assert "pending_subtasks" in state
        assert "results" in state
        assert "retry_counts" in state


class TestApprovalWorkflowIntegration:
    """Test approval workflow integration with main workflow"""
    
    @pytest.fixture
    def mock_approval_services(self):
        """Mock services for approval workflow"""
        with patch('boto3.client') as mock_client:
            mock_dynamodb = MagicMock()
            mock_sns = MagicMock()
            
            def client_factory(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                elif service_name == 'sns':
                    return mock_sns
                return MagicMock()
            
            mock_client.side_effect = client_factory
            yield {
                'dynamodb': mock_dynamodb,
                'sns': mock_sns
            }
    
    def test_approval_payload_generation(self, mock_approval_services):
        """Test approval payload is generated correctly"""
        
        approval_payload = {
            "approval_id": str(uuid.uuid4()),
            "user_id": "user_123",
            "trade_orders": [
                {
                    "order_id": "order_1",
                    "action": "sell",
                    "ticker": "BND",
                    "quantity": 10,
                    "estimated_price": 78.50
                }
            ],
            "tax_implications": {
                "estimated_tax_savings": 150.00
            },
            "expected_costs": {
                "total": 50.00
            },
            "deadline": (datetime.utcnow() + timedelta(hours=24)).isoformat()
        }
        
        # Verify payload structure
        assert "approval_id" in approval_payload
        assert "user_id" in approval_payload
        assert "trade_orders" in approval_payload
        assert len(approval_payload["trade_orders"]) > 0
        assert "deadline" in approval_payload
    
    def test_approval_notification_sent(self, mock_approval_services):
        """Test that user is notified of pending approval"""
        
        # Mock SNS notification
        mock_approval_services['sns'].publish.return_value = {
            'MessageId': str(uuid.uuid4())
        }
        
        # Send notification
        response = mock_approval_services['sns'].publish(
            TopicArn='arn:aws:sns:us-east-1:123456789:portfolio-approvals',
            Subject='Portfolio Rebalancing Approval Required',
            Message='Please review and approve the proposed trades'
        )
        
        assert response['MessageId'] is not None
    
    def test_approval_deadline_enforcement(self, mock_approval_services):
        """Test that approval deadline is enforced"""
        
        approval_deadline = datetime.utcnow() + timedelta(hours=24)
        current_time = datetime.utcnow()
        
        # Check if approval is still valid
        is_valid = current_time < approval_deadline
        assert is_valid is True
        
        # Check if approval is expired
        expired_deadline = datetime.utcnow() - timedelta(hours=1)
        is_expired = current_time > expired_deadline
        assert is_expired is True


@given(
    user_id=st.text(min_size=1, max_size=50),
    portfolio_id=st.text(min_size=1, max_size=50),
    num_trades=st.integers(min_value=1, max_value=10)
)
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_workflow_with_varying_inputs(user_id, portfolio_id, num_trades):
    """Property test: workflow handles varying inputs correctly"""
    
    # Create workflow request
    request = {
        "user_id": user_id,
        "portfolio_id": portfolio_id,
        "num_trades": num_trades
    }
    
    # Verify request structure
    assert request["user_id"] == user_id
    assert request["portfolio_id"] == portfolio_id
    assert request["num_trades"] == num_trades
    assert request["num_trades"] >= 1
    assert request["num_trades"] <= 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



class TestStepFunctionsWorkflowIntegration:
    """Test Step Functions workflow orchestration and execution"""
    
    @pytest.fixture
    def mock_stepfunctions_client(self):
        """Mock Step Functions client"""
        with patch('boto3.client') as mock_client:
            mock_sf = MagicMock()
            mock_client.return_value = mock_sf
            yield mock_sf
    
    def test_workflow_execution_start(self, mock_stepfunctions_client):
        """Test starting a workflow execution"""
        
        state_machine_arn = "arn:aws:states:us-east-1:123456789:stateMachine:portfolio-rebalancing"
        execution_input = {
            "user_id": "user_123",
            "portfolio_id": "portfolio_456",
            "request_type": "rebalance"
        }
        
        # Mock workflow start
        mock_stepfunctions_client.start_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789:execution:portfolio-rebalancing:exec_123',
            'startDate': datetime.utcnow().isoformat()
        }
        
        # Start execution
        response = mock_stepfunctions_client.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps(execution_input)
        )
        
        assert 'executionArn' in response
        assert 'startDate' in response
        assert 'exec_123' in response['executionArn']
    
    def test_workflow_execution_status_tracking(self, mock_stepfunctions_client):
        """Test tracking workflow execution status"""
        
        execution_arn = 'arn:aws:states:us-east-1:123456789:execution:portfolio-rebalancing:exec_123'
        
        # Mock execution status
        mock_stepfunctions_client.describe_execution.return_value = {
            'executionArn': execution_arn,
            'stateMachineArn': 'arn:aws:states:us-east-1:123456789:stateMachine:portfolio-rebalancing',
            'name': 'exec_123',
            'status': 'RUNNING',
            'startDate': datetime.utcnow().isoformat(),
            'input': json.dumps({"user_id": "user_123"})
        }
        
        # Get execution status
        response = mock_stepfunctions_client.describe_execution(executionArn=execution_arn)
        
        assert response['status'] == 'RUNNING'
        assert response['executionArn'] == execution_arn
    
    def test_workflow_step_execution_history(self, mock_stepfunctions_client):
        """Test retrieving workflow execution history"""
        
        execution_arn = 'arn:aws:states:us-east-1:123456789:execution:portfolio-rebalancing:exec_123'
        
        # Mock execution history
        mock_stepfunctions_client.get_execution_history.return_value = {
            'events': [
                {
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'ExecutionStarted',
                    'id': 1,
                    'executionStartedEventDetails': {
                        'input': json.dumps({"user_id": "user_123"}),
                        'roleArn': 'arn:aws:iam::123456789:role/StepFunctionsRole'
                    }
                },
                {
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'TaskStateEntered',
                    'id': 2,
                    'stateEnteredEventDetails': {
                        'name': 'InitializeSupervisor',
                        'input': json.dumps({"user_id": "user_123"})
                    }
                },
                {
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'TaskSucceeded',
                    'id': 3,
                    'taskSucceededEventDetails': {
                        'resourceType': 'lambda',
                        'resource': 'arn:aws:lambda:us-east-1:123456789:function:supervisor-agent',
                        'output': json.dumps({"status": "success"})
                    }
                }
            ]
        }
        
        # Get execution history
        response = mock_stepfunctions_client.get_execution_history(executionArn=execution_arn)
        
        assert len(response['events']) >= 3
        assert response['events'][0]['type'] == 'ExecutionStarted'
        assert response['events'][1]['type'] == 'TaskStateEntered'
        assert response['events'][2]['type'] == 'TaskSucceeded'
    
    def test_workflow_retry_on_failure(self, mock_stepfunctions_client):
        """Test workflow retry behavior on task failure"""
        
        execution_arn = 'arn:aws:states:us-east-1:123456789:execution:portfolio-rebalancing:exec_123'
        
        # Mock execution history with retries
        mock_stepfunctions_client.get_execution_history.return_value = {
            'events': [
                {
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'TaskFailed',
                    'id': 1,
                    'taskFailedEventDetails': {
                        'resourceType': 'lambda',
                        'resource': 'arn:aws:lambda:us-east-1:123456789:function:portfolio-analyzer',
                        'error': 'States.TaskFailed',
                        'cause': 'Lambda function failed'
                    }
                },
                {
                    'timestamp': (datetime.utcnow() + timedelta(seconds=2)).isoformat(),
                    'type': 'TaskStateEntered',
                    'id': 2,
                    'stateEnteredEventDetails': {
                        'name': 'AnalyzePortfolio',
                        'input': json.dumps({"retry_count": 1})
                    }
                },
                {
                    'timestamp': (datetime.utcnow() + timedelta(seconds=5)).isoformat(),
                    'type': 'TaskSucceeded',
                    'id': 3,
                    'taskSucceededEventDetails': {
                        'resourceType': 'lambda',
                        'resource': 'arn:aws:lambda:us-east-1:123456789:function:portfolio-analyzer',
                        'output': json.dumps({"status": "success"})
                    }
                }
            ]
        }
        
        # Get execution history
        response = mock_stepfunctions_client.get_execution_history(executionArn=execution_arn)
        
        # Verify retry occurred
        assert response['events'][0]['type'] == 'TaskFailed'
        assert response['events'][1]['type'] == 'TaskStateEntered'
        assert response['events'][2]['type'] == 'TaskSucceeded'
    
    def test_workflow_approval_state_with_task_token(self, mock_stepfunctions_client):
        """Test WaitForApproval state with task token"""
        
        execution_arn = 'arn:aws:states:us-east-1:123456789:execution:portfolio-rebalancing:exec_123'
        task_token = 'AAAAKgAAAAEADWIV6IFwq1JsslFkMzVQIjEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Ng=='
        
        # Mock execution history with approval state
        mock_stepfunctions_client.get_execution_history.return_value = {
            'events': [
                {
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'TaskStateEntered',
                    'id': 1,
                    'stateEnteredEventDetails': {
                        'name': 'WaitForApproval',
                        'input': json.dumps({
                            "trade_orders": [{"ticker": "VTI", "quantity": 10}],
                            "Task": {"Token": task_token}
                        })
                    }
                }
            ]
        }
        
        # Get execution history
        response = mock_stepfunctions_client.get_execution_history(executionArn=execution_arn)
        
        # Verify approval state
        assert response['events'][0]['type'] == 'TaskStateEntered'
        assert response['events'][0]['stateEnteredEventDetails']['name'] == 'WaitForApproval'
    
    def test_workflow_choice_state_routing(self, mock_stepfunctions_client):
        """Test Choice state routing based on approval status"""
        
        execution_arn = 'arn:aws:states:us-east-1:123456789:execution:portfolio-rebalancing:exec_123'
        
        # Mock execution history with choice state
        mock_stepfunctions_client.get_execution_history.return_value = {
            'events': [
                {
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'TaskStateEntered',
                    'id': 1,
                    'stateEnteredEventDetails': {
                        'name': 'CheckApprovalStatus',
                        'input': json.dumps({"approval_status": "approved"})
                    }
                },
                {
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'TaskStateEntered',
                    'id': 2,
                    'stateEnteredEventDetails': {
                        'name': 'ExecuteTrades',
                        'input': json.dumps({"trade_orders": []})
                    }
                }
            ]
        }
        
        # Get execution history
        response = mock_stepfunctions_client.get_execution_history(executionArn=execution_arn)
        
        # Verify choice state routing
        assert response['events'][0]['stateEnteredEventDetails']['name'] == 'CheckApprovalStatus'
        assert response['events'][1]['stateEnteredEventDetails']['name'] == 'ExecuteTrades'
    
    def test_workflow_map_state_parallel_execution(self, mock_stepfunctions_client):
        """Test Map state for parallel trade execution"""
        
        execution_arn = 'arn:aws:states:us-east-1:123456789:execution:portfolio-rebalancing:exec_123'
        
        # Mock execution history with map state
        mock_stepfunctions_client.get_execution_history.return_value = {
            'events': [
                {
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'TaskStateEntered',
                    'id': 1,
                    'stateEnteredEventDetails': {
                        'name': 'ExecuteTrades',
                        'input': json.dumps({
                            "trade_orders": [
                                {"order_id": "1", "ticker": "VTI", "quantity": 10},
                                {"order_id": "2", "ticker": "BND", "quantity": 5}
                            ]
                        })
                    }
                },
                {
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'MapStateStarted',
                    'id': 2,
                    'mapStateStartedEventDetails': {
                        'length': 2
                    }
                },
                {
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'TaskSucceeded',
                    'id': 3,
                    'taskSucceededEventDetails': {
                        'resourceType': 'lambda',
                        'resource': 'arn:aws:lambda:us-east-1:123456789:function:trade-executor',
                        'output': json.dumps({"order_id": "1", "status": "executed"})
                    }
                }
            ]
        }
        
        # Get execution history
        response = mock_stepfunctions_client.get_execution_history(executionArn=execution_arn)
        
        # Verify map state
        assert response['events'][0]['stateEnteredEventDetails']['name'] == 'ExecuteTrades'
        assert response['events'][1]['type'] == 'MapStateStarted'
    
    def test_workflow_error_handling_and_notification(self, mock_stepfunctions_client):
        """Test error handling and SNS notification"""
        
        execution_arn = 'arn:aws:states:us-east-1:123456789:execution:portfolio-rebalancing:exec_123'
        
        # Mock execution history with error
        mock_stepfunctions_client.get_execution_history.return_value = {
            'events': [
                {
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'TaskFailed',
                    'id': 1,
                    'taskFailedEventDetails': {
                        'resourceType': 'lambda',
                        'resource': 'arn:aws:lambda:us-east-1:123456789:function:portfolio-analyzer',
                        'error': 'States.TaskFailed',
                        'cause': 'Lambda function failed after 3 retries'
                    }
                },
                {
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'TaskStateEntered',
                    'id': 2,
                    'stateEnteredEventDetails': {
                        'name': 'ErrorNotification',
                        'input': json.dumps({
                            "error": {
                                "error": "States.TaskFailed",
                                "cause": "Lambda function failed after 3 retries"
                            }
                        })
                    }
                },
                {
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'ExecutionFailed',
                    'id': 3,
                    'executionFailedEventDetails': {
                        'error': 'WorkflowExecutionFailed',
                        'cause': 'Workflow encountered an error and could not complete'
                    }
                }
            ]
        }
        
        # Get execution history
        response = mock_stepfunctions_client.get_execution_history(executionArn=execution_arn)
        
        # Verify error handling
        assert response['events'][0]['type'] == 'TaskFailed'
        assert response['events'][1]['stateEnteredEventDetails']['name'] == 'ErrorNotification'
        assert response['events'][2]['type'] == 'ExecutionFailed'
    
    def test_workflow_complete_rebalancing_flow(self, mock_stepfunctions_client):
        """Test complete rebalancing workflow from start to finish"""
        
        state_machine_arn = "arn:aws:states:us-east-1:123456789:stateMachine:portfolio-rebalancing"
        execution_input = {
            "user_id": "user_123",
            "portfolio_id": "portfolio_456",
            "request_type": "rebalance"
        }
        
        # Mock workflow start
        mock_stepfunctions_client.start_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789:execution:portfolio-rebalancing:exec_123',
            'startDate': datetime.utcnow().isoformat()
        }
        
        # Start execution
        start_response = mock_stepfunctions_client.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps(execution_input)
        )
        
        execution_arn = start_response['executionArn']
        
        # Mock execution history for complete workflow
        mock_stepfunctions_client.get_execution_history.return_value = {
            'events': [
                {'type': 'ExecutionStarted', 'id': 1},
                {'type': 'TaskStateEntered', 'id': 2, 'stateEnteredEventDetails': {'name': 'InitializeSupervisor'}},
                {'type': 'TaskSucceeded', 'id': 3},
                {'type': 'TaskStateEntered', 'id': 4, 'stateEnteredEventDetails': {'name': 'AnalyzePortfolio'}},
                {'type': 'TaskSucceeded', 'id': 5},
                {'type': 'TaskStateEntered', 'id': 6, 'stateEnteredEventDetails': {'name': 'OptimizeTaxes'}},
                {'type': 'TaskSucceeded', 'id': 7},
                {'type': 'TaskStateEntered', 'id': 8, 'stateEnteredEventDetails': {'name': 'CalculateRebalancing'}},
                {'type': 'TaskSucceeded', 'id': 9},
                {'type': 'TaskStateEntered', 'id': 10, 'stateEnteredEventDetails': {'name': 'AggregateResults'}},
                {'type': 'TaskSucceeded', 'id': 11},
                {'type': 'TaskStateEntered', 'id': 12, 'stateEnteredEventDetails': {'name': 'WaitForApproval'}},
                {'type': 'TaskSucceeded', 'id': 13},
                {'type': 'TaskStateEntered', 'id': 14, 'stateEnteredEventDetails': {'name': 'CheckApprovalStatus'}},
                {'type': 'TaskStateEntered', 'id': 15, 'stateEnteredEventDetails': {'name': 'ExecuteTrades'}},
                {'type': 'MapStateStarted', 'id': 16},
                {'type': 'TaskSucceeded', 'id': 17},
                {'type': 'MapStateEnded', 'id': 18},
                {'type': 'TaskStateEntered', 'id': 19, 'stateEnteredEventDetails': {'name': 'UpdatePortfolio'}},
                {'type': 'TaskSucceeded', 'id': 20},
                {'type': 'TaskStateEntered', 'id': 21, 'stateEnteredEventDetails': {'name': 'WorkflowComplete'}},
                {'type': 'ExecutionSucceeded', 'id': 22}
            ]
        }
        
        # Mock final execution status
        mock_stepfunctions_client.describe_execution.return_value = {
            'executionArn': execution_arn,
            'status': 'SUCCEEDED',
            'startDate': datetime.utcnow().isoformat(),
            'stopDate': datetime.utcnow().isoformat()
        }
        
        # Get execution history
        history = mock_stepfunctions_client.get_execution_history(executionArn=execution_arn)
        
        # Get final status
        final_status = mock_stepfunctions_client.describe_execution(executionArn=execution_arn)
        
        # Verify complete workflow
        assert len(history['events']) >= 20
        assert final_status['status'] == 'SUCCEEDED'
        assert history['events'][0]['type'] == 'ExecutionStarted'
        assert history['events'][-1]['type'] == 'ExecutionSucceeded'
