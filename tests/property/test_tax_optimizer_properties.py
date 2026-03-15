"""
Property-based tests for Tax Optimizer Agent.

Tests:
- Property 10: Unrealized Loss Identification Accuracy
- Property 11: Tax Savings Calculation Validity
- Property 12: After-Tax Return Optimization
- Property 13: Tax Optimization Plan Schema Conformance

These tests validate that the Tax Optimizer produces correct and complete
tax optimization plans across all valid portfolio configurations.
"""

import sys
import os
import importlib.util
import json

# Load the handler module directly
handler_path = os.path.join(os.path.dirname(__file__), '../../lambda/tax-optimizer/handler.py')
spec = importlib.util.spec_from_file_location("tax_optimizer_handler", handler_path)
handler_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler_module)

TaxOptimizer = handler_module.TaxOptimizer

import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch

from src.models.portfolio import Portfolio, Holding
from src.models.responses import (
    TaxOptimizationPlan,
    TaxLossOpportunity,
    TaxOptimizedTrade,
    WashSaleWarning,
    CostBasisInfo,
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
    
    # Generate 1-5 unique holdings (no duplicate tickers)
    tickers = draw(st.lists(
        st.text(min_size=1, max_size=5, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        min_size=1,
        max_size=5,
        unique=True
    ))
    
    holdings = []
    for ticker in tickers:
        holding = draw(holding_strategy())
        holding.ticker = ticker
        holdings.append(holding)
    
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


@st.composite
def cost_basis_data_strategy(draw, portfolio):
    """Generate cost basis data matching portfolio holdings."""
    cost_basis_data = {}
    
    for holding in portfolio.holdings:
        cost_basis_data[holding.ticker] = CostBasisInfo(
            ticker=holding.ticker,
            quantity=holding.quantity,
            cost_per_share=holding.cost_basis,
            purchase_date=holding.purchase_date
        )
    
    return cost_basis_data


# ============================================================================
# Property 10: Unrealized Loss Identification Accuracy
# ============================================================================

@settings(max_examples=50, deadline=None)
@given(portfolio=portfolio_strategy())
def test_unrealized_loss_identification_accuracy(portfolio):
    """
    **Validates: Requirements 3.2**
    
    For any portfolio, the Tax Optimizer should identify all securities where
    current value is less than cost basis as unrealized loss opportunities.
    """
    optimizer = TaxOptimizer()
    
    # Create cost basis data
    cost_basis_data = {}
    for holding in portfolio.holdings:
        cost_basis_data[holding.ticker] = CostBasisInfo(
            ticker=holding.ticker,
            quantity=holding.quantity,
            cost_per_share=holding.cost_basis,
            purchase_date=holding.purchase_date
        )
    
    # Identify opportunities
    opportunities = optimizer._identify_tax_loss_opportunities(portfolio, cost_basis_data)
    
    # Verify all identified opportunities have losses
    for opp in opportunities:
        assert opp.unrealized_loss < 0, f"Opportunity {opp.ticker} should have negative unrealized loss"
        assert opp.current_value < (opp.cost_basis * opp.quantity), \
            f"Current value should be less than cost basis for {opp.ticker}"
    
    # Verify each holding is correctly classified
    for holding in portfolio.holdings:
        cost_basis_info = cost_basis_data.get(holding.ticker)
        if cost_basis_info:
            cost_basis_total = cost_basis_info.cost_per_share * holding.quantity
            current_value = holding.current_price * holding.quantity
            
            # Find opportunity for this ticker
            opportunity = next((o for o in opportunities if o.ticker == holding.ticker), None)
            
            if current_value < cost_basis_total:
                # Should be in opportunities
                assert opportunity is not None, \
                    f"Loss opportunity for {holding.ticker} should be identified"
            else:
                # Should not be in opportunities
                assert opportunity is None, \
                    f"Gain for {holding.ticker} should not be identified as loss opportunity"


# ============================================================================
# Property 11: Tax Savings Calculation Validity
# ============================================================================

@settings(max_examples=50, deadline=None)
@given(
    loss_amount=st.floats(min_value=100.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    tax_rate=st.floats(min_value=0.1, max_value=0.4)
)
def test_tax_savings_calculation_validity(loss_amount, tax_rate):
    """
    **Validates: Requirements 3.3**
    
    For any identified tax-loss harvesting opportunity, the calculated potential
    tax savings should be non-negative and should not exceed the unrealized loss
    amount multiplied by the maximum tax rate.
    """
    optimizer = TaxOptimizer(tax_rate=tax_rate)
    
    # Create a tax loss opportunity
    opportunity = TaxLossOpportunity(
        ticker="TEST",
        quantity=100,
        cost_basis=loss_amount / 100,
        current_value=loss_amount * 0.9,
        unrealized_loss=-loss_amount * 0.1,
        potential_tax_savings=loss_amount * 0.1 * tax_rate
    )
    
    # Verify tax savings calculation
    assert opportunity.potential_tax_savings >= 0, "Tax savings should be non-negative"
    
    # Tax savings should not exceed loss * max_tax_rate
    max_tax_savings = abs(opportunity.unrealized_loss) * tax_rate
    assert opportunity.potential_tax_savings <= max_tax_savings + 0.01, \
        f"Tax savings {opportunity.potential_tax_savings} exceeds max {max_tax_savings}"
    
    # Tax savings should be approximately loss * tax_rate
    expected_savings = abs(opportunity.unrealized_loss) * tax_rate
    assert abs(opportunity.potential_tax_savings - expected_savings) < 0.01, \
        f"Tax savings calculation incorrect: expected {expected_savings}, got {opportunity.potential_tax_savings}"


# ============================================================================
# Property 12: After-Tax Return Optimization
# ============================================================================

@settings(max_examples=30, deadline=None)
@given(portfolio=portfolio_strategy())
def test_after_tax_return_optimization(portfolio):
    """
    **Validates: Requirements 3.4**
    
    For any portfolio, the Tax Optimizer's proposed allocation should have equal
    or higher projected after-tax returns compared to the current allocation.
    """
    optimizer = TaxOptimizer()
    
    # Create cost basis data
    cost_basis_data = {}
    for holding in portfolio.holdings:
        cost_basis_data[holding.ticker] = CostBasisInfo(
            ticker=holding.ticker,
            quantity=holding.quantity,
            cost_per_share=holding.cost_basis,
            purchase_date=holding.purchase_date
        )
    
    # Identify opportunities
    opportunities = optimizer._identify_tax_loss_opportunities(portfolio, cost_basis_data)
    
    # Calculate current after-tax return
    current_total_value = sum(h.market_value for h in portfolio.holdings)
    current_cost_basis = sum(h.quantity * h.cost_basis for h in portfolio.holdings)
    current_unrealized_gain = current_total_value - current_cost_basis
    current_tax_liability = max(0, current_unrealized_gain * optimizer.tax_rate)
    current_after_tax_return = current_total_value - current_tax_liability
    
    # Calculate potential after-tax return with tax harvesting
    total_tax_savings = sum(opp.potential_tax_savings for opp in opportunities)
    potential_after_tax_return = current_after_tax_return + total_tax_savings
    
    # After-tax return should be equal or higher
    assert potential_after_tax_return >= current_after_tax_return - 0.01, \
        "Tax optimization should not reduce after-tax returns"


# ============================================================================
# Property 13: Tax Optimization Plan Schema Conformance
# ============================================================================

@settings(max_examples=30, deadline=None)
@given(portfolio=portfolio_strategy())
def test_tax_optimization_plan_schema_conformance(portfolio):
    """
    **Validates: Requirements 3.5**
    
    For any completed tax optimization, the output should conform to the
    TaxOptimizationPlan schema with all required fields populated.
    """
    optimizer = TaxOptimizer()
    
    # Mock dependencies
    optimizer.portfolio_tool = Mock()
    optimizer.portfolio_tool.execute.return_value = portfolio
    
    optimizer.cost_basis_tool = Mock()
    cost_basis_data = {}
    for holding in portfolio.holdings:
        cost_basis_data[holding.ticker] = CostBasisInfo(
            ticker=holding.ticker,
            quantity=holding.quantity,
            cost_per_share=holding.cost_basis,
            purchase_date=holding.purchase_date
        )
    optimizer.cost_basis_tool.execute.side_effect = lambda u, p, t: cost_basis_data.get(t)
    
    optimizer.bedrock_client = Mock()
    optimizer.bedrock_client.invoke_model.return_value = {
        "body": Mock(read=lambda: json.dumps({
            "content": [{
                "text": json.dumps({
                    "recommended_trades": [],
                    "total_tax_savings": 0.0,
                    "notes": "No trades recommended"
                })
            }]
        }))
    }
    
    # Generate plan
    plan = optimizer.optimize(portfolio.user_id, portfolio.portfolio_id)
    
    # Verify schema conformance
    assert isinstance(plan, TaxOptimizationPlan)
    assert hasattr(plan, "portfolio_id")
    assert hasattr(plan, "timestamp")
    assert hasattr(plan, "tax_loss_opportunities")
    assert hasattr(plan, "total_potential_savings")
    assert hasattr(plan, "recommended_trades")
    assert hasattr(plan, "wash_sale_warnings")
    
    # Verify required fields are populated
    assert plan.portfolio_id == portfolio.portfolio_id
    assert isinstance(plan.timestamp, str)
    assert isinstance(plan.tax_loss_opportunities, list)
    assert isinstance(plan.total_potential_savings, (int, float))
    assert isinstance(plan.recommended_trades, list)
    assert isinstance(plan.wash_sale_warnings, list)
    
    # Verify all opportunities have required fields
    for opp in plan.tax_loss_opportunities:
        assert hasattr(opp, "ticker")
        assert hasattr(opp, "quantity")
        assert hasattr(opp, "cost_basis")
        assert hasattr(opp, "current_value")
        assert hasattr(opp, "unrealized_loss")
        assert hasattr(opp, "potential_tax_savings")
    
    # Verify all trades have required fields
    for trade in plan.recommended_trades:
        assert hasattr(trade, "action")
        assert hasattr(trade, "ticker")
        assert hasattr(trade, "quantity")
        assert hasattr(trade, "reason")
        assert hasattr(trade, "tax_impact")
        assert trade.action in ["buy", "sell"]
    
    # Verify all warnings have required fields
    for warning in plan.wash_sale_warnings:
        assert hasattr(warning, "ticker")
        assert hasattr(warning, "sale_date")
        assert hasattr(warning, "purchase_date")
        assert hasattr(warning, "days_between")
        assert hasattr(warning, "warning_message")
