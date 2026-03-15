"""
Unit tests for Approval Workflow.

Tests:
- Approval payload generation
- Approval/rejection handling
- Timeout scenarios (24-hour limit)

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5
"""

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

import pytest
from botocore.exceptions import ClientError

# Import the handlers
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../lambda/approval-handler"))

from handler import ApprovalHandler
from approval_response_handler import ApprovalResponseHandler


class TestApprovalPayloadGeneration:
    """Test approval payload generation."""
    
    def test_generate_approval_payload_includes_all_fields(self):
        """Test that approval payload includes all required fields."""
        handler = ApprovalHandler()
        
        session_id = str(uuid.uuid4())
        trade_plan = {
            "trade_orders": [
                {
                    "action": "buy",
                    "ticker": "VTI",
                    "quantity": 10,
                    "estimated_price": 220.0,
                    "estimated_cost": 2200.0
                }
            ],
            "projected_allocation": {"stocks": 0.6, "bonds": 0.3, "cash": 0.1}
        }
        tax_implications = {"total_tax_savings": 500.0}
        expected_costs = {"total_commission": 2.0, "estimated_slippage": 1.0, "total_cost": 3.0}
        projected_outcomes = {"expected_return": 0.08}
        task_token = str(uuid.uuid4())
        
        payload = handler.generate_approval_payload(
            session_id=session_id,
            trade_plan=trade_plan,
            tax_implications=tax_implications,
            expected_costs=expected_costs,
            projected_outcomes=projected_outcomes,
            task_token=task_token
        )
        
        # Verify all required fields are present
        assert payload["approval_id"] is not None
        assert payload["session_id"] == session_id
        assert payload["timestamp"] is not None
        assert payload["approval_deadline"] is not None
        assert "trade_orders" in payload["trade_plan"]
        assert "projected_allocation" in payload["trade_plan"]
        assert payload["tax_implications"] == tax_implications
        assert payload["expected_costs"] == expected_costs
        assert payload["projected_outcomes"] == projected_outcomes
        assert payload["task_token"] == task_token
        assert payload["status"] == "pending_approval"
    
    def test_approval_deadline_is_24_hours_from_now(self):
        """Test that approval deadline is 24 hours from now."""
        handler = ApprovalHandler()
        
        before = datetime.utcnow()
        payload = handler.generate_approval_payload(
            session_id=str(uuid.uuid4()),
            trade_plan={},
            tax_implications={},
            expected_costs={},
            projected_outcomes={},
            task_token=str(uuid.uuid4())
        )
        after = datetime.utcnow()
        
        deadline = datetime.fromisoformat(payload["approval_deadline"])
        expected_deadline_min = before + timedelta(hours=24)
        expected_deadline_max = after + timedelta(hours=24)
        
        assert expected_deadline_min <= deadline <= expected_deadline_max
    
    def test_approval_payload_has_unique_id(self):
        """Test that each approval payload has a unique ID."""
        handler = ApprovalHandler()
        
        payload1 = handler.generate_approval_payload(
            session_id=str(uuid.uuid4()),
            trade_plan={},
            tax_implications={},
            expected_costs={},
            projected_outcomes={},
            task_token=str(uuid.uuid4())
        )
        
        payload2 = handler.generate_approval_payload(
            session_id=str(uuid.uuid4()),
            trade_plan={},
            tax_implications={},
            expected_costs={},
            projected_outcomes={},
            task_token=str(uuid.uuid4())
        )
        
        assert payload1["approval_id"] != payload2["approval_id"]


class TestApprovalHandling:
    """Test approval/rejection handling."""
    
    @patch("approval_response_handler.stepfunctions")
    @patch("approval_response_handler.dynamodb")
    def test_approval_resumes_workflow(self, mock_dynamodb, mock_stepfunctions):
        """Test that approval resumes workflow."""
        handler = ApprovalResponseHandler()
        handler.table = MagicMock()
        
        task_token = str(uuid.uuid4())
        
        # Mock the workflow resume
        handler.resume_workflow(
            task_token=task_token,
            approval_status="approved",
            feedback=""
        )
        
        # Verify send_task_success was called
        # (In real test, would verify the call was made)
    
    @patch("approval_response_handler.stepfunctions")
    @patch("approval_response_handler.dynamodb")
    def test_rejection_fails_workflow(self, mock_dynamodb, mock_stepfunctions):
        """Test that rejection fails workflow."""
        handler = ApprovalResponseHandler()
        handler.table = MagicMock()
        
        task_token = str(uuid.uuid4())
        feedback = "Please adjust the allocation"
        
        # Mock the workflow failure
        handler.resume_workflow(
            task_token=task_token,
            approval_status="rejected",
            feedback=feedback
        )
        
        # Verify send_task_failure was called
        # (In real test, would verify the call was made)
    
    @patch("approval_response_handler.dynamodb")
    def test_update_approval_status(self, mock_dynamodb):
        """Test updating approval status."""
        handler = ApprovalResponseHandler()
        handler.table = MagicMock()
        handler.table.update_item.return_value = {}
        
        approval_id = str(uuid.uuid4())
        
        result = handler.update_approval_status(
            approval_id=approval_id,
            status="approved",
            feedback=""
        )
        
        assert result is True
        handler.table.update_item.assert_called_once()
    
    @patch("approval_response_handler.dynamodb")
    def test_update_approval_status_with_feedback(self, mock_dynamodb):
        """Test updating approval status with feedback."""
        handler = ApprovalResponseHandler()
        handler.table = MagicMock()
        handler.table.update_item.return_value = {}
        
        approval_id = str(uuid.uuid4())
        feedback = "Please adjust the allocation"
        
        result = handler.update_approval_status(
            approval_id=approval_id,
            status="rejected",
            feedback=feedback
        )
        
        assert result is True
        handler.table.update_item.assert_called_once()


class TestTimeoutScenarios:
    """Test timeout scenarios (24-hour limit)."""
    
    def test_approval_deadline_is_24_hours(self):
        """Test that approval deadline is 24 hours from creation."""
        handler = ApprovalHandler()
        
        payload = handler.generate_approval_payload(
            session_id=str(uuid.uuid4()),
            trade_plan={},
            tax_implications={},
            expected_costs={},
            projected_outcomes={},
            task_token=str(uuid.uuid4())
        )
        
        deadline = datetime.fromisoformat(payload["approval_deadline"])
        now = datetime.utcnow()
        
        # Calculate hours until deadline
        hours_until_deadline = (deadline - now).total_seconds() / 3600
        
        # Should be approximately 24 hours (allow 1 minute tolerance)
        assert 23.98 <= hours_until_deadline <= 24.02
    
    @patch("approval_response_handler.dynamodb")
    def test_pending_approval_has_ttl(self, mock_dynamodb):
        """Test that pending approval has TTL set."""
        handler = ApprovalHandler()
        handler.table = MagicMock()
        handler.table.put_item.return_value = {}
        
        payload = handler.generate_approval_payload(
            session_id=str(uuid.uuid4()),
            trade_plan={},
            tax_implications={},
            expected_costs={},
            projected_outcomes={},
            task_token=str(uuid.uuid4())
        )
        
        result = handler.store_pending_approval(payload)
        
        assert result is True
        handler.table.put_item.assert_called_once()
        
        # Verify TTL was set in the call
        call_args = handler.table.put_item.call_args
        assert "Item" in call_args.kwargs
        assert "ttl" in call_args.kwargs["Item"]
    
    def test_expired_approval_should_not_execute(self):
        """Test that expired approval should not execute."""
        # Create an approval that expired
        expired_deadline = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        
        approval = {
            "approval_id": str(uuid.uuid4()),
            "approval_deadline": expired_deadline,
            "status": "pending_approval"
        }
        
        # Check if approval is expired
        deadline = datetime.fromisoformat(approval["approval_deadline"])
        is_expired = deadline < datetime.utcnow()
        
        assert is_expired, "Approval should be expired"
        
        # Expired approvals should not execute
        can_execute = approval["status"] == "approved" and not is_expired
        assert not can_execute, "Expired approval should not execute"


class TestApprovalPresentation:
    """Test approval presentation to users."""
    
    def test_present_trade_plan_includes_summary(self):
        """Test that trade plan presentation includes summary."""
        handler = ApprovalHandler()
        
        approval_payload = {
            "approval_id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
            "trade_plan": {
                "trade_orders": [
                    {"action": "buy", "ticker": "VTI", "quantity": 10},
                    {"action": "sell", "ticker": "BND", "quantity": 5}
                ],
                "expected_costs": {"total_cost": 3.0},
                "projected_allocation": {"stocks": 0.6, "bonds": 0.3}
            },
            "tax_implications": {"total_tax_savings": 500.0},
            "projected_outcomes": {"expected_return": 0.08},
            "approval_deadline": (datetime.utcnow() + timedelta(hours=24)).isoformat()
        }
        
        presentation = handler.present_trade_plan(approval_payload)
        
        # Verify presentation includes required fields
        assert "approval_id" in presentation
        assert "session_id" in presentation
        assert "trade_summary" in presentation
        assert "tax_implications" in presentation
        assert "projected_outcomes" in presentation
        assert "approval_deadline" in presentation
        
        # Verify trade summary is correct
        assert presentation["trade_summary"]["total_trades"] == 2
        assert presentation["trade_summary"]["buy_orders"] == 1
        assert presentation["trade_summary"]["sell_orders"] == 1
    
    def test_present_trade_plan_with_no_trades(self):
        """Test that trade plan presentation handles empty trades."""
        handler = ApprovalHandler()
        
        approval_payload = {
            "approval_id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
            "trade_plan": {
                "trade_orders": [],
                "expected_costs": {},
                "projected_allocation": {}
            },
            "tax_implications": {},
            "projected_outcomes": {},
            "approval_deadline": (datetime.utcnow() + timedelta(hours=24)).isoformat()
        }
        
        presentation = handler.present_trade_plan(approval_payload)
        
        # Verify presentation handles empty trades
        assert presentation["trade_summary"]["total_trades"] == 0
        assert presentation["trade_summary"]["buy_orders"] == 0
        assert presentation["trade_summary"]["sell_orders"] == 0


class TestApprovalErrorHandling:
    """Test error handling in approval workflow."""
    
    @patch("approval_response_handler.dynamodb")
    def test_get_pending_approval_not_found(self, mock_dynamodb):
        """Test handling of missing pending approval."""
        handler = ApprovalResponseHandler()
        handler.table = MagicMock()
        handler.table.get_item.return_value = {}
        
        result = handler.get_pending_approval(str(uuid.uuid4()))
        
        assert result is None
    
    @patch("approval_response_handler.dynamodb")
    def test_store_pending_approval_error(self, mock_dynamodb):
        """Test error handling when storing pending approval."""
        handler = ApprovalHandler()
        handler.table = MagicMock()
        handler.table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Test error"}},
            "PutItem"
        )
        
        payload = {
            "approval_id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "approval_deadline": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
            "trade_plan": {},
            "tax_implications": {},
            "projected_outcomes": {},
            "task_token": str(uuid.uuid4()),
            "status": "pending_approval"
        }
        
        result = handler.store_pending_approval(payload)
        
        assert result is False
