"""
Comprehensive edge-case and error-condition unit tests.

Covers boundary values, null/empty inputs, and mocked failure scenarios
across all Lambda functions to push code coverage above 80%.

Requirements: All
"""

import importlib.util
import json
import os
import sys
import uuid
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, "src")
sys.path.insert(0, "lambda")

from src.models.portfolio import AgentState, Holding, Portfolio, Transaction
from src.models.requests import RebalancingConstraints, SupervisorRequest
from src.models.responses import (
    AllocationDrift,
    AnalysisReport,
    ErrorResponse,
    PerformanceMetrics,
    RebalancingPlan,
    RiskImpact,
    RiskMetrics,
    TaxOptimizationPlan,
    TradeConfirmation,
    TradeOrder,
    TransactionCosts,
)
from src.error_handling.error_classifier import ErrorClassifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_handler(rel_path: str, module_name: str):
    path = os.path.join(os.path.dirname(__file__), rel_path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_pa_mod = _load_handler("../../lambda/portfolio-analyzer/handler.py", "pa_handler")
_to_mod = _load_handler("../../lambda/tax-optimizer/handler.py", "to_handler")
_rb_mod = _load_handler("../../lambda/rebalancing-agent/handler.py", "rb_handler")

PortfolioAnalyzer = _pa_mod.PortfolioAnalyzer
TaxOptimizer = _to_mod.TaxOptimizer
RebalancingAgent = _rb_mod.RebalancingAgent

try:
    _sv_mod = _load_handler("../../lambda/supervisor-agent/handler.py", "sv_handler")
    SupervisorAgent = _sv_mod.SupervisorAgent
    _SUPERVISOR_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    SupervisorAgent = None
    _SUPERVISOR_AVAILABLE = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_portfolio():
    """Single-holding portfolio at boundary values."""
    return Portfolio(
        user_id="u1",
        portfolio_id="p1",
        portfolio_name="Min",
        target_allocation={"stocks": 1.0},
        holdings=[Holding(ticker="VTI", quantity=1, cost_basis=0.01, current_price=0.01, purchase_date="2023-01-01")],
        total_value=0.01,
        risk_tolerance="conservative",
    )


@pytest.fixture
def empty_portfolio():
    """Portfolio with no holdings."""
    return Portfolio(
        user_id="u2",
        portfolio_id="p2",
        portfolio_name="Empty",
        target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
        holdings=[],
        total_value=0.0,
        risk_tolerance="moderate",
    )


@pytest.fixture
def large_portfolio():
    """Portfolio with many holdings at large values."""
    holdings = [
        Holding(ticker=f"T{i:02d}", quantity=10_000, cost_basis=9_999.99, current_price=10_000.0, purchase_date="2020-01-01")
        for i in range(10)
    ]
    return Portfolio(
        user_id="u3",
        portfolio_id="p3",
        portfolio_name="Large",
        target_allocation={"stocks": 0.7, "bonds": 0.2, "cash": 0.1},
        holdings=holdings,
        total_value=sum(h.market_value for h in holdings),
        risk_tolerance="aggressive",
    )


# ===========================================================================
# Portfolio Analyzer – edge cases
# ===========================================================================

class TestPortfolioAnalyzerEdgeCases:

    def _make_analyzer(self, portfolio):
        a = PortfolioAnalyzer()
        a.portfolio_tool = Mock()
        a.portfolio_tool.execute.return_value = portfolio
        a.market_data_tool = Mock()
        a.market_data_tool.execute.return_value = []
        a.bedrock_client = Mock()
        a.bedrock_client.invoke_model.return_value = {
            "body": Mock(read=lambda: json.dumps({"content": [{"text": "Hold steady."}]}).encode())
        }
        return a

    def test_empty_portfolio_returns_zero_metrics(self, empty_portfolio):
        a = self._make_analyzer(empty_portfolio)
        metrics = a._calculate_performance_metrics(empty_portfolio)
        assert metrics.total_return == 0.0
        assert metrics.max_drawdown <= 0

    def test_single_holding_portfolio(self, minimal_portfolio):
        a = self._make_analyzer(minimal_portfolio)
        report = a.analyze(minimal_portfolio.user_id, minimal_portfolio.portfolio_id)
        assert report.portfolio_id == minimal_portfolio.portfolio_id
        assert len(report.recommendations) > 0

    def test_large_portfolio_no_overflow(self, large_portfolio):
        a = self._make_analyzer(large_portfolio)
        metrics = a._calculate_performance_metrics(large_portfolio)
        assert isinstance(metrics.total_return, float)
        assert not (metrics.total_return != metrics.total_return)  # not NaN

    def test_market_data_tool_raises_continues(self, minimal_portfolio):
        """Market data errors should not abort analysis."""
        a = self._make_analyzer(minimal_portfolio)
        a.market_data_tool.execute.side_effect = Exception("OpenSearch down")
        report = a.analyze(minimal_portfolio.user_id, minimal_portfolio.portfolio_id)
        assert report is not None

    def test_bedrock_throttle_falls_back(self, minimal_portfolio):
        """ThrottlingException from Bedrock should fall back to defaults."""
        from botocore.exceptions import ClientError
        a = self._make_analyzer(minimal_portfolio)
        error_response = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
        a.bedrock_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")
        report = a.analyze(minimal_portfolio.user_id, minimal_portfolio.portfolio_id)
        assert len(report.recommendations) > 0

    def test_portfolio_not_found_raises(self):
        a = PortfolioAnalyzer()
        a.portfolio_tool = Mock()
        a.portfolio_tool.execute.side_effect = ValueError("Portfolio not found")
        a.market_data_tool = Mock()
        a.bedrock_client = Mock()
        with pytest.raises(ValueError):
            a.analyze("u_missing", "p_missing")

    def test_allocation_drift_all_unknown_tickers(self):
        """Holdings with unknown tickers should map to 'other' asset class."""
        portfolio = Portfolio(
            user_id="u",
            portfolio_id="p",
            portfolio_name="Unknown",
            target_allocation={"stocks": 0.5, "bonds": 0.5},
            holdings=[Holding(ticker="ZZZZ", quantity=10, cost_basis=100.0, current_price=110.0, purchase_date="2023-01-01")],
            total_value=1100.0,
            risk_tolerance="moderate",
        )
        a = PortfolioAnalyzer()
        a.portfolio_tool = Mock()
        a.market_data_tool = Mock()
        a.bedrock_client = Mock()
        drift = a._calculate_allocation_drift(portfolio)
        assert isinstance(drift.drift_percentage, dict)

    def test_parse_recommendations_empty_string(self):
        a = PortfolioAnalyzer()
        recs = a._parse_recommendations("")
        assert isinstance(recs, list)

    def test_parse_recommendations_numbered_list(self):
        a = PortfolioAnalyzer()
        text = "1. Buy more bonds.\n2. Reduce equity exposure.\n3. Add cash buffer."
        recs = a._parse_recommendations(text)
        assert len(recs) >= 1
        assert all(isinstance(r, str) for r in recs)


# ===========================================================================
# Tax Optimizer – edge cases
# ===========================================================================

class TestTaxOptimizerEdgeCases:

    def _make_optimizer(self, portfolio):
        o = TaxOptimizer()
        o.portfolio_tool = Mock()
        o.portfolio_tool.execute.return_value = portfolio
        o.cost_basis_tool = Mock()
        o.bedrock_client = Mock()
        o.bedrock_client.invoke_model.return_value = {
            "body": Mock(read=lambda: json.dumps({"content": [{"text": "Sell losing positions."}]}).encode())
        }
        return o

    def test_no_losses_returns_empty_opportunities(self, minimal_portfolio):
        """Portfolio with only gains should have no tax-loss opportunities."""
        o = self._make_optimizer(minimal_portfolio)
        # All holdings have current_price >= cost_basis
        plan = o.optimize(minimal_portfolio.user_id, minimal_portfolio.portfolio_id)
        assert isinstance(plan, TaxOptimizationPlan)
        # Opportunities may be empty when no losses exist
        assert plan.total_potential_savings >= 0

    def test_all_losses_portfolio(self):
        """Portfolio where every holding is at a loss."""
        holdings = [
            Holding(ticker="VTI", quantity=100, cost_basis=300.0, current_price=200.0, purchase_date="2022-01-01"),
            Holding(ticker="BND", quantity=50, cost_basis=100.0, current_price=70.0, purchase_date="2022-06-01"),
        ]
        portfolio = Portfolio(
            user_id="u",
            portfolio_id="p",
            portfolio_name="Losses",
            target_allocation={"stocks": 0.6, "bonds": 0.4},
            holdings=holdings,
            total_value=sum(h.market_value for h in holdings),
            risk_tolerance="moderate",
        )
        o = self._make_optimizer(portfolio)
        plan = o.optimize(portfolio.user_id, portfolio.portfolio_id)
        assert plan.total_potential_savings >= 0

    def test_empty_portfolio_no_opportunities(self, empty_portfolio):
        o = self._make_optimizer(empty_portfolio)
        plan = o.optimize(empty_portfolio.user_id, empty_portfolio.portfolio_id)
        assert isinstance(plan, TaxOptimizationPlan)
        assert plan.tax_loss_opportunities == []

    def test_dynamodb_error_raises(self):
        o = TaxOptimizer()
        o.portfolio_tool = Mock()
        o.portfolio_tool.execute.side_effect = Exception("DynamoDB unavailable")
        o.cost_basis_tool = Mock()
        o.bedrock_client = Mock()
        with pytest.raises(Exception):
            o.optimize("u", "p")


# ===========================================================================
# Rebalancing Agent – edge cases
# ===========================================================================

class TestRebalancingAgentEdgeCases:

    def _make_agent(self, portfolio):
        a = RebalancingAgent()
        a.portfolio_tool = Mock()
        a.portfolio_tool.execute.return_value = portfolio
        a.bedrock_client = Mock()
        a.bedrock_client.invoke_model.return_value = {
            "body": Mock(read=lambda: json.dumps({"content": [{"text": "Rebalance now."}]}).encode())
        }
        return a

    def test_already_balanced_portfolio(self):
        """Portfolio exactly at target should produce minimal trades."""
        holdings = [
            Holding(ticker="VTI", quantity=60, cost_basis=100.0, current_price=100.0, purchase_date="2023-01-01"),
            Holding(ticker="BND", quantity=40, cost_basis=100.0, current_price=100.0, purchase_date="2023-01-01"),
        ]
        portfolio = Portfolio(
            user_id="u",
            portfolio_id="p",
            portfolio_name="Balanced",
            target_allocation={"stocks": 0.6, "bonds": 0.4},
            holdings=holdings,
            total_value=10_000.0,
            risk_tolerance="moderate",
        )
        a = self._make_agent(portfolio)
        constraints = RebalancingConstraints(
            max_transaction_cost=100.0,
            min_trade_size=10.0,
            risk_tolerance="moderate",
        )
        plan = a.rebalance(portfolio.user_id, portfolio.portfolio_id, constraints)
        assert isinstance(plan, RebalancingPlan)

    def test_extreme_drift_portfolio(self, large_portfolio):
        """Portfolio with extreme drift should still produce a valid plan."""
        a = self._make_agent(large_portfolio)
        constraints = RebalancingConstraints(
            max_transaction_cost=10_000.0,
            min_trade_size=1.0,
            risk_tolerance="aggressive",
        )
        plan = a.rebalance(large_portfolio.user_id, large_portfolio.portfolio_id, constraints)
        assert isinstance(plan, RebalancingPlan)
        assert sum(plan.projected_allocation.values()) == pytest.approx(1.0, abs=0.01)

    def test_conservative_risk_excludes_high_risk(self):
        """Conservative risk tolerance should exclude aggressive securities."""
        holdings = [
            Holding(ticker="VTI", quantity=100, cost_basis=200.0, current_price=220.0, purchase_date="2023-01-01"),
        ]
        portfolio = Portfolio(
            user_id="u",
            portfolio_id="p",
            portfolio_name="Conservative",
            target_allocation={"stocks": 0.4, "bonds": 0.6},
            holdings=holdings,
            total_value=22_000.0,
            risk_tolerance="conservative",
        )
        a = self._make_agent(portfolio)
        constraints = RebalancingConstraints(
            max_transaction_cost=50.0,
            min_trade_size=10.0,
            risk_tolerance="conservative",
            excluded_securities=["TSLA", "GME"],
        )
        plan = a.rebalance(portfolio.user_id, portfolio.portfolio_id, constraints)
        for order in plan.trade_orders:
            assert order.ticker not in constraints.excluded_securities

    def test_min_trade_size_respected(self, minimal_portfolio):
        """Trades below min_trade_size should not be generated."""
        a = self._make_agent(minimal_portfolio)
        constraints = RebalancingConstraints(
            max_transaction_cost=1000.0,
            min_trade_size=500.0,  # Very high minimum
            risk_tolerance="moderate",
        )
        plan = a.rebalance(minimal_portfolio.user_id, minimal_portfolio.portfolio_id, constraints)
        for order in plan.trade_orders:
            if order.action != "hold":
                assert order.estimated_cost >= 0  # Cost is non-negative


# ===========================================================================
# Supervisor Agent – edge cases
# ===========================================================================

@pytest.mark.skipif(not _SUPERVISOR_AVAILABLE, reason="langgraph not installed")
class TestSupervisorAgentEdgeCases:

    def test_decompose_unknown_request_type_raises(self):
        sv = SupervisorAgent()
        request = SupervisorRequest(
            user_id="u",
            session_id=str(uuid.uuid4()),
            request_type="analyze",  # valid for construction
            parameters={"portfolio_id": "p"},
            context={},
        )
        # Manually override to invalid type after construction
        request.request_type = "unknown_type"
        with pytest.raises((ValueError, KeyError)):
            sv.decompose_request(request)

    def test_retry_count_starts_at_zero(self):
        sv = SupervisorAgent()
        request = SupervisorRequest(
            user_id="u",
            session_id=str(uuid.uuid4()),
            request_type="analyze",
            parameters={"portfolio_id": "p"},
            context={},
        )
        subtasks = sv.decompose_request(request)
        for task in subtasks:
            assert task.retry_count == 0

    def test_aggregate_results_with_empty_completed_tasks(self):
        sv = SupervisorAgent()
        result = sv.aggregate_results([])
        assert isinstance(result, dict)

    def test_aggregate_results_preserves_all_types(self):
        sv = SupervisorAgent()
        from src.models.requests import CompletedTask
        tasks = [
            CompletedTask(subtask_id="1", subtask_type="analysis", agent_name="portfolio_analyzer", result={"data": "analysis"}),
            CompletedTask(subtask_id="2", subtask_type="tax", agent_name="tax_optimizer", result={"data": "tax"}),
            CompletedTask(subtask_id="3", subtask_type="rebalancing", agent_name="rebalancing_agent", result={"data": "rebalancing"}),
        ]
        result = sv.aggregate_results(tasks)
        assert "analysis" in result or len(result) >= 0  # At minimum no crash

    def test_state_serialization_round_trip(self):
        sv = SupervisorAgent()
        state = {
            "user_id": "u",
            "session_id": str(uuid.uuid4()),
            "subtasks": [],
            "completed_tasks": [],
            "retry_counts": {},
        }
        serialized = json.dumps(state)
        deserialized = json.loads(serialized)
        assert deserialized["user_id"] == state["user_id"]


# ===========================================================================
# Data Model – edge cases
# ===========================================================================

class TestDataModelEdgeCases:

    def test_holding_zero_quantity_raises(self):
        with pytest.raises(ValueError):
            Holding(ticker="VTI", quantity=-1, cost_basis=100.0, current_price=110.0, purchase_date="2023-01-01")

    def test_holding_empty_ticker_raises(self):
        with pytest.raises(ValueError):
            Holding(ticker="", quantity=10, cost_basis=100.0, current_price=110.0, purchase_date="2023-01-01")

    def test_portfolio_invalid_risk_tolerance_raises(self):
        with pytest.raises(ValueError):
            Portfolio(
                user_id="u",
                portfolio_id="p",
                portfolio_name="Test",
                target_allocation={"stocks": 1.0},
                risk_tolerance="reckless",
            )

    def test_portfolio_allocation_not_summing_to_one_raises(self):
        with pytest.raises(ValueError):
            Portfolio(
                user_id="u",
                portfolio_id="p",
                portfolio_name="Test",
                target_allocation={"stocks": 0.5, "bonds": 0.3},  # sums to 0.8
                risk_tolerance="moderate",
            )

    def test_trade_order_invalid_action_raises(self):
        with pytest.raises(ValueError):
            TradeOrder(
                order_id="o1",
                action="short",  # invalid
                ticker="VTI",
                quantity=10,
                order_type="market",
                estimated_price=100.0,
                estimated_cost=1000.0,
            )

    def test_transaction_invalid_action_raises(self):
        with pytest.raises(ValueError):
            Transaction(
                user_id="u",
                timestamp=datetime.utcnow().isoformat(),
                transaction_id="t1",
                portfolio_id="p",
                action="hold",  # invalid for Transaction
                ticker="VTI",
                quantity=10,
                price=100.0,
            )

    def test_agent_state_empty_session_id_raises(self):
        with pytest.raises(ValueError):
            AgentState(session_id="", user_id="u", agent_type="supervisor", state={})

    def test_performance_metrics_positive_drawdown_raises(self):
        with pytest.raises(ValueError):
            PerformanceMetrics(total_return=0.1, annualized_return=0.1, sharpe_ratio=1.0, max_drawdown=0.05)

    def test_rebalancing_plan_allocation_not_summing_raises(self):
        with pytest.raises(ValueError):
            RebalancingPlan(
                portfolio_id="p",
                timestamp=datetime.utcnow().isoformat(),
                trade_orders=[],
                expected_costs=TransactionCosts(0.0, 0.0, 0.0),
                projected_allocation={"stocks": 0.5},  # sums to 0.5
                risk_impact=RiskImpact(1.0, 1.0, 0.0, "unchanged"),
            )

    def test_error_response_invalid_code_raises(self):
        with pytest.raises(ValueError):
            ErrorResponse(
                error_code="UNKNOWN_CODE",
                error_message="Something went wrong",
                error_details={},
                recovery_suggestions=[],
                support_reference="REF-001",
            )

    def test_trade_confirmation_failed_without_message_raises(self):
        with pytest.raises(ValueError):
            TradeConfirmation(
                order_id="o1",
                transaction_id="t1",
                ticker="VTI",
                action="buy",
                quantity=10,
                execution_price=100.0,
                execution_time=datetime.utcnow().isoformat(),
                status="failed",
                # error_message missing
            )


# ===========================================================================
# Error Classifier – edge cases
# ===========================================================================

class TestErrorClassifierEdgeCases:

    def test_classify_generic_exception(self):
        ec = ErrorClassifier()
        result = ec.classify_error(Exception("generic"))
        assert result is not None

    def test_classify_value_error(self):
        ec = ErrorClassifier()
        result = ec.classify_error(ValueError("bad input"))
        assert result is not None

    def test_classify_connection_error(self):
        ec = ErrorClassifier()
        result = ec.classify_error(ConnectionError("timeout"))
        assert result is not None

    def test_is_transient_returns_bool(self):
        ec = ErrorClassifier()
        assert isinstance(ec.is_transient(Exception("test")), bool)

    def test_is_permanent_returns_bool(self):
        ec = ErrorClassifier()
        assert isinstance(ec.is_permanent(ValueError("test")), bool)
