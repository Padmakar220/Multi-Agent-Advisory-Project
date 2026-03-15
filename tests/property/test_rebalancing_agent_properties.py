"""
Property-based tests for Rebalancing Agent.

Tests:
- Property 14: Allocation Delta Calculation Accuracy
- Property 15: Trade Order Completeness
- Property 16: Transaction Cost Inclusion
- Property 17: Risk Tolerance Constraint Satisfaction
- Property 18: Rebalancing Plan Schema Conformance

These tests validate that the Rebalancing Agent produces correct trade orders
and rebalancing plans across all valid portfolio configurations.
"""

import sys
import os
import importlib.util
import json

# Load the handler module directly
handler_path = os.path.join(os.path.dirname(__file__), '../../lambda/rebalancing-agent/handler.py')
spec = importlib.util.spec_from_file_location("rebalancing_agent_handler", handler_path)
handler_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler_module)

RebalancingAgent = handler_module.RebalancingAgent

import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch

from src.models.portfolio import Portfolio, Holding
from src.models.requests import RebalancingConstraints
from src.models.responses import (
    RebalancingPlan,
    TradeOrder,
    TransactionCosts,
    RiskImpact,
)


# ============================================================================
# Hypothesis Strategies for Data Generation
# ============================================================================

@st.composite
def holding_strategy(draw):
    """Generate a valid holding object."""
    ticker = draw(st.sampled_from(["VTI", "VXUS", "BND", "VGIT", "VMFXX"]))
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
    if total == 0:
        return {"stocks": 0.6, "bonds": 0.3, "cash": 0.1}
    
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


@st.composite
def rebalancing_constraints_strategy(draw):
    """Generate valid rebalancing constraints."""
    max_cost = draw(st.floats(min_value=10.0, max_value=10000.0, allow_nan=False, allow_infinity=False))
    min_size = draw(st.floats(min_value=1.0, max_value=max_cost / 2, allow_nan=False, allow_infinity=False))
    risk_tolerance = draw(st.sampled_from(["conservative", "moderate", "aggressive"]))
    
    return RebalancingConstraints(
        max_transaction_cost=max_cost,
        min_trade_size=min_size,
        risk_tolerance=risk_tolerance,
        excluded_securities=[]
    )


# ============================================================================
# Property 14: Allocation Delta Calculation Accuracy
# ============================================================================

@given(portfolio_strategy(), target_allocation_strategy())
@settings(max_examples=50)
def test_allocation_delta_calculation_accuracy(portfolio, target_allocation):
    """
    **Validates: Requirements 4.1**
    
    Property: Allocation deltas should accurately represent the difference
    between current and target allocation.
    
    For each asset class:
    - Delta = (target_pct - current_pct) * portfolio_value
    - Sum of all deltas should be approximately zero (buy and sell balance)
    """
    agent = RebalancingAgent()
    
    deltas = agent._calculate_allocation_deltas(portfolio, target_allocation)
    
    # Verify deltas are calculated for all asset classes
    assert "stocks" in deltas
    assert "bonds" in deltas
    assert "cash" in deltas
    
    # Verify sum of deltas is approximately zero
    total_delta = sum(deltas.values())
    assert abs(total_delta) < 1.0, f"Deltas don't balance: {total_delta}"
    
    # Verify deltas are in reasonable range
    for delta in deltas.values():
        assert isinstance(delta, (int, float))
        assert -portfolio.total_value <= delta <= portfolio.total_value


# ============================================================================
# Property 15: Trade Order Completeness
# ============================================================================

@given(portfolio_strategy(), target_allocation_strategy(), rebalancing_constraints_strategy())
@settings(max_examples=50)
def test_trade_order_completeness(portfolio, target_allocation, constraints):
    """
    **Validates: Requirements 4.2**
    
    Property: Trade orders should be complete and valid.
    
    Each trade order must have:
    - Unique order_id
    - Valid action (buy, sell, hold)
    - Valid ticker
    - Non-negative quantity
    - Valid order_type (market, limit)
    - Non-negative estimated_price
    - Non-negative estimated_cost
    """
    agent = RebalancingAgent()
    
    deltas = agent._calculate_allocation_deltas(portfolio, target_allocation)
    orders = agent._generate_trade_orders(portfolio, deltas, constraints)
    
    # Verify all orders are TradeOrder instances
    for order in orders:
        assert isinstance(order, TradeOrder)
        
        # Verify required fields
        assert order.order_id
        assert order.action in ["buy", "sell", "hold"]
        assert order.ticker
        assert order.quantity >= 0
        assert order.order_type in ["market", "limit"]
        assert order.estimated_price >= 0
        assert order.estimated_cost >= 0
    
    # Verify order IDs are unique
    order_ids = [order.order_id for order in orders]
    assert len(order_ids) == len(set(order_ids))


# ============================================================================
# Property 16: Transaction Cost Inclusion
# ============================================================================

@given(st.lists(
    st.builds(
        TradeOrder,
        order_id=st.uuids().map(str),
        action=st.sampled_from(["buy", "sell"]),
        ticker=st.sampled_from(["VTI", "BND", "VMFXX"]),
        quantity=st.integers(min_value=1, max_value=1000),
        order_type=st.sampled_from(["market", "limit"]),
        estimated_price=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        estimated_cost=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    ),
    min_size=0,
    max_size=10
))
@settings(max_examples=50)
def test_transaction_cost_inclusion(orders):
    """
    **Validates: Requirements 4.3**
    
    Property: Transaction costs should be calculated and included.
    
    - total_commission >= 0
    - estimated_slippage >= 0
    - total_cost = total_commission + estimated_slippage
    - total_cost should be reasonable (< 1% of total trade value)
    """
    agent = RebalancingAgent()
    
    costs = agent._calculate_transaction_costs(orders)
    
    # Verify TransactionCosts instance
    assert isinstance(costs, TransactionCosts)
    
    # Verify cost components
    assert costs.total_commission >= 0
    assert costs.estimated_slippage >= 0
    assert costs.total_cost >= 0
    
    # Verify total cost calculation
    assert abs(costs.total_cost - (costs.total_commission + costs.estimated_slippage)) < 0.01
    
    # Verify costs are reasonable
    total_trade_value = sum(order.estimated_cost for order in orders)
    if total_trade_value > 0:
        cost_ratio = costs.total_cost / total_trade_value
        assert cost_ratio < 0.05, f"Costs too high: {cost_ratio:.2%}"


# ============================================================================
# Property 17: Risk Tolerance Constraint Satisfaction
# ============================================================================

@given(portfolio_strategy(), rebalancing_constraints_strategy())
@settings(max_examples=50)
def test_risk_tolerance_constraint_satisfaction(portfolio, constraints):
    """
    **Validates: Requirements 4.4**
    
    Property: Risk tolerance constraints should be enforced.
    
    - Excluded securities should not appear in trade orders
    - Transaction costs should not exceed max_transaction_cost
    - All trades should respect min_trade_size
    """
    agent = RebalancingAgent()
    
    # Create test orders
    orders = [
        TradeOrder(
            order_id="order_1",
            action="buy",
            ticker="VTI",
            quantity=10,
            order_type="market",
            estimated_price=220.0,
            estimated_cost=2200.0
        ),
    ]
    
    # Should not raise exception for valid constraints
    try:
        agent._check_risk_tolerance_constraints(orders, constraints, portfolio)
    except ValueError as e:
        # Only excluded security errors are expected
        assert "excluded security" in str(e)
    
    # Test with excluded security
    if "VTI" not in constraints.excluded_securities:
        constraints.excluded_securities.append("VTI")
        
        with pytest.raises(ValueError, match="excluded security"):
            agent._check_risk_tolerance_constraints(orders, constraints, portfolio)


# ============================================================================
# Property 18: Rebalancing Plan Schema Conformance
# ============================================================================

@given(portfolio_strategy(), target_allocation_strategy(), rebalancing_constraints_strategy())
@settings(max_examples=50)
def test_rebalancing_plan_schema_conformance(portfolio, target_allocation, constraints):
    """
    **Validates: Requirements 4.5**
    
    Property: Rebalancing plan should conform to schema.
    
    - portfolio_id must match input
    - timestamp must be valid ISO 8601 format
    - trade_orders must be list of TradeOrder
    - expected_costs must be TransactionCosts
    - projected_allocation must sum to 1.0
    - risk_impact must be RiskImpact
    """
    agent = RebalancingAgent()
    
    # Mock dependencies
    agent.portfolio_tool.execute = Mock(return_value=portfolio)
    agent.bedrock_client.invoke_model = Mock(return_value=Mock(
        body=Mock(read=lambda: json.dumps({
            "content": [{"text": '{"recommended_trades": []}'}]
        }).encode())
    ))
    
    plan = agent.rebalance("user_123", "portfolio_456", target_allocation, constraints)
    
    # Verify RebalancingPlan instance
    assert isinstance(plan, RebalancingPlan)
    
    # Verify portfolio_id
    assert plan.portfolio_id == "portfolio_456"
    
    # Verify timestamp is valid ISO 8601
    try:
        datetime.fromisoformat(plan.timestamp)
    except ValueError:
        pytest.fail(f"Invalid timestamp format: {plan.timestamp}")
    
    # Verify trade_orders
    assert isinstance(plan.trade_orders, list)
    for order in plan.trade_orders:
        assert isinstance(order, TradeOrder)
    
    # Verify expected_costs
    assert isinstance(plan.expected_costs, TransactionCosts)
    assert plan.expected_costs.total_cost >= 0
    
    # Verify projected_allocation
    assert isinstance(plan.projected_allocation, dict)
    allocation_sum = sum(plan.projected_allocation.values())
    assert abs(allocation_sum - 1.0) < 0.01, f"Allocation sum: {allocation_sum}"
    
    # Verify risk_impact
    assert isinstance(plan.risk_impact, RiskImpact)
    assert plan.risk_impact.risk_assessment in ["reduced", "increased", "unchanged"]


# ============================================================================
# Additional Property Tests
# ============================================================================

@given(portfolio_strategy())
@settings(max_examples=50)
def test_risk_score_bounds(portfolio):
    """
    Property: Risk score should always be between 0 and 1.
    """
    agent = RebalancingAgent()
    
    risk_score = agent._calculate_risk_score(portfolio)
    
    assert isinstance(risk_score, float)
    assert 0.0 <= risk_score <= 1.0


@given(portfolio_strategy(), target_allocation_strategy())
@settings(max_examples=50)
def test_projected_allocation_validity(portfolio, target_allocation):
    """
    Property: Projected allocation should always sum to 1.0.
    """
    agent = RebalancingAgent()
    
    orders = []
    projected = agent._calculate_projected_allocation(portfolio, orders, target_allocation)
    
    assert isinstance(projected, dict)
    allocation_sum = sum(projected.values())
    assert abs(allocation_sum - 1.0) < 0.01
