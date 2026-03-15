"""
Property-based tests for Portfolio Analyzer Agent.

Tests:
- Property 6: Performance Metrics Completeness
- Property 7: Allocation Drift Calculation Accuracy
- Property 8: Market Data Query Execution
- Property 9: Analysis Report Schema Conformance

These tests validate that the Portfolio Analyzer produces correct and complete
analysis reports across all valid portfolio configurations.
"""

import sys
import os
import importlib.util
import json

# Load the handler module directly
handler_path = os.path.join(os.path.dirname(__file__), '../../lambda/portfolio-analyzer/handler.py')
spec = importlib.util.spec_from_file_location("portfolio_analyzer_handler", handler_path)
handler_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler_module)

PortfolioAnalyzer = handler_module.PortfolioAnalyzer

import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch

from src.models.portfolio import Portfolio, Holding
from src.models.responses import (
    AnalysisReport,
    PerformanceMetrics,
    RiskMetrics,
    AllocationDrift,
    MarketInsight,
)


# ============================================================================
# Hypothesis Strategies for Data Generation
# ============================================================================

@st.composite
def holding_strategy(draw):
    """Generate a valid holding object."""
    ticker = draw(st.text(min_size=1, max_size=5, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    quantity = draw(st.integers(min_value=1, max_value=10000))
    cost_basis = draw(st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False))
    current_price = draw(st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False))
    
    return Holding(
        ticker=ticker,
        quantity=quantity,
        cost_basis=cost_basis,
        current_price=current_price,
        purchase_date="2023-01-15"
    )


@st.composite
def target_allocation_strategy(draw):
    """Generate a valid target allocation that sums to 1.0."""
    stocks = draw(st.floats(min_value=0.0, max_value=1.0))
    bonds = draw(st.floats(min_value=0.0, max_value=1.0 - stocks))
    cash = 1.0 - stocks - bonds
    
    # Normalize to ensure sum is exactly 1.0
    total = stocks + bonds + cash
    return {
        "stocks": round(stocks / total, 4),
        "bonds": round(bonds / total, 4),
        "cash": round(cash / total, 4)
    }


@st.composite
def portfolio_strategy(draw):
    """Generate a valid portfolio object."""
    user_id = draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"))
    portfolio_id = draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"))
    portfolio_name = draw(st.text(min_size=1, max_size=50))
    
    # Generate 1-5 holdings
    holdings = draw(st.lists(holding_strategy(), min_size=1, max_size=5))
    target_allocation = draw(target_allocation_strategy())
    
    total_value = sum(h.market_value for h in holdings)
    
    return Portfolio(
        user_id=user_id,
        portfolio_id=portfolio_id,
        portfolio_name=portfolio_name,
        target_allocation=target_allocation,
        holdings=holdings,
        total_value=total_value,
        risk_tolerance="moderate"
    )


# ============================================================================
# Property 6: Performance Metrics Completeness
# ============================================================================

@settings(max_examples=50, deadline=None)
@given(portfolio=portfolio_strategy())
def test_performance_metrics_completeness(portfolio):
    """
    **Validates: Requirements 2.2**
    
    For any portfolio analysis, the resulting report should include all required
    performance metrics (total return, risk exposure, Sharpe ratio, volatility)
    with valid numerical values.
    """
    analyzer = PortfolioAnalyzer()
    analyzer.portfolio_tool = Mock()
    analyzer.market_data_tool = Mock()
    analyzer.bedrock_client = Mock()
    
    metrics = analyzer._calculate_performance_metrics(portfolio)
    
    # All metrics should be present
    assert hasattr(metrics, "total_return")
    assert hasattr(metrics, "annualized_return")
    assert hasattr(metrics, "sharpe_ratio")
    assert hasattr(metrics, "max_drawdown")
    
    # All metrics should be numeric
    assert isinstance(metrics.total_return, (int, float))
    assert isinstance(metrics.annualized_return, (int, float))
    assert isinstance(metrics.sharpe_ratio, (int, float))
    assert isinstance(metrics.max_drawdown, (int, float))
    
    # Max drawdown should be non-positive
    assert metrics.max_drawdown <= 0
    
    # Annualized return can be positive or negative
    assert isinstance(metrics.annualized_return, (int, float))


# ============================================================================
# Property 7: Allocation Drift Calculation Accuracy
# ============================================================================

@settings(max_examples=50, deadline=None)
@given(portfolio=portfolio_strategy())
def test_allocation_drift_calculation_accuracy(portfolio):
    """
    **Validates: Requirements 2.3**
    
    For any portfolio with a defined target allocation, the calculated drift
    should equal the absolute difference between current and target allocations
    for each asset class.
    """
    analyzer = PortfolioAnalyzer()
    analyzer.portfolio_tool = Mock()
    analyzer.market_data_tool = Mock()
    analyzer.bedrock_client = Mock()
    
    drift = analyzer._calculate_allocation_drift(portfolio)
    
    # Verify drift calculation accuracy
    for asset_class in portfolio.target_allocation:
        current = drift.current_allocation.get(asset_class, 0.0)
        target = drift.target_allocation.get(asset_class, 0.0)
        calculated_drift = drift.drift_percentage.get(asset_class, 0.0)
        
        expected_drift = abs(current - target)
        assert abs(calculated_drift - expected_drift) < 0.0001, \
            f"Drift mismatch for {asset_class}: expected {expected_drift}, got {calculated_drift}"
    
    # Current and target allocations should sum to approximately 1.0
    current_sum = sum(drift.current_allocation.values())
    target_sum = sum(drift.target_allocation.values())
    
    assert abs(current_sum - 1.0) < 0.01, f"Current allocation sum: {current_sum}"
    assert abs(target_sum - 1.0) < 0.01, f"Target allocation sum: {target_sum}"


# ============================================================================
# Property 8: Market Data Query Execution
# ============================================================================

@settings(max_examples=30, deadline=None)
@given(portfolio=portfolio_strategy())
def test_market_data_query_execution(portfolio):
    """
    **Validates: Requirements 2.4**
    
    For any portfolio analysis request, the Portfolio Analyzer should query
    OpenSearch Serverless and receive market data results relevant to the
    portfolio holdings.
    """
    analyzer = PortfolioAnalyzer()
    analyzer.portfolio_tool = Mock()
    analyzer.market_data_tool = Mock()
    analyzer.bedrock_client = Mock()
    
    # Setup mock market data
    mock_market_data = [
        Mock(
            title="Market Update",
            content="Market content",
            ticker=portfolio.holdings[0].ticker,
            sector="technology",
            timestamp="2024-01-15T10:00:00Z",
            source="news_api",
            similarity_score=0.95
        )
    ]
    analyzer.market_data_tool.execute.return_value = mock_market_data
    
    context = analyzer._query_market_context(portfolio)
    
    # Should return list of market insights
    assert isinstance(context, list)
    
    # Each item should be a MarketInsight
    for insight in context:
        assert isinstance(insight, MarketInsight)
        assert hasattr(insight, "title")
        assert hasattr(insight, "content")
        assert hasattr(insight, "relevance_score")
        assert 0 <= insight.relevance_score <= 1


# ============================================================================
# Property 9: Analysis Report Schema Conformance
# ============================================================================

@settings(max_examples=30, deadline=None)
@given(portfolio=portfolio_strategy())
def test_analysis_report_schema_conformance(portfolio):
    """
    **Validates: Requirements 2.5**
    
    For any completed portfolio analysis, the output should conform to the
    AnalysisReport schema with all required fields populated.
    """
    analyzer = PortfolioAnalyzer()
    analyzer.portfolio_tool = Mock()
    analyzer.portfolio_tool.execute.return_value = portfolio
    analyzer.market_data_tool = Mock()
    analyzer.market_data_tool.execute.return_value = []
    analyzer.bedrock_client = Mock()
    analyzer.bedrock_client.invoke_model.return_value = {
        "body": Mock(read=lambda: json.dumps({
            "content": [{"text": "Recommendation 1\nRecommendation 2"}]
        }))
    }
    
    report = analyzer.analyze(portfolio.user_id, portfolio.portfolio_id)
    
    # Verify report structure
    assert isinstance(report, AnalysisReport)
    
    # All required fields should be present
    assert report.portfolio_id == portfolio.portfolio_id
    assert report.timestamp is not None
    assert isinstance(report.performance_metrics, PerformanceMetrics)
    assert isinstance(report.risk_metrics, RiskMetrics)
    assert isinstance(report.allocation_drift, AllocationDrift)
    assert isinstance(report.market_context, list)
    assert isinstance(report.recommendations, list)
    
    # Recommendations should be non-empty
    assert len(report.recommendations) > 0
    
    # All recommendations should be strings
    for rec in report.recommendations:
        assert isinstance(rec, str)
        assert len(rec) > 0


# ============================================================================
# Additional Property Tests
# ============================================================================

@settings(max_examples=50, deadline=None)
@given(portfolio=portfolio_strategy())
def test_risk_metrics_validity(portfolio):
    """
    Test that risk metrics are always valid and within expected ranges.
    """
    analyzer = PortfolioAnalyzer()
    analyzer.portfolio_tool = Mock()
    analyzer.market_data_tool = Mock()
    analyzer.bedrock_client = Mock()
    
    metrics = analyzer._calculate_risk_metrics(portfolio)
    
    # Volatility should be non-negative
    assert metrics.portfolio_volatility >= 0
    
    # Beta should be positive
    assert metrics.beta > 0
    
    # VaR should be non-positive
    assert metrics.var_95 <= 0
    
    # Concentration risk should be a dict
    assert isinstance(metrics.concentration_risk, dict)


@settings(max_examples=50, deadline=None)
@given(portfolio=portfolio_strategy())
def test_allocation_drift_rebalancing_threshold(portfolio):
    """
    Test that rebalancing_needed flag is set correctly based on drift threshold.
    """
    analyzer = PortfolioAnalyzer()
    analyzer.portfolio_tool = Mock()
    analyzer.market_data_tool = Mock()
    analyzer.bedrock_client = Mock()
    
    drift = analyzer._calculate_allocation_drift(portfolio)
    
    # Calculate maximum drift
    max_drift = max(drift.drift_percentage.values()) if drift.drift_percentage else 0.0
    
    # Rebalancing should be needed if max drift > 5%
    # Note: Due to asset class mapping, drift may be larger than expected
    if max_drift > 0.05:
        assert drift.rebalancing_needed is True
    else:
        assert drift.rebalancing_needed is False
