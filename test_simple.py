#!/usr/bin/env python
"""Simple test without handler import."""

from src.models.portfolio import Portfolio, Holding
from src.models.requests import RebalancingConstraints
from src.models.responses import TradeOrder, TransactionCosts, RiskImpact, RebalancingPlan

# Test creating objects
holding = Holding(
    ticker="VTI",
    quantity=100,
    cost_basis=200.0,
    current_price=220.0,
    purchase_date="2023-01-15"
)
print(f"Created holding: {holding.ticker}")

portfolio = Portfolio(
    user_id="user_123",
    portfolio_id="portfolio_456",
    portfolio_name="Test",
    target_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
    holdings=[holding],
    total_value=22000.0
)
print(f"Created portfolio: {portfolio.portfolio_name}")

constraints = RebalancingConstraints(
    max_transaction_cost=500.0,
    min_trade_size=50.0,
    risk_tolerance="moderate"
)
print(f"Created constraints: {constraints.risk_tolerance}")

trade_order = TradeOrder(
    order_id="order_1",
    action="buy",
    ticker="VTI",
    quantity=10,
    order_type="market",
    estimated_price=220.0,
    estimated_cost=2200.0
)
print(f"Created trade order: {trade_order.action} {trade_order.quantity} {trade_order.ticker}")

costs = TransactionCosts(
    total_commission=0.0,
    estimated_slippage=2.2,
    total_cost=2.2
)
print(f"Created costs: ${costs.total_cost:.2f}")

risk_impact = RiskImpact(
    current_risk_score=0.5,
    projected_risk_score=0.45,
    risk_change=-0.05,
    risk_assessment="reduced"
)
print(f"Created risk impact: {risk_impact.risk_assessment}")

plan = RebalancingPlan(
    portfolio_id="portfolio_456",
    timestamp="2024-01-15T10:00:00",
    trade_orders=[trade_order],
    expected_costs=costs,
    projected_allocation={"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
    risk_impact=risk_impact
)
print(f"Created rebalancing plan: {plan.portfolio_id}")

print("\nAll tests passed!")
