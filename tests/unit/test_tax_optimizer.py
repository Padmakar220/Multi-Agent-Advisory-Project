"""Unit tests for Tax Optimizer Agent."""

import json
import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
from decimal import Decimal

from src.models.portfolio import Portfolio, Holding
from src.models.responses import (
    TaxOptimizationPlan,
    TaxLossOpportunity,
    TaxOptimizedTrade,
    WashSaleWarning,
    CostBasisInfo,
)


# Import the handler module
import sys
import os
import importlib.util

handler_path = os.path.join(os.path.dirname(__file__), '../../lambda/tax-optimizer/handler.py')
spec = importlib.util.spec_from_file_location("tax_optimizer_handler", handler_path)
handler_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler_module)

TaxOptimizer = handler_module.TaxOptimizer
lambda_handler = handler_module.lambda_handler


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def optimizer():
    """Create a TaxOptimizer instance."""
    return TaxOptimizer(tax_rate=0.24)


@pytest.fixture
def sample_portfolio():
    """Create a sample portfolio with mixed gains and losses."""
    return Portfolio(
        user_id="user_123",
        portfolio_id="portfolio_456",
        portfolio_name="Test Portfolio",
        target_allocation={"stocks": 0.6, "bonds": 0.4},
        holdings=[
            Holding(
                ticker="VTI",
                quantity=100,
                cost_basis=200.0,
                current_price=220.0,  # Gain
                purchase_date="2023-01-15"
            ),
            Holding(
                ticker="BND",
                quantity=50,
                cost_basis=100.0,
                current_price=90.0,  # Loss
                purchase_date="2023-06-01"
            ),
            Holding(
                ticker="VXUS",
                quantity=75,
                cost_basis=150.0,
                current_price=140.0,  # Loss
                purchase_date="2023-03-15"
            ),
        ],
        total_value=35000.0,
        risk_tolerance="moderate"
    )


@pytest.fixture
def cost_basis_data():
    """Create sample cost basis data."""
    return {
        "VTI": CostBasisInfo(
            ticker="VTI",
            quantity=100,
            cost_per_share=200.0,
            purchase_date="2023-01-15"
        ),
        "BND": CostBasisInfo(
            ticker="BND",
            quantity=50,
            cost_per_share=100.0,
            purchase_date="2023-06-01"
        ),
        "VXUS": CostBasisInfo(
            ticker="VXUS",
            quantity=75,
            cost_per_share=150.0,
            purchase_date="2023-03-15"
        ),
    }


# ============================================================================
# Test Classes
# ============================================================================

class TestTaxOptimizerUnrealizedLossIdentification:
    """Tests for unrealized loss identification."""
    
    def test_identify_tax_loss_opportunities_with_losses(self, optimizer, sample_portfolio, cost_basis_data):
        """Test identification of securities with unrealized losses."""
        opportunities = optimizer._identify_tax_loss_opportunities(sample_portfolio, cost_basis_data)
        
        assert isinstance(opportunities, list)
        assert len(opportunities) == 2  # BND and VXUS have losses
        
        # Check BND loss
        bnd_opp = next((o for o in opportunities if o.ticker == "BND"), None)
        assert bnd_opp is not None
        assert bnd_opp.unrealized_loss == -500.0  # (90 - 100) * 50
        assert bnd_opp.potential_tax_savings == 120.0  # 500 * 0.24
        
        # Check VXUS loss
        vxus_opp = next((o for o in opportunities if o.ticker == "VXUS"), None)
        assert vxus_opp is not None
        assert vxus_opp.unrealized_loss == -750.0  # (140 - 150) * 75
        assert vxus_opp.potential_tax_savings == 180.0  # 750 * 0.24
    
    def test_identify_tax_loss_opportunities_no_losses(self, optimizer):
        """Test when portfolio has no losses."""
        portfolio = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Gains Only",
            target_allocation={"stocks": 1.0},
            holdings=[
                Holding(
                    ticker="VTI",
                    quantity=100,
                    cost_basis=200.0,
                    current_price=250.0,  # Gain
                    purchase_date="2023-01-15"
                ),
            ],
            total_value=25000.0
        )
        
        cost_basis_data = {
            "VTI": CostBasisInfo(
                ticker="VTI",
                quantity=100,
                cost_per_share=200.0,
                purchase_date="2023-01-15"
            ),
        }
        
        opportunities = optimizer._identify_tax_loss_opportunities(portfolio, cost_basis_data)
        
        assert len(opportunities) == 0
    
    def test_identify_tax_loss_opportunities_empty_portfolio(self, optimizer):
        """Test with empty portfolio."""
        portfolio = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Empty",
            target_allocation={"stocks": 1.0},
            holdings=[],
            total_value=0.0
        )
        
        opportunities = optimizer._identify_tax_loss_opportunities(portfolio, {})
        
        assert len(opportunities) == 0


class TestTaxOptimizerTaxSavingsCalculation:
    """Tests for tax savings calculation."""
    
    def test_calculate_total_tax_savings(self, optimizer):
        """Test total tax savings calculation."""
        opportunities = [
            TaxLossOpportunity(
                ticker="BND",
                quantity=50,
                cost_basis=100.0,
                current_value=4500.0,
                unrealized_loss=-500.0,
                potential_tax_savings=120.0
            ),
            TaxLossOpportunity(
                ticker="VXUS",
                quantity=75,
                cost_basis=150.0,
                current_value=10500.0,
                unrealized_loss=-750.0,
                potential_tax_savings=180.0
            ),
        ]
        
        total_savings = optimizer._calculate_total_tax_savings(opportunities)
        
        assert total_savings == 300.0  # 120 + 180
    
    def test_calculate_total_tax_savings_empty(self, optimizer):
        """Test total tax savings with no opportunities."""
        total_savings = optimizer._calculate_total_tax_savings([])
        
        assert total_savings == 0.0


class TestTaxOptimizerReplacementSecurities:
    """Tests for finding replacement securities."""
    
    def test_find_replacement_securities(self, optimizer, sample_portfolio):
        """Test finding replacement securities."""
        opportunities = [
            TaxLossOpportunity(
                ticker="BND",
                quantity=50,
                cost_basis=100.0,
                current_value=4500.0,
                unrealized_loss=-500.0,
                potential_tax_savings=120.0
            ),
        ]
        
        trades = optimizer._find_replacement_securities(opportunities, sample_portfolio)
        
        # Should have sell and buy trades
        assert len(trades) >= 2
        
        # Check sell trade
        sell_trades = [t for t in trades if t.action == "sell"]
        assert len(sell_trades) == 1
        assert sell_trades[0].ticker == "BND"
        assert sell_trades[0].quantity == 50
        
        # Check buy trade
        buy_trades = [t for t in trades if t.action == "buy"]
        assert len(buy_trades) == 1
        assert buy_trades[0].action == "buy"
    
    def test_find_similar_security(self, optimizer, sample_portfolio):
        """Test finding similar security."""
        # BND should have replacement options
        replacement = optimizer._find_similar_security("bonds", "BND", sample_portfolio)
        
        assert replacement is not None
        assert replacement in ["VBTLX", "FXNAX"]


class TestTaxOptimizerWashSaleRules:
    """Tests for wash sale rule checking."""
    
    def test_check_wash_sale_rules(self, optimizer, sample_portfolio):
        """Test wash sale rule checking."""
        trades = [
            TaxOptimizedTrade(
                action="sell",
                ticker="BND",
                quantity=50,
                reason="Tax loss harvesting",
                tax_impact=120.0
            ),
            TaxOptimizedTrade(
                action="buy",
                ticker="VBTLX",
                quantity=50,
                reason="Replacement",
                tax_impact=0.0
            ),
        ]
        
        warnings = optimizer._check_wash_sale_rules(sample_portfolio, trades)
        
        # Should have at least one warning for potential wash sale
        assert isinstance(warnings, list)
        assert all(isinstance(w, WashSaleWarning) for w in warnings)
    
    def test_check_wash_sale_rules_no_replacement(self, optimizer, sample_portfolio):
        """Test wash sale rules when no replacement is purchased."""
        trades = [
            TaxOptimizedTrade(
                action="sell",
                ticker="BND",
                quantity=50,
                reason="Tax loss harvesting",
                tax_impact=120.0
            ),
        ]
        
        warnings = optimizer._check_wash_sale_rules(sample_portfolio, trades)
        
        # Should have no warnings if no replacement
        assert len(warnings) == 0


class TestTaxOptimizerBedrockIntegration:
    """Tests for Bedrock integration."""
    
    def test_build_tax_optimization_prompt(self, optimizer, sample_portfolio):
        """Test prompt building for Bedrock."""
        opportunities = [
            TaxLossOpportunity(
                ticker="BND",
                quantity=50,
                cost_basis=100.0,
                current_value=4500.0,
                unrealized_loss=-500.0,
                potential_tax_savings=120.0
            ),
        ]
        
        trades = [
            TaxOptimizedTrade(
                action="sell",
                ticker="BND",
                quantity=50,
                reason="Tax loss harvesting",
                tax_impact=120.0
            ),
        ]
        
        prompt = optimizer._build_tax_optimization_prompt(
            sample_portfolio,
            opportunities,
            trades,
            []
        )
        
        assert isinstance(prompt, str)
        assert "BND" in prompt
        assert "tax-loss harvesting" in prompt.lower()
        assert "recommended_trades" in prompt
    
    def test_parse_bedrock_trades_valid_json(self, optimizer):
        """Test parsing valid Bedrock response."""
        response = """{
            "recommended_trades": [
                {
                    "action": "sell",
                    "ticker": "BND",
                    "quantity": 50,
                    "reason": "Tax loss harvesting",
                    "tax_impact": 120.0
                },
                {
                    "action": "buy",
                    "ticker": "VBTLX",
                    "quantity": 50,
                    "reason": "Replacement",
                    "tax_impact": 0.0
                }
            ],
            "total_tax_savings": 120.0,
            "notes": "Recommended strategy"
        }"""
        
        fallback_trades = []
        trades = optimizer._parse_bedrock_trades(response, fallback_trades)
        
        assert len(trades) == 2
        assert trades[0].action == "sell"
        assert trades[0].ticker == "BND"
        assert trades[1].action == "buy"
        assert trades[1].ticker == "VBTLX"
    
    def test_parse_bedrock_trades_invalid_json(self, optimizer):
        """Test parsing invalid Bedrock response."""
        response = "This is not JSON"
        
        fallback_trades = [
            TaxOptimizedTrade(
                action="sell",
                ticker="BND",
                quantity=50,
                reason="Fallback",
                tax_impact=120.0
            ),
        ]
        
        trades = optimizer._parse_bedrock_trades(response, fallback_trades)
        
        # Should return fallback trades
        assert trades == fallback_trades


class TestTaxOptimizerErrorHandling:
    """Tests for error handling."""
    
    def test_retrieve_portfolio_not_found(self, optimizer):
        """Test error when portfolio not found."""
        optimizer.portfolio_tool = Mock()
        optimizer.portfolio_tool.execute.side_effect = ValueError("Portfolio not found")
        
        with pytest.raises(ValueError):
            optimizer._retrieve_portfolio("user_123", "nonexistent")
    
    def test_retrieve_cost_basis_partial_failure(self, optimizer, sample_portfolio):
        """Test cost basis retrieval with partial failures."""
        optimizer.cost_basis_tool = Mock()
        optimizer.cost_basis_tool.execute.side_effect = [
            CostBasisInfo("VTI", 100, 200.0, "2023-01-15"),
            ValueError("Not found"),  # BND fails
            CostBasisInfo("VXUS", 75, 150.0, "2023-03-15"),
        ]
        
        cost_basis_data = optimizer._retrieve_cost_basis("user_123", "portfolio_456", sample_portfolio)
        
        # Should have 2 entries (VTI and VXUS), BND should use holding data
        assert "VTI" in cost_basis_data
        assert "VXUS" in cost_basis_data
        assert "BND" in cost_basis_data


class TestTaxOptimizerIntegration:
    """Integration tests for Tax Optimizer."""
    
    def test_optimize_complete_workflow(self, sample_portfolio):
        """Test complete tax optimization workflow."""
        optimizer = TaxOptimizer()
        
        # Mock dependencies
        optimizer.portfolio_tool = Mock()
        optimizer.portfolio_tool.execute.return_value = sample_portfolio
        
        optimizer.cost_basis_tool = Mock()
        optimizer.cost_basis_tool.execute.side_effect = [
            CostBasisInfo("VTI", 100, 200.0, "2023-01-15"),
            CostBasisInfo("BND", 50, 100.0, "2023-06-01"),
            CostBasisInfo("VXUS", 75, 150.0, "2023-03-15"),
        ]
        
        optimizer.bedrock_client = Mock()
        optimizer.bedrock_client.invoke_model.return_value = {
            "body": MagicMock(read=lambda: json.dumps({
                "content": [{
                    "text": json.dumps({
                        "recommended_trades": [
                            {
                                "action": "sell",
                                "ticker": "BND",
                                "quantity": 50,
                                "reason": "Tax loss harvesting",
                                "tax_impact": 120.0
                            }
                        ],
                        "total_tax_savings": 120.0,
                        "notes": "Recommended"
                    })
                }]
            }))
        }
        
        plan = optimizer.optimize("user_123", "portfolio_456")
        
        assert isinstance(plan, TaxOptimizationPlan)
        assert plan.portfolio_id == "portfolio_456"
        assert len(plan.tax_loss_opportunities) == 2
        assert plan.total_potential_savings > 0
        assert len(plan.recommended_trades) > 0


class TestLambdaHandler:
    """Tests for Lambda handler."""
    
    def test_lambda_handler_success(self):
        """Test successful Lambda handler invocation."""
        with patch.object(TaxOptimizer, 'optimize') as mock_optimize:
            mock_plan = Mock()
            mock_plan.portfolio_id = "portfolio_456"
            mock_plan.timestamp = "2024-01-15T10:00:00Z"
            mock_plan.tax_loss_opportunities = []
            mock_plan.total_potential_savings = 300.0
            mock_plan.recommended_trades = []
            mock_plan.wash_sale_warnings = []
            
            mock_optimize.return_value = mock_plan
            
            event = {
                "user_id": "user_123",
                "portfolio_id": "portfolio_456"
            }
            
            response = lambda_handler(event, None)
            
            assert response["statusCode"] == 200
            body = json.loads(response["body"])
            assert body["status"] == "success"
            assert body["portfolio_id"] == "portfolio_456"
            assert body["total_potential_savings"] == 300.0
    
    def test_lambda_handler_missing_parameters(self):
        """Test Lambda handler with missing parameters."""
        event = {"user_id": "user_123"}  # Missing portfolio_id
        
        response = lambda_handler(event, None)
        
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["status"] == "error"
        assert body["error_code"] == "VALIDATION_ERROR"
    
    def test_lambda_handler_portfolio_not_found(self):
        """Test Lambda handler when portfolio not found."""
        with patch.object(TaxOptimizer, 'optimize') as mock_optimize:
            mock_optimize.side_effect = ValueError("Portfolio not found")
            
            event = {
                "user_id": "user_123",
                "portfolio_id": "nonexistent"
            }
            
            response = lambda_handler(event, None)
            
            assert response["statusCode"] == 400
            body = json.loads(response["body"])
            assert body["status"] == "error"
    
    def test_lambda_handler_aws_error(self):
        """Test Lambda handler with AWS service error."""
        with patch.object(TaxOptimizer, 'optimize') as mock_optimize:
            from botocore.exceptions import ClientError
            
            error_response = {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}}
            mock_optimize.side_effect = ClientError(error_response, 'GetItem')
            
            event = {
                "user_id": "user_123",
                "portfolio_id": "portfolio_456"
            }
            
            response = lambda_handler(event, None)
            
            assert response["statusCode"] == 500
            body = json.loads(response["body"])
            assert body["status"] == "error"
            assert body["error_code"] == "AGENT_ERROR"
