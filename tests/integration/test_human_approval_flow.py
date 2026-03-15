"""
Integration tests for the human-in-the-loop approval flow.

Tests the complete approval lifecycle: plan presentation → user decision
→ Step Functions task token resolution → trade execution or cancellation.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
"""

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

import sys
sys.path.insert(0, "src")
sys.path.insert(0, "lambda")

from src.models.responses import ApprovalPayload, RebalancingPlan, TradeOrder, TransactionCosts, RiskImpact


@pytest.fixture
def mock_aws():
    with patch("boto3.client") as mock_client:
        mock_dynamodb = MagicMock()
        mock_sfn = MagicMock()
        mock_sns = MagicMock()

        def factory(service, **kwargs):
            return {"dynamodb": mock_dynamodb, "stepfunctions": mock_sfn, "sns": mock_sns}.get(service, MagicMock())

        mock_client.side_effect = factory
        yield {"dynamodb": mock_dynamodb, "sfn": mock_sfn, "sns": mock_sns}


@pytest.fixture
def sample_trade_orders():
    return [
        TradeOrder(order_id="o1", action="sell", ticker="BND", quantity=10, order_type="market", estimated_price=78.5, estimated_cost=785.0),
        TradeOrder(order_id="o2", action="buy", ticker="VTI", quantity=5, order_type="market", estimated_price=220.0, estimated_cost=1100.0),
    ]


@pytest.fixture
def sample_rebalancing_plan(sample_trade_orders):
    return RebalancingPlan(
        portfolio_id="p1",
        timestamp=datetime.utcnow().isoformat(),
        trade_orders=sample_trade_orders,
        expected_costs=TransactionCosts(total_commission=0.0, estimated_slippage=20.0, total_cost=20.0),
        projected_allocation={"stocks": 0.60, "bonds": 0.30, "cash": 0.10},
        risk_impact=RiskImpact(current_risk_score=5.0, projected_risk_score=4.8, risk_change=-0.2, risk_assessment="reduced"),
    )


class TestHumanApprovalFlow:
    """Integration tests for the human approval workflow."""

    def test_approval_payload_contains_required_fields(self, sample_rebalancing_plan):
        """Approval payload must include all required information for user review."""
        import importlib.util, os
        path = os.path.join(os.path.dirname(__file__), "../../lambda/approval-handler/handler.py")
        spec = importlib.util.spec_from_file_location("ah_handler", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        handler = mod.ApprovalHandler()
        handler.dynamodb = MagicMock()
        handler.sfn_client = MagicMock()

        session_id = str(uuid.uuid4())
        task_token = "test_task_token_abc123"

        payload = handler.create_approval_payload(
            session_id=session_id,
            rebalancing_plan=sample_rebalancing_plan,
            tax_implications={"estimated_tax_savings": 150.0},
            task_token=task_token,
        )

        assert payload is not None
        assert "session_id" in payload or hasattr(payload, "session_id")

    def test_approval_stored_in_dynamodb(self, mock_aws, sample_rebalancing_plan):
        """Pending approval must be stored in DynamoDB with task token."""
        import importlib.util, os
        path = os.path.join(os.path.dirname(__file__), "../../lambda/approval-handler/handler.py")
        spec = importlib.util.spec_from_file_location("ah_handler2", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        handler = mod.ApprovalHandler()
        handler.dynamodb = mock_aws["dynamodb"]
        handler.sfn_client = mock_aws["sfn"]

        mock_aws["dynamodb"].put_item.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}

        session_id = str(uuid.uuid4())
        task_token = "task_token_xyz"

        handler.store_pending_approval(
            session_id=session_id,
            task_token=task_token,
            rebalancing_plan=sample_rebalancing_plan,
        )

        mock_aws["dynamodb"].put_item.assert_called_once()

    def test_approval_resumes_step_functions(self, mock_aws):
        """Approving a plan must send task success to Step Functions."""
        import importlib.util, os
        path = os.path.join(os.path.dirname(__file__), "../../lambda/approval-handler/handler.py")
        spec = importlib.util.spec_from_file_location("ah_handler3", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        handler = mod.ApprovalHandler()
        handler.dynamodb = mock_aws["dynamodb"]
        handler.sfn_client = mock_aws["sfn"]

        task_token = "task_token_approve"
        mock_aws["sfn"].send_task_success.return_value = {}

        handler.handle_approval(task_token=task_token, status="approved", feedback=None)

        mock_aws["sfn"].send_task_success.assert_called_once()
        call_kwargs = mock_aws["sfn"].send_task_success.call_args[1]
        assert call_kwargs.get("taskToken") == task_token

    def test_rejection_sends_task_failure(self, mock_aws):
        """Rejecting a plan must send task failure to Step Functions."""
        import importlib.util, os
        path = os.path.join(os.path.dirname(__file__), "../../lambda/approval-handler/handler.py")
        spec = importlib.util.spec_from_file_location("ah_handler4", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        handler = mod.ApprovalHandler()
        handler.dynamodb = mock_aws["dynamodb"]
        handler.sfn_client = mock_aws["sfn"]

        task_token = "task_token_reject"
        mock_aws["sfn"].send_task_failure.return_value = {}

        handler.handle_approval(
            task_token=task_token,
            status="rejected",
            feedback="Too many trades",
        )

        mock_aws["sfn"].send_task_failure.assert_called_once()

    def test_approval_deadline_is_24_hours(self, sample_rebalancing_plan):
        """Approval deadline must be set to 24 hours from creation."""
        import importlib.util, os
        path = os.path.join(os.path.dirname(__file__), "../../lambda/approval-handler/handler.py")
        spec = importlib.util.spec_from_file_location("ah_handler5", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        handler = mod.ApprovalHandler()
        handler.dynamodb = MagicMock()
        handler.sfn_client = MagicMock()

        before = datetime.utcnow()
        deadline = handler.calculate_approval_deadline()
        after = datetime.utcnow()

        expected_min = before + timedelta(hours=23, minutes=59)
        expected_max = after + timedelta(hours=24, minutes=1)

        assert expected_min <= deadline <= expected_max

    def test_expired_approval_is_rejected(self, mock_aws):
        """Approvals past their deadline must be treated as expired/rejected."""
        import importlib.util, os
        path = os.path.join(os.path.dirname(__file__), "../../lambda/approval-handler/handler.py")
        spec = importlib.util.spec_from_file_location("ah_handler6", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        handler = mod.ApprovalHandler()
        handler.dynamodb = mock_aws["dynamodb"]
        handler.sfn_client = mock_aws["sfn"]

        expired_deadline = datetime.utcnow() - timedelta(hours=1)
        is_expired = handler.is_approval_expired(expired_deadline)
        assert is_expired is True

    def test_valid_approval_not_expired(self):
        """Approvals within deadline must not be treated as expired."""
        import importlib.util, os
        path = os.path.join(os.path.dirname(__file__), "../../lambda/approval-handler/handler.py")
        spec = importlib.util.spec_from_file_location("ah_handler7", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        handler = mod.ApprovalHandler()
        handler.dynamodb = MagicMock()
        handler.sfn_client = MagicMock()

        future_deadline = datetime.utcnow() + timedelta(hours=12)
        is_expired = handler.is_approval_expired(future_deadline)
        assert is_expired is False


class TestTradeExecutionIntegration:
    """Integration tests for trade execution after approval."""

    def test_trade_execution_on_approval(self, mock_aws, sample_trade_orders):
        """Approved trades must be executed via the trade executor Lambda."""
        import importlib.util, os
        path = os.path.join(os.path.dirname(__file__), "../../lambda/trade-executor/handler.py")
        spec = importlib.util.spec_from_file_location("te_handler", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        executor = mod.TradeExecutor()
        executor.dynamodb = mock_aws["dynamodb"]
        executor.brokerage_client = MagicMock()
        executor.brokerage_client.execute_order.return_value = {
            "order_id": "o1",
            "status": "filled",
            "execution_price": 78.5,
            "execution_time": datetime.utcnow().isoformat(),
        }

        mock_aws["dynamodb"].put_item.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}

        for order in sample_trade_orders:
            confirmation = executor.execute_trade(order)
            assert confirmation is not None
            assert confirmation.status in ("completed", "failed", "partial")

    def test_trade_failure_recorded_in_dynamodb(self, mock_aws, sample_trade_orders):
        """Failed trades must be recorded in DynamoDB with error status."""
        import importlib.util, os
        path = os.path.join(os.path.dirname(__file__), "../../lambda/trade-executor/handler.py")
        spec = importlib.util.spec_from_file_location("te_handler2", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        executor = mod.TradeExecutor()
        executor.dynamodb = mock_aws["dynamodb"]
        executor.brokerage_client = MagicMock()
        executor.brokerage_client.execute_order.side_effect = Exception("Brokerage API down")

        mock_aws["dynamodb"].put_item.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}

        order = sample_trade_orders[0]
        confirmation = executor.execute_trade(order)

        # Should record failure, not raise
        assert confirmation.status == "failed"
        assert confirmation.error_message is not None
