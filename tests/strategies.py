"""
Custom Hypothesis strategies for the Multi-Agent Advisory AI System test suite.

Provides reusable generators for:
- Portfolio objects
- TradeOrder objects
- AgentState objects
- Target allocation dicts
"""

import uuid
from datetime import datetime

from hypothesis import strategies as st

from src.models.portfolio import AgentState, Holding, Portfolio, Transaction
from src.models.requests import RebalancingConstraints, Subtask
from src.models.responses import (
    AllocationDrift,
    PerformanceMetrics,
    RebalancingPlan,
    RiskImpact,
    RiskMetrics,
    TradeOrder,
    TransactionCosts,
)

# ---------------------------------------------------------------------------
# Primitive building blocks
# ---------------------------------------------------------------------------

_TICKERS = st.sampled_from(["VTI", "VXUS", "BND", "VGIT", "VMFXX", "SPY", "QQQ", "IWM", "GLD", "TLT"])
_RISK_TOLERANCES = st.sampled_from(["conservative", "moderate", "aggressive"])
_AGENT_TYPES = st.sampled_from(["supervisor", "portfolio_analyzer", "tax_optimizer", "rebalancing_agent"])
_ORDER_TYPES = st.sampled_from(["market", "limit"])
_ACTIONS = st.sampled_from(["buy", "sell"])
_TRADE_ACTIONS = st.sampled_from(["buy", "sell", "hold"])


@st.composite
def holding_strategy(draw, ticker=None):
    """Generate a valid Holding object."""
    t = ticker if ticker else draw(_TICKERS)
    quantity = draw(st.integers(min_value=1, max_value=10_000))
    cost_basis = draw(st.floats(min_value=0.01, max_value=10_000.0, allow_nan=False, allow_infinity=False))
    current_price = draw(st.floats(min_value=0.01, max_value=10_000.0, allow_nan=False, allow_infinity=False))
    return Holding(
        ticker=t,
        quantity=quantity,
        cost_basis=cost_basis,
        current_price=current_price,
        purchase_date="2023-01-15",
    )


@st.composite
def allocation_strategy(draw, asset_classes=None):
    """
    Generate a valid target allocation dict that sums to exactly 1.0.

    Args:
        asset_classes: optional list of asset class names; defaults to
                       ["stocks", "bonds", "cash"].
    """
    classes = asset_classes or ["stocks", "bonds", "cash"]
    n = len(classes)

    # Draw n-1 random fractions and derive the last one
    fractions = [draw(st.floats(min_value=0.0, max_value=1.0)) for _ in range(n - 1)]
    total = sum(fractions)

    if total > 1.0:
        # Normalise so they fit within [0, 1]
        fractions = [f / total for f in fractions]
        total = sum(fractions)

    last = max(0.0, 1.0 - total)
    fractions.append(last)

    # Re-normalise to guarantee exact sum of 1.0
    grand_total = sum(fractions)
    if grand_total == 0.0:
        fractions = [1.0 / n] * n
        grand_total = 1.0

    return {cls: round(f / grand_total, 6) for cls, f in zip(classes, fractions)}


@st.composite
def portfolio_strategy(draw, min_holdings=1, max_holdings=5):
    """
    Generate a valid Portfolio object.

    Args:
        min_holdings: minimum number of holdings (default 1).
        max_holdings: maximum number of holdings (default 5).
    """
    user_id = draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"))
    portfolio_id = draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"))
    portfolio_name = draw(st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789 "))
    risk_tolerance = draw(_RISK_TOLERANCES)
    target_allocation = draw(allocation_strategy())
    holdings = draw(st.lists(holding_strategy(), min_size=min_holdings, max_size=max_holdings))
    total_value = sum(h.market_value for h in holdings)

    return Portfolio(
        user_id=user_id,
        portfolio_id=portfolio_id,
        portfolio_name=portfolio_name,
        target_allocation=target_allocation,
        holdings=holdings,
        total_value=total_value,
        risk_tolerance=risk_tolerance,
    )


@st.composite
def trade_order_strategy(draw):
    """Generate a valid TradeOrder object."""
    order_id = draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"))
    action = draw(_TRADE_ACTIONS)
    ticker = draw(_TICKERS)
    quantity = draw(st.integers(min_value=0, max_value=10_000))
    order_type = draw(_ORDER_TYPES)
    estimated_price = draw(st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False, allow_infinity=False))
    estimated_cost = estimated_price * quantity

    return TradeOrder(
        order_id=order_id,
        action=action,
        ticker=ticker,
        quantity=quantity,
        order_type=order_type,
        estimated_price=estimated_price,
        estimated_cost=estimated_cost,
    )


@st.composite
def agent_state_strategy(draw):
    """Generate a valid AgentState object."""
    session_id = draw(st.text(min_size=1, max_size=36, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-"))
    user_id = draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"))
    agent_type = draw(_AGENT_TYPES)

    state = {
        "current_step": draw(st.sampled_from(["idle", "analyzing", "waiting_approval", "executing"])),
        "subtasks_completed": draw(st.lists(st.sampled_from(["portfolio_analysis", "tax_optimization", "rebalancing"]), max_size=3)),
        "conversation_history": [],
        "user_preferences": {"risk_tolerance": draw(_RISK_TOLERANCES)},
    }

    return AgentState(
        session_id=session_id,
        user_id=user_id,
        agent_type=agent_type,
        state=state,
    )


@st.composite
def rebalancing_plan_strategy(draw):
    """Generate a valid RebalancingPlan object."""
    portfolio_id = draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"))
    trade_orders = draw(st.lists(trade_order_strategy(), min_size=1, max_size=5))
    projected_allocation = draw(allocation_strategy())

    costs = TransactionCosts(
        total_commission=draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)),
        estimated_slippage=draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)),
        total_cost=draw(st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False)),
    )

    risk_impact = RiskImpact(
        current_risk_score=draw(st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)),
        projected_risk_score=draw(st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)),
        risk_change=draw(st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False)),
        risk_assessment=draw(st.sampled_from(["reduced", "increased", "unchanged"])),
    )

    return RebalancingPlan(
        portfolio_id=portfolio_id,
        timestamp=datetime.utcnow().isoformat(),
        trade_orders=trade_orders,
        expected_costs=costs,
        projected_allocation=projected_allocation,
        risk_impact=risk_impact,
    )
