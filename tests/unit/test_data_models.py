"""Unit tests for data models."""

import pytest
from datetime import datetime
from decimal import Decimal

from src.models.portfolio import Holding, Portfolio, Transaction, AgentState
from src.models.requests import (
    SupervisorRequest,
    AnalysisRequest,
    TaxOptimizationRequest,
    RebalancingRequest,
    RebalancingConstraints,
    Subtask,
    CompletedTask
)
from src.models.responses import (
    PerformanceMetrics,
    RiskMetrics,
    AllocationDrift,
    MarketInsight,
    AnalysisReport,
    TaxLossOpportunity,
    TaxOptimizedTrade,
    WashSaleWarning,
    TaxOptimizationPlan,
    TradeOrder,
    TransactionCosts,
    RiskImpact,
    RebalancingPlan,
    SupervisorResponse,
    ErrorResponse
)


class TestHolding:
    """Test Holding model."""
    
    def test_valid_holding(self):
        """Test creating a valid holding."""
        holding = Holding(
            ticker="AAPL",
            quantity=100,
            cost_basis=150.0,
            current_price=175.0,
            purchase_date="2023-01-15T00:00:00Z"
        )
        assert holding.ticker == "AAPL"
        assert holding.market_value == 17500.0
        assert holding.unrealized_gain_loss == 2500.0
    
    def test_holding_validation_negative_quantity(self):
        """Test that negative quantity raises error."""
        with pytest.raises(ValueError, match="Quantity must be non-negative"):
            Holding(
                ticker="AAPL",
                quantity=-10,
                cost_basis=150.0,
                current_price=175.0,
                purchase_date="2023-01-15T00:00:00Z"
            )
    
    def test_holding_validation_empty_ticker(self):
        """Test that empty ticker raises error."""
        with pytest.raises(ValueError, match="Ticker symbol cannot be empty"):
            Holding(
                ticker="",
                quantity=100,
                cost_basis=150.0,
                current_price=175.0,
                purchase_date="2023-01-15T00:00:00Z"
            )
    
    def test_holding_dynamodb_round_trip(self):
        """Test serialization to DynamoDB and back."""
        original = Holding(
            ticker="AAPL",
            quantity=100,
            cost_basis=150.0,
            current_price=175.0,
            purchase_date="2023-01-15T00:00:00Z"
        )
        
        # Convert to DynamoDB format
        ddb_item = original.to_dynamodb()
        assert isinstance(ddb_item["cost_basis"], Decimal)
        assert isinstance(ddb_item["current_price"], Decimal)
        
        # Convert back
        restored = Holding.from_dynamodb(ddb_item)
        assert restored.ticker == original.ticker
        assert restored.quantity == original.quantity
        assert restored.cost_basis == original.cost_basis
        assert restored.current_price == original.current_price


class TestPortfolio:
    """Test Portfolio model."""
    
    def test_valid_portfolio(self):
        """Test creating a valid portfolio."""
        portfolio = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Retirement",
            target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
            holdings=[],
            risk_tolerance="moderate"
        )
        assert portfolio.user_id == "user_123"
        assert portfolio.risk_tolerance == "moderate"
    
    def test_portfolio_validation_invalid_risk_tolerance(self):
        """Test that invalid risk tolerance raises error."""
        with pytest.raises(ValueError, match="Invalid risk tolerance"):
            Portfolio(
                user_id="user_123",
                portfolio_id="portfolio_456",
                portfolio_name="Retirement",
                target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
                risk_tolerance="extreme"
            )
    
    def test_portfolio_validation_allocation_sum(self):
        """Test that allocation must sum to 1.0."""
        with pytest.raises(ValueError, match="Target allocation must sum to 1.0"):
            Portfolio(
                user_id="user_123",
                portfolio_id="portfolio_456",
                portfolio_name="Retirement",
                target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.2}
            )
    
    def test_portfolio_dynamodb_round_trip(self):
        """Test serialization to DynamoDB and back."""
        holding = Holding(
            ticker="AAPL",
            quantity=100,
            cost_basis=150.0,
            current_price=175.0,
            purchase_date="2023-01-15T00:00:00Z"
        )
        
        original = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Retirement",
            target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
            holdings=[holding],
            total_value=17500.0,
            risk_tolerance="moderate"
        )
        
        # Convert to DynamoDB format
        ddb_item = original.to_dynamodb()
        assert isinstance(ddb_item["total_value"], Decimal)
        
        # Convert back
        restored = Portfolio.from_dynamodb(ddb_item)
        assert restored.user_id == original.user_id
        assert restored.portfolio_id == original.portfolio_id
        assert len(restored.holdings) == 1
        assert restored.holdings[0].ticker == "AAPL"


class TestTransaction:
    """Test Transaction model."""
    
    def test_valid_transaction(self):
        """Test creating a valid transaction."""
        transaction = Transaction(
            user_id="user_123",
            timestamp="2024-01-15T14:30:00Z",
            transaction_id="txn_789",
            portfolio_id="portfolio_456",
            action="buy",
            ticker="AAPL",
            quantity=10,
            price=175.0,
            commission=0.0
        )
        assert transaction.action == "buy"
        assert transaction.total_cost == 1750.0
    
    def test_transaction_validation_invalid_action(self):
        """Test that invalid action raises error."""
        with pytest.raises(ValueError, match="Action must be 'buy' or 'sell'"):
            Transaction(
                user_id="user_123",
                timestamp="2024-01-15T14:30:00Z",
                transaction_id="txn_789",
                portfolio_id="portfolio_456",
                action="hold",
                ticker="AAPL",
                quantity=10,
                price=175.0
            )
    
    def test_transaction_dynamodb_round_trip(self):
        """Test serialization to DynamoDB and back."""
        original = Transaction(
            user_id="user_123",
            timestamp="2024-01-15T14:30:00Z",
            transaction_id="txn_789",
            portfolio_id="portfolio_456",
            action="buy",
            ticker="AAPL",
            quantity=10,
            price=175.0,
            commission=1.0,
            total_cost=1751.0,
            execution_status="completed"
        )
        
        ddb_item = original.to_dynamodb()
        restored = Transaction.from_dynamodb(ddb_item)
        
        assert restored.user_id == original.user_id
        assert restored.action == original.action
        assert restored.quantity == original.quantity


class TestAgentState:
    """Test AgentState model."""
    
    def test_valid_agent_state(self):
        """Test creating a valid agent state."""
        state = AgentState(
            session_id="session_abc",
            user_id="user_123",
            agent_type="supervisor",
            state={"step": "analysis"}
        )
        assert state.session_id == "session_abc"
        assert state.ttl > 0
    
    def test_agent_state_dynamodb_round_trip(self):
        """Test serialization to DynamoDB and back."""
        original = AgentState(
            session_id="session_abc",
            user_id="user_123",
            agent_type="supervisor",
            state={"step": "analysis", "completed": ["task1"]}
        )
        
        ddb_item = original.to_dynamodb()
        restored = AgentState.from_dynamodb(ddb_item)
        
        assert restored.session_id == original.session_id
        assert restored.user_id == original.user_id
        assert restored.state == original.state


class TestAnalysisReport:
    """Test AnalysisReport model."""
    
    def test_valid_analysis_report(self):
        """Test creating a valid analysis report."""
        perf = PerformanceMetrics(
            total_return=0.15,
            annualized_return=0.12,
            sharpe_ratio=1.5,
            max_drawdown=-0.08
        )
        
        risk = RiskMetrics(
            portfolio_volatility=0.15,
            beta=1.1,
            var_95=-0.05,
            concentration_risk={"tech": 0.3}
        )
        
        drift = AllocationDrift(
            current_allocation={"stocks": 0.65, "bonds": 0.25, "cash": 0.1},
            target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
            drift_percentage={"stocks": 0.05, "bonds": -0.05, "cash": 0.0},
            rebalancing_needed=True
        )
        
        report = AnalysisReport(
            portfolio_id="portfolio_456",
            timestamp="2024-01-15T14:30:00Z",
            performance_metrics=perf,
            risk_metrics=risk,
            allocation_drift=drift,
            market_context=[],
            recommendations=["Consider rebalancing"]
        )
        
        assert report.portfolio_id == "portfolio_456"
        assert report.performance_metrics.total_return == 0.15
    
    def test_analysis_report_dynamodb_serialization(self):
        """Test DynamoDB serialization."""
        perf = PerformanceMetrics(
            total_return=0.15,
            annualized_return=0.12,
            sharpe_ratio=1.5,
            max_drawdown=-0.08
        )
        
        risk = RiskMetrics(
            portfolio_volatility=0.15,
            beta=1.1,
            var_95=-0.05,
            concentration_risk={"tech": 0.3}
        )
        
        drift = AllocationDrift(
            current_allocation={"stocks": 0.65, "bonds": 0.25, "cash": 0.1},
            target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
            drift_percentage={"stocks": 0.05, "bonds": -0.05, "cash": 0.0},
            rebalancing_needed=True
        )
        
        report = AnalysisReport(
            portfolio_id="portfolio_456",
            timestamp="2024-01-15T14:30:00Z",
            performance_metrics=perf,
            risk_metrics=risk,
            allocation_drift=drift,
            market_context=[],
            recommendations=["Consider rebalancing"]
        )
        
        ddb_item = report.to_dynamodb()
        assert isinstance(ddb_item["performance_metrics"]["total_return"], Decimal)
        assert ddb_item["portfolio_id"] == "portfolio_456"


class TestTaxOptimizationPlan:
    """Test TaxOptimizationPlan model."""
    
    def test_valid_tax_optimization_plan(self):
        """Test creating a valid tax optimization plan."""
        opportunity = TaxLossOpportunity(
            ticker="AAPL",
            quantity=50,
            cost_basis=180.0,
            current_value=150.0,
            unrealized_loss=-1500.0,
            potential_tax_savings=450.0
        )
        
        trade = TaxOptimizedTrade(
            action="sell",
            ticker="AAPL",
            quantity=50,
            reason="Tax loss harvesting",
            tax_impact=-450.0
        )
        
        plan = TaxOptimizationPlan(
            portfolio_id="portfolio_456",
            timestamp="2024-01-15T14:30:00Z",
            tax_loss_opportunities=[opportunity],
            total_potential_savings=450.0,
            recommended_trades=[trade]
        )
        
        assert plan.total_potential_savings == 450.0
        assert len(plan.tax_loss_opportunities) == 1
    
    def test_tax_loss_opportunity_validation(self):
        """Test that unrealized loss must be negative."""
        with pytest.raises(ValueError, match="Unrealized loss must be negative"):
            TaxLossOpportunity(
                ticker="AAPL",
                quantity=50,
                cost_basis=150.0,
                current_value=180.0,
                unrealized_loss=1500.0,
                potential_tax_savings=0.0
            )


class TestRebalancingPlan:
    """Test RebalancingPlan model."""
    
    def test_valid_rebalancing_plan(self):
        """Test creating a valid rebalancing plan."""
        order = TradeOrder(
            order_id="order_123",
            action="buy",
            ticker="VTI",
            quantity=10,
            order_type="market",
            estimated_price=220.0,
            estimated_cost=2200.0
        )
        
        costs = TransactionCosts(
            total_commission=0.0,
            estimated_slippage=5.0,
            total_cost=5.0
        )
        
        risk = RiskImpact(
            current_risk_score=0.15,
            projected_risk_score=0.14,
            risk_change=-0.01,
            risk_assessment="reduced"
        )
        
        plan = RebalancingPlan(
            portfolio_id="portfolio_456",
            timestamp="2024-01-15T14:30:00Z",
            trade_orders=[order],
            expected_costs=costs,
            projected_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
            risk_impact=risk
        )
        
        assert len(plan.trade_orders) == 1
        assert plan.risk_impact.risk_assessment == "reduced"
    
    def test_rebalancing_plan_allocation_validation(self):
        """Test that projected allocation must sum to 1.0."""
        order = TradeOrder(
            order_id="order_123",
            action="buy",
            ticker="VTI",
            quantity=10,
            order_type="market",
            estimated_price=220.0,
            estimated_cost=2200.0
        )
        
        costs = TransactionCosts(
            total_commission=0.0,
            estimated_slippage=5.0,
            total_cost=5.0
        )
        
        risk = RiskImpact(
            current_risk_score=0.15,
            projected_risk_score=0.14,
            risk_change=-0.01,
            risk_assessment="reduced"
        )
        
        with pytest.raises(ValueError, match="Projected allocation must sum to 1.0"):
            RebalancingPlan(
                portfolio_id="portfolio_456",
                timestamp="2024-01-15T14:30:00Z",
                trade_orders=[order],
                expected_costs=costs,
                projected_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.2},
                risk_impact=risk
            )


class TestErrorResponse:
    """Test ErrorResponse model."""
    
    def test_valid_error_response(self):
        """Test creating a valid error response."""
        error = ErrorResponse(
            error_code="VALIDATION_ERROR",
            error_message="Invalid input",
            error_details={"field": "quantity", "issue": "negative value"},
            recovery_suggestions=["Provide a positive quantity"],
            support_reference="ERR-12345"
        )
        
        assert error.error_code == "VALIDATION_ERROR"
        assert len(error.recovery_suggestions) == 1
    
    def test_error_response_validation_invalid_code(self):
        """Test that invalid error code raises error."""
        with pytest.raises(ValueError, match="Invalid error code"):
            ErrorResponse(
                error_code="UNKNOWN_ERROR",
                error_message="Something went wrong",
                error_details={},
                recovery_suggestions=[],
                support_reference="ERR-12345"
            )


class TestEdgeCases:
    """Test edge cases for data models."""
    
    def test_empty_portfolio(self):
        """Test portfolio with no holdings."""
        portfolio = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Empty Portfolio",
            target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
            holdings=[],
            total_value=0.0
        )
        assert portfolio.total_value == 0.0
        assert len(portfolio.holdings) == 0
    
    def test_zero_quantity_holding(self):
        """Test holding with zero quantity."""
        holding = Holding(
            ticker="AAPL",
            quantity=0,
            cost_basis=150.0,
            current_price=175.0,
            purchase_date="2023-01-15T00:00:00Z"
        )
        assert holding.market_value == 0.0
    
    def test_allocation_drift_no_drift(self):
        """Test allocation drift when allocations match."""
        drift = AllocationDrift(
            current_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
            target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
            drift_percentage={"stocks": 0.0, "bonds": 0.0, "cash": 0.0},
            rebalancing_needed=False
        )
        assert not drift.rebalancing_needed


class TestEdgeCases:
    """Test edge cases for data models."""
    
    def test_empty_portfolio(self):
        """Test portfolio with no holdings."""
        portfolio = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Empty Portfolio",
            target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
            holdings=[],
            total_value=0.0
        )
        assert portfolio.total_value == 0.0
        assert len(portfolio.holdings) == 0
    
    def test_zero_quantity_holding(self):
        """Test holding with zero quantity."""
        holding = Holding(
            ticker="AAPL",
            quantity=0,
            cost_basis=150.0,
            current_price=175.0,
            purchase_date="2023-01-15T00:00:00Z"
        )
        assert holding.market_value == 0.0
    
    def test_allocation_drift_no_drift(self):
        """Test allocation drift when allocations match."""
        drift = AllocationDrift(
            current_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
            target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
            drift_percentage={"stocks": 0.0, "bonds": 0.0, "cash": 0.0},
            rebalancing_needed=False
        )
        assert not drift.rebalancing_needed
    
    def test_holding_negative_cost_basis(self):
        """Test that negative cost basis raises error."""
        with pytest.raises(ValueError, match="Cost basis must be non-negative"):
            Holding(
                ticker="AAPL",
                quantity=100,
                cost_basis=-150.0,
                current_price=175.0,
                purchase_date="2023-01-15T00:00:00Z"
            )
    
    def test_holding_negative_current_price(self):
        """Test that negative current price raises error."""
        with pytest.raises(ValueError, match="Current price must be non-negative"):
            Holding(
                ticker="AAPL",
                quantity=100,
                cost_basis=150.0,
                current_price=-175.0,
                purchase_date="2023-01-15T00:00:00Z"
            )
    
    def test_portfolio_empty_user_id(self):
        """Test that empty user ID raises error."""
        with pytest.raises(ValueError, match="User ID cannot be empty"):
            Portfolio(
                user_id="",
                portfolio_id="portfolio_456",
                portfolio_name="Test",
                target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1}
            )
    
    def test_portfolio_empty_portfolio_id(self):
        """Test that empty portfolio ID raises error."""
        with pytest.raises(ValueError, match="Portfolio ID cannot be empty"):
            Portfolio(
                user_id="user_123",
                portfolio_id="",
                portfolio_name="Test",
                target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1}
            )
    
    def test_transaction_negative_price(self):
        """Test that negative price raises error."""
        with pytest.raises(ValueError, match="Price must be non-negative"):
            Transaction(
                user_id="user_123",
                timestamp="2024-01-15T14:30:00Z",
                transaction_id="txn_789",
                portfolio_id="portfolio_456",
                action="buy",
                ticker="AAPL",
                quantity=10,
                price=-175.0
            )
    
    def test_transaction_zero_quantity(self):
        """Test that zero quantity raises error."""
        with pytest.raises(ValueError, match="Quantity must be positive"):
            Transaction(
                user_id="user_123",
                timestamp="2024-01-15T14:30:00Z",
                transaction_id="txn_789",
                portfolio_id="portfolio_456",
                action="buy",
                ticker="AAPL",
                quantity=0,
                price=175.0
            )
    
    def test_transaction_invalid_status(self):
        """Test that invalid execution status raises error."""
        with pytest.raises(ValueError, match="Invalid execution status"):
            Transaction(
                user_id="user_123",
                timestamp="2024-01-15T14:30:00Z",
                transaction_id="txn_789",
                portfolio_id="portfolio_456",
                action="buy",
                ticker="AAPL",
                quantity=10,
                price=175.0,
                execution_status="unknown"
            )
    
    def test_agent_state_empty_session_id(self):
        """Test that empty session ID raises error."""
        with pytest.raises(ValueError, match="Session ID cannot be empty"):
            AgentState(
                session_id="",
                user_id="user_123",
                agent_type="supervisor",
                state={"step": "analysis"}
            )
    
    def test_agent_state_empty_user_id(self):
        """Test that empty user ID raises error."""
        with pytest.raises(ValueError, match="User ID cannot be empty"):
            AgentState(
                session_id="session_abc",
                user_id="",
                agent_type="supervisor",
                state={"step": "analysis"}
            )
    
    def test_agent_state_empty_agent_type(self):
        """Test that empty agent type raises error."""
        with pytest.raises(ValueError, match="Agent type cannot be empty"):
            AgentState(
                session_id="session_abc",
                user_id="user_123",
                agent_type="",
                state={"step": "analysis"}
            )
    
    def test_performance_metrics_positive_max_drawdown(self):
        """Test that positive max drawdown raises error."""
        with pytest.raises(ValueError, match="Max drawdown must be non-positive"):
            PerformanceMetrics(
                total_return=0.15,
                annualized_return=0.12,
                sharpe_ratio=1.5,
                max_drawdown=0.08
            )
    
    def test_risk_metrics_negative_volatility(self):
        """Test that negative volatility raises error."""
        with pytest.raises(ValueError, match="Portfolio volatility must be non-negative"):
            RiskMetrics(
                portfolio_volatility=-0.15,
                beta=1.1,
                var_95=-0.05,
                concentration_risk={"tech": 0.3}
            )
    
    def test_risk_metrics_positive_var(self):
        """Test that positive VaR raises error."""
        with pytest.raises(ValueError, match="VaR should be non-positive"):
            RiskMetrics(
                portfolio_volatility=0.15,
                beta=1.1,
                var_95=0.05,
                concentration_risk={"tech": 0.3}
            )
    
    def test_allocation_drift_invalid_current_sum(self):
        """Test that current allocation not summing to 1.0 raises error."""
        with pytest.raises(ValueError, match="Current allocation must sum to 1.0"):
            AllocationDrift(
                current_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.2},
                target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
                drift_percentage={"stocks": 0.0, "bonds": 0.0, "cash": 0.1},
                rebalancing_needed=True
            )
    
    def test_allocation_drift_invalid_target_sum(self):
        """Test that target allocation not summing to 1.0 raises error."""
        with pytest.raises(ValueError, match="Target allocation must sum to 1.0"):
            AllocationDrift(
                current_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
                target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.2},
                drift_percentage={"stocks": 0.0, "bonds": 0.0, "cash": 0.0},
                rebalancing_needed=False
            )
    
    def test_market_insight_empty_title(self):
        """Test that empty title raises error."""
        with pytest.raises(ValueError, match="Title and content are required"):
            MarketInsight(
                title="",
                content="Some content",
                ticker="AAPL",
                sector="Technology",
                timestamp="2024-01-15T14:30:00Z",
                source="Bloomberg",
                relevance_score=0.8
            )
    
    def test_market_insight_empty_content(self):
        """Test that empty content raises error."""
        with pytest.raises(ValueError, match="Title and content are required"):
            MarketInsight(
                title="Market Update",
                content="",
                ticker="AAPL",
                sector="Technology",
                timestamp="2024-01-15T14:30:00Z",
                source="Bloomberg",
                relevance_score=0.8
            )
    
    def test_market_insight_invalid_relevance_score_high(self):
        """Test that relevance score > 1 raises error."""
        with pytest.raises(ValueError, match="Relevance score must be between 0 and 1"):
            MarketInsight(
                title="Market Update",
                content="Some content",
                ticker="AAPL",
                sector="Technology",
                timestamp="2024-01-15T14:30:00Z",
                source="Bloomberg",
                relevance_score=1.5
            )
    
    def test_market_insight_invalid_relevance_score_low(self):
        """Test that relevance score < 0 raises error."""
        with pytest.raises(ValueError, match="Relevance score must be between 0 and 1"):
            MarketInsight(
                title="Market Update",
                content="Some content",
                ticker="AAPL",
                sector="Technology",
                timestamp="2024-01-15T14:30:00Z",
                source="Bloomberg",
                relevance_score=-0.5
            )
    
    def test_analysis_report_empty_portfolio_id(self):
        """Test that empty portfolio ID raises error."""
        perf = PerformanceMetrics(
            total_return=0.15,
            annualized_return=0.12,
            sharpe_ratio=1.5,
            max_drawdown=-0.08
        )
        
        risk = RiskMetrics(
            portfolio_volatility=0.15,
            beta=1.1,
            var_95=-0.05,
            concentration_risk={"tech": 0.3}
        )
        
        drift = AllocationDrift(
            current_allocation={"stocks": 0.65, "bonds": 0.25, "cash": 0.1},
            target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
            drift_percentage={"stocks": 0.05, "bonds": -0.05, "cash": 0.0},
            rebalancing_needed=True
        )
        
        with pytest.raises(ValueError, match="Portfolio ID cannot be empty"):
            AnalysisReport(
                portfolio_id="",
                timestamp="2024-01-15T14:30:00Z",
                performance_metrics=perf,
                risk_metrics=risk,
                allocation_drift=drift,
                market_context=[],
                recommendations=[]
            )
    
    def test_tax_loss_opportunity_empty_ticker(self):
        """Test that empty ticker raises error."""
        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            TaxLossOpportunity(
                ticker="",
                quantity=50,
                cost_basis=180.0,
                current_value=150.0,
                unrealized_loss=-1500.0,
                potential_tax_savings=450.0
            )
    
    def test_tax_loss_opportunity_zero_quantity(self):
        """Test that zero quantity raises error."""
        with pytest.raises(ValueError, match="Quantity must be positive"):
            TaxLossOpportunity(
                ticker="AAPL",
                quantity=0,
                cost_basis=180.0,
                current_value=150.0,
                unrealized_loss=-1500.0,
                potential_tax_savings=450.0
            )
    
    def test_tax_loss_opportunity_negative_savings(self):
        """Test that negative potential tax savings raises error."""
        with pytest.raises(ValueError, match="Potential tax savings must be non-negative"):
            TaxLossOpportunity(
                ticker="AAPL",
                quantity=50,
                cost_basis=180.0,
                current_value=150.0,
                unrealized_loss=-1500.0,
                potential_tax_savings=-450.0
            )
    
    def test_tax_optimized_trade_invalid_action(self):
        """Test that invalid action raises error."""
        with pytest.raises(ValueError, match="Action must be 'sell' or 'buy'"):
            TaxOptimizedTrade(
                action="hold",
                ticker="AAPL",
                quantity=50,
                reason="Tax loss harvesting",
                tax_impact=-450.0
            )
    
    def test_tax_optimized_trade_empty_ticker(self):
        """Test that empty ticker raises error."""
        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            TaxOptimizedTrade(
                action="sell",
                ticker="",
                quantity=50,
                reason="Tax loss harvesting",
                tax_impact=-450.0
            )
    
    def test_tax_optimized_trade_negative_quantity(self):
        """Test that negative quantity raises error."""
        with pytest.raises(ValueError, match="Quantity must be positive"):
            TaxOptimizedTrade(
                action="sell",
                ticker="AAPL",
                quantity=-50,
                reason="Tax loss harvesting",
                tax_impact=-450.0
            )
    
    def test_wash_sale_warning_negative_days(self):
        """Test that negative days between raises error."""
        with pytest.raises(ValueError, match="Days between must be non-negative"):
            WashSaleWarning(
                ticker="AAPL",
                sale_date="2024-01-15",
                purchase_date="2024-01-20",
                days_between=-5,
                warning_message="Potential wash sale"
            )
    
    def test_tax_optimization_plan_empty_portfolio_id(self):
        """Test that empty portfolio ID raises error."""
        with pytest.raises(ValueError, match="Portfolio ID cannot be empty"):
            TaxOptimizationPlan(
                portfolio_id="",
                timestamp="2024-01-15T14:30:00Z",
                tax_loss_opportunities=[],
                total_potential_savings=0.0,
                recommended_trades=[]
            )
    
    def test_tax_optimization_plan_negative_savings(self):
        """Test that negative total potential savings raises error."""
        with pytest.raises(ValueError, match="Total potential savings must be non-negative"):
            TaxOptimizationPlan(
                portfolio_id="portfolio_456",
                timestamp="2024-01-15T14:30:00Z",
                tax_loss_opportunities=[],
                total_potential_savings=-100.0,
                recommended_trades=[]
            )
    
    def test_trade_order_invalid_action(self):
        """Test that invalid action raises error."""
        with pytest.raises(ValueError, match="Action must be 'buy', 'sell', or 'hold'"):
            TradeOrder(
                order_id="order_123",
                action="cancel",
                ticker="VTI",
                quantity=10,
                order_type="market",
                estimated_price=220.0,
                estimated_cost=2200.0
            )
    
    def test_trade_order_empty_ticker(self):
        """Test that empty ticker raises error."""
        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            TradeOrder(
                order_id="order_123",
                action="buy",
                ticker="",
                quantity=10,
                order_type="market",
                estimated_price=220.0,
                estimated_cost=2200.0
            )
    
    def test_trade_order_negative_quantity(self):
        """Test that negative quantity raises error."""
        with pytest.raises(ValueError, match="Quantity must be non-negative"):
            TradeOrder(
                order_id="order_123",
                action="buy",
                ticker="VTI",
                quantity=-10,
                order_type="market",
                estimated_price=220.0,
                estimated_cost=2200.0
            )
    
    def test_trade_order_invalid_order_type(self):
        """Test that invalid order type raises error."""
        with pytest.raises(ValueError, match="Order type must be 'market' or 'limit'"):
            TradeOrder(
                order_id="order_123",
                action="buy",
                ticker="VTI",
                quantity=10,
                order_type="stop",
                estimated_price=220.0,
                estimated_cost=2200.0
            )
    
    def test_trade_order_negative_price(self):
        """Test that negative estimated price raises error."""
        with pytest.raises(ValueError, match="Estimated price must be non-negative"):
            TradeOrder(
                order_id="order_123",
                action="buy",
                ticker="VTI",
                quantity=10,
                order_type="market",
                estimated_price=-220.0,
                estimated_cost=2200.0
            )
    
    def test_transaction_costs_negative_commission(self):
        """Test that negative commission raises error."""
        with pytest.raises(ValueError, match="Total commission must be non-negative"):
            TransactionCosts(
                total_commission=-10.0,
                estimated_slippage=5.0,
                total_cost=5.0
            )
    
    def test_transaction_costs_negative_slippage(self):
        """Test that negative slippage raises error."""
        with pytest.raises(ValueError, match="Estimated slippage must be non-negative"):
            TransactionCosts(
                total_commission=0.0,
                estimated_slippage=-5.0,
                total_cost=5.0
            )
    
    def test_transaction_costs_negative_total(self):
        """Test that negative total cost raises error."""
        with pytest.raises(ValueError, match="Total cost must be non-negative"):
            TransactionCosts(
                total_commission=0.0,
                estimated_slippage=5.0,
                total_cost=-5.0
            )
    
    def test_risk_impact_negative_current_score(self):
        """Test that negative current risk score raises error."""
        with pytest.raises(ValueError, match="Current risk score must be non-negative"):
            RiskImpact(
                current_risk_score=-0.15,
                projected_risk_score=0.14,
                risk_change=-0.01,
                risk_assessment="reduced"
            )
    
    def test_risk_impact_negative_projected_score(self):
        """Test that negative projected risk score raises error."""
        with pytest.raises(ValueError, match="Projected risk score must be non-negative"):
            RiskImpact(
                current_risk_score=0.15,
                projected_risk_score=-0.14,
                risk_change=-0.01,
                risk_assessment="reduced"
            )
    
    def test_risk_impact_invalid_assessment(self):
        """Test that invalid risk assessment raises error."""
        with pytest.raises(ValueError, match="Invalid risk assessment"):
            RiskImpact(
                current_risk_score=0.15,
                projected_risk_score=0.14,
                risk_change=-0.01,
                risk_assessment="unknown"
            )
    
    def test_rebalancing_plan_empty_portfolio_id(self):
        """Test that empty portfolio ID raises error."""
        order = TradeOrder(
            order_id="order_123",
            action="buy",
            ticker="VTI",
            quantity=10,
            order_type="market",
            estimated_price=220.0,
            estimated_cost=2200.0
        )
        
        costs = TransactionCosts(
            total_commission=0.0,
            estimated_slippage=5.0,
            total_cost=5.0
        )
        
        risk = RiskImpact(
            current_risk_score=0.15,
            projected_risk_score=0.14,
            risk_change=-0.01,
            risk_assessment="reduced"
        )
        
        with pytest.raises(ValueError, match="Portfolio ID cannot be empty"):
            RebalancingPlan(
                portfolio_id="",
                timestamp="2024-01-15T14:30:00Z",
                trade_orders=[order],
                expected_costs=costs,
                projected_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
                risk_impact=risk
            )
    
    def test_supervisor_response_empty_session_id(self):
        """Test that empty session ID raises error."""
        with pytest.raises(ValueError, match="Session ID cannot be empty"):
            SupervisorResponse(
                session_id="",
                status="success",
                results={},
                requires_approval=False
            )
    
    def test_supervisor_response_invalid_status(self):
        """Test that invalid status raises error."""
        with pytest.raises(ValueError, match="Invalid status"):
            SupervisorResponse(
                session_id="session_123",
                status="unknown",
                results={},
                requires_approval=False
            )
    
    def test_supervisor_response_error_without_details(self):
        """Test that error status requires error details."""
        with pytest.raises(ValueError, match="Error details required when status is 'error'"):
            SupervisorResponse(
                session_id="session_123",
                status="error",
                results={},
                requires_approval=False
            )
    
    def test_supervisor_response_approval_without_payload(self):
        """Test that approval required needs approval payload."""
        with pytest.raises(ValueError, match="Approval payload required when approval is needed"):
            SupervisorResponse(
                session_id="session_123",
                status="pending_approval",
                results={},
                requires_approval=True
            )
    
    def test_error_response_empty_message(self):
        """Test that empty error message raises error."""
        with pytest.raises(ValueError, match="Error message cannot be empty"):
            ErrorResponse(
                error_code="VALIDATION_ERROR",
                error_message="",
                error_details={},
                recovery_suggestions=[],
                support_reference="ERR-12345"
            )


class TestRequestModels:
    """Test request model edge cases."""
    
    def test_supervisor_request_empty_user_id(self):
        """Test that empty user ID raises error."""
        with pytest.raises(ValueError, match="User ID cannot be empty"):
            SupervisorRequest(
                user_id="",
                session_id="session_123",
                request_type="analyze",
                parameters={}
            )
    
    def test_supervisor_request_empty_session_id(self):
        """Test that empty session ID raises error."""
        with pytest.raises(ValueError, match="Session ID cannot be empty"):
            SupervisorRequest(
                user_id="user_123",
                session_id="",
                request_type="analyze",
                parameters={}
            )
    
    def test_supervisor_request_invalid_type(self):
        """Test that invalid request type raises error."""
        with pytest.raises(ValueError, match="Invalid request type"):
            SupervisorRequest(
                user_id="user_123",
                session_id="session_123",
                request_type="invalid",
                parameters={}
            )
    
    def test_analysis_request_empty_user_id(self):
        """Test that empty user ID raises error."""
        with pytest.raises(ValueError, match="User ID and Portfolio ID are required"):
            AnalysisRequest(
                user_id="",
                portfolio_id="portfolio_456",
                analysis_type="performance",
                time_period="1M"
            )
    
    def test_analysis_request_empty_portfolio_id(self):
        """Test that empty portfolio ID raises error."""
        with pytest.raises(ValueError, match="User ID and Portfolio ID are required"):
            AnalysisRequest(
                user_id="user_123",
                portfolio_id="",
                analysis_type="performance",
                time_period="1M"
            )
    
    def test_analysis_request_invalid_type(self):
        """Test that invalid analysis type raises error."""
        with pytest.raises(ValueError, match="Invalid analysis type"):
            AnalysisRequest(
                user_id="user_123",
                portfolio_id="portfolio_456",
                analysis_type="invalid",
                time_period="1M"
            )
    
    def test_tax_optimization_request_invalid_year(self):
        """Test that invalid tax year raises error."""
        with pytest.raises(ValueError, match="Invalid tax year"):
            TaxOptimizationRequest(
                user_id="user_123",
                portfolio_id="portfolio_456",
                current_holdings=[],
                target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
                tax_year=1999
            )
    
    def test_rebalancing_constraints_negative_max_cost(self):
        """Test that negative max transaction cost raises error."""
        with pytest.raises(ValueError, match="Max transaction cost must be non-negative"):
            RebalancingConstraints(
                max_transaction_cost=-100.0,
                min_trade_size=10.0,
                risk_tolerance="moderate"
            )
    
    def test_rebalancing_constraints_negative_min_trade(self):
        """Test that negative min trade size raises error."""
        with pytest.raises(ValueError, match="Min trade size must be non-negative"):
            RebalancingConstraints(
                max_transaction_cost=100.0,
                min_trade_size=-10.0,
                risk_tolerance="moderate"
            )
    
    def test_rebalancing_constraints_invalid_risk_tolerance(self):
        """Test that invalid risk tolerance raises error."""
        with pytest.raises(ValueError, match="Invalid risk tolerance"):
            RebalancingConstraints(
                max_transaction_cost=100.0,
                min_trade_size=10.0,
                risk_tolerance="extreme"
            )
    
    def test_subtask_empty_id(self):
        """Test that empty subtask ID raises error."""
        with pytest.raises(ValueError, match="Subtask ID cannot be empty"):
            Subtask(
                subtask_id="",
                subtask_type="analysis",
                agent_name="portfolio_analyzer",
                parameters={}
            )
    
    def test_subtask_invalid_type(self):
        """Test that invalid subtask type raises error."""
        with pytest.raises(ValueError, match="Invalid subtask type"):
            Subtask(
                subtask_id="subtask_1",
                subtask_type="invalid",
                agent_name="portfolio_analyzer",
                parameters={}
            )
    
    def test_subtask_invalid_agent_name(self):
        """Test that invalid agent name raises error."""
        with pytest.raises(ValueError, match="Invalid agent name"):
            Subtask(
                subtask_id="subtask_1",
                subtask_type="analysis",
                agent_name="invalid_agent",
                parameters={}
            )
    
    def test_subtask_invalid_status(self):
        """Test that invalid status raises error."""
        with pytest.raises(ValueError, match="Invalid status"):
            Subtask(
                subtask_id="subtask_1",
                subtask_type="analysis",
                agent_name="portfolio_analyzer",
                parameters={},
                status="unknown"
            )
    
    def test_subtask_negative_retry_count(self):
        """Test that negative retry count raises error."""
        with pytest.raises(ValueError, match="Retry count must be non-negative"):
            Subtask(
                subtask_id="subtask_1",
                subtask_type="analysis",
                agent_name="portfolio_analyzer",
                parameters={},
                retry_count=-1
            )
    
    def test_completed_task_empty_id(self):
        """Test that empty subtask ID raises error."""
        with pytest.raises(ValueError, match="Subtask ID cannot be empty"):
            CompletedTask(
                subtask_id="",
                subtask_type="analysis",
                agent_name="portfolio_analyzer",
                result={"status": "success"}
            )
    
    def test_completed_task_empty_result(self):
        """Test that empty result raises error."""
        with pytest.raises(ValueError, match="Result cannot be empty"):
            CompletedTask(
                subtask_id="subtask_1",
                subtask_type="analysis",
                agent_name="portfolio_analyzer",
                result={}
            )
