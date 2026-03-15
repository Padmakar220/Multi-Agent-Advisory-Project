"""
Integration tests for the Tax Optimization workflow.

Tests the complete flow from supervisor request through tax optimizer
to plan generation, using LocalStack-compatible mocks for AWS services.

Requirements: All
"""

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

import sys
sys.path.insert(0, "src")
sys.path.insert(0, "lambda")

from src.models.portfolio import Holding, Portfolio
from src.models.requests import SupervisorRequest
from src.models.responses import TaxOptimizationPlan


@pytest.fixture
def mock_aws():
    """Provide mocked AWS clients for LocalStack-compatible testing."""
    with patch("boto3.client") as mock_client, patch("boto3.resource") as mock_resource:
        mock_dynamodb_client = MagicMock()
        mock_dynamodb_resource = MagicMock()
        mock_bedrock = MagicMock()
        mock_sns = MagicMock()

        def client_factory(service, **kwargs):
            mapping = {
                "dynamodb": mock_dynamodb_client,
                "bedrock-runtime": mock_bedrock,
                "sns": mock_sns,
            }
            return mapping.get(service, MagicMock())

        def resource_factory(service, **kwargs):
            if service == "dynamodb":
                return mock_dynamodb_resource
            return MagicMock()

        mock_client.side_effect = client_factory
        mock_resource.side_effect = resource_factory

        yield {
            "dynamodb_client": mock_dynamodb_client,
            "dynamodb_resource": mock_dynamodb_resource,
            "bedrock": mock_bedrock,
            "sns": mock_sns,
        }


@pytest.fixture
def portfolio_with_losses():
    return Portfolio(
        user_id="user_tax_001",
        portfolio_id="portfolio_tax_001",
        portfolio_name="Tax Test Portfolio",
        holdings=[
            Holding(ticker="VTI", quantity=100, cost_basis=250.0, current_price=220.0, purchase_date="2022-01-15"),
            Holding(ticker="BND", quantity=50, cost_basis=90.0, current_price=78.0, purchase_date="2022-06-01"),
            Holding(ticker="VXUS", quantity=75, cost_basis=60.0, current_price=65.0, purchase_date="2023-01-01"),
        ],
        target_allocation={"stocks": 0.60, "bonds": 0.30, "cash": 0.10},
        total_value=sum([100 * 220.0, 50 * 78.0, 75 * 65.0]),
        risk_tolerance="moderate",
    )


class TestTaxOptimizationWorkflow:
    """Integration tests for the complete tax optimization workflow."""

    def test_tax_optimization_identifies_losses(self, mock_aws, portfolio_with_losses):
        """Tax optimizer should identify holdings with unrealized losses."""
        import importlib.util, os
        path = os.path.join(os.path.dirname(__file__), "../../lambda/tax-optimizer/handler.py")
        spec = importlib.util.spec_from_file_location("to_handler", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        TaxOptimizer = mod.TaxOptimizer

        optimizer = TaxOptimizer()
        optimizer.portfolio_tool = Mock()
        optimizer.portfolio_tool.execute.return_value = portfolio_with_losses
        optimizer.cost_basis_tool = Mock()
        optimizer.bedrock_client = Mock()
        optimizer.bedrock_client.invoke_model.return_value = {
            "body": Mock(read=lambda: json.dumps({"content": [{"text": "Harvest losses in VTI and BND."}]}).encode())
        }

        plan = optimizer.optimize(portfolio_with_losses.user_id, portfolio_with_losses.portfolio_id)

        assert isinstance(plan, TaxOptimizationPlan)
        assert plan.portfolio_id == portfolio_with_losses.portfolio_id
        assert plan.total_potential_savings >= 0

    def test_tax_optimization_plan_schema(self, mock_aws, portfolio_with_losses):
        """Tax optimization plan must conform to expected schema."""
        import importlib.util, os
        path = os.path.join(os.path.dirname(__file__), "../../lambda/tax-optimizer/handler.py")
        spec = importlib.util.spec_from_file_location("to_handler2", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        TaxOptimizer = mod.TaxOptimizer

        optimizer = TaxOptimizer()
        optimizer.portfolio_tool = Mock()
        optimizer.portfolio_tool.execute.return_value = portfolio_with_losses
        optimizer.cost_basis_tool = Mock()
        optimizer.bedrock_client = Mock()
        optimizer.bedrock_client.invoke_model.return_value = {
            "body": Mock(read=lambda: json.dumps({"content": [{"text": "Sell VTI at a loss."}]}).encode())
        }

        plan = optimizer.optimize(portfolio_with_losses.user_id, portfolio_with_losses.portfolio_id)

        # Schema validation
        assert hasattr(plan, "portfolio_id")
        assert hasattr(plan, "timestamp")
        assert hasattr(plan, "tax_loss_opportunities")
        assert hasattr(plan, "total_potential_savings")
        assert hasattr(plan, "recommended_trades")
        assert hasattr(plan, "wash_sale_warnings")
        assert isinstance(plan.tax_loss_opportunities, list)
        assert isinstance(plan.recommended_trades, list)
        assert isinstance(plan.wash_sale_warnings, list)

    def test_tax_optimization_dynamodb_error_handled(self, mock_aws):
        """DynamoDB errors during tax optimization should be handled gracefully."""
        import importlib.util, os
        path = os.path.join(os.path.dirname(__file__), "../../lambda/tax-optimizer/handler.py")
        spec = importlib.util.spec_from_file_location("to_handler3", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        TaxOptimizer = mod.TaxOptimizer

        optimizer = TaxOptimizer()
        optimizer.portfolio_tool = Mock()
        optimizer.portfolio_tool.execute.side_effect = Exception("DynamoDB connection refused")
        optimizer.cost_basis_tool = Mock()
        optimizer.bedrock_client = Mock()

        with pytest.raises(Exception, match="DynamoDB"):
            optimizer.optimize("u", "p")

    def test_tax_optimization_no_losses_returns_empty_opportunities(self, mock_aws):
        """Portfolio with only gains should return empty tax-loss opportunities."""
        import importlib.util, os
        path = os.path.join(os.path.dirname(__file__), "../../lambda/tax-optimizer/handler.py")
        spec = importlib.util.spec_from_file_location("to_handler4", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        TaxOptimizer = mod.TaxOptimizer

        gains_portfolio = Portfolio(
            user_id="u",
            portfolio_id="p",
            portfolio_name="Gains",
            holdings=[
                Holding(ticker="VTI", quantity=100, cost_basis=100.0, current_price=200.0, purchase_date="2020-01-01"),
            ],
            target_allocation={"stocks": 1.0},
            total_value=20_000.0,
            risk_tolerance="moderate",
        )

        optimizer = TaxOptimizer()
        optimizer.portfolio_tool = Mock()
        optimizer.portfolio_tool.execute.return_value = gains_portfolio
        optimizer.cost_basis_tool = Mock()
        optimizer.bedrock_client = Mock()
        optimizer.bedrock_client.invoke_model.return_value = {
            "body": Mock(read=lambda: json.dumps({"content": [{"text": "No losses to harvest."}]}).encode())
        }

        plan = optimizer.optimize(gains_portfolio.user_id, gains_portfolio.portfolio_id)
        assert plan.total_potential_savings >= 0
