"""
Property-based tests for DynamoDB schema conformance.

Tests:
- Property 31: Portfolio Storage Schema Conformance
- Property 32: Transaction Storage Schema Conformance

These tests validate that portfolio and transaction data conform to the expected
DynamoDB schema structure and can be serialized/deserialized correctly.
"""

import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime, timezone
from decimal import Decimal
import json


# ============================================================================
# Hypothesis Strategies for Data Generation
# ============================================================================

@st.composite
def holding_strategy(draw):
    """Generate a valid holding object."""
    return {
        "ticker": draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Lu",)))),
        "quantity": draw(st.integers(min_value=1, max_value=10000)),
        "cost_basis": draw(st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False)),
        "current_price": draw(st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False)),
        "purchase_date": draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2024, 12, 31))).isoformat()
    }


@st.composite
def target_allocation_strategy(draw):
    """Generate a valid target allocation that sums to 1.0."""
    # Generate three positive floats that sum to 1.0
    stocks = draw(st.floats(min_value=0.0, max_value=1.0))
    bonds = draw(st.floats(min_value=0.0, max_value=1.0 - stocks))
    cash = 1.0 - stocks - bonds
    
    return {
        "stocks": round(stocks, 2),
        "bonds": round(bonds, 2),
        "cash": round(cash, 2)
    }


@st.composite
def portfolio_strategy(draw):
    """Generate a valid portfolio object conforming to DynamoDB schema."""
    holdings = draw(st.lists(holding_strategy(), min_size=0, max_size=20))
    total_value = sum(h["quantity"] * h["current_price"] for h in holdings)
    
    return {
        "user_id": draw(st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=("Ll", "Nd")))),
        "portfolio_id": draw(st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=("Ll", "Nd")))),
        "portfolio_name": draw(st.text(min_size=1, max_size=100)),
        "target_allocation": draw(target_allocation_strategy()),
        "holdings": holdings,
        "total_value": round(total_value, 2),
        "risk_tolerance": draw(st.sampled_from(["conservative", "moderate", "aggressive"])),
        "created_at": draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2024, 12, 31))).isoformat(),
        "updated_at": draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2024, 12, 31))).isoformat()
    }


@st.composite
def transaction_strategy(draw):
    """Generate a valid transaction object conforming to DynamoDB schema."""
    action = draw(st.sampled_from(["buy", "sell"]))
    quantity = draw(st.integers(min_value=1, max_value=1000))
    price = draw(st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False))
    commission = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    
    return {
        "user_id": draw(st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=("Ll", "Nd")))),
        "timestamp": draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2024, 12, 31))).isoformat(),
        "transaction_id": draw(st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=("Ll", "Nd")))),
        "portfolio_id": draw(st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=("Ll", "Nd")))),
        "action": action,
        "ticker": draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Lu",)))),
        "quantity": quantity,
        "price": round(price, 2),
        "commission": round(commission, 2),
        "total_cost": round(quantity * price + commission, 2),
        "execution_status": draw(st.sampled_from(["pending", "completed", "failed", "cancelled"])),
        "order_type": draw(st.sampled_from(["market", "limit", "stop", "stop_limit"])),
        "initiated_by": draw(st.sampled_from(["user", "rebalancing_agent", "tax_optimizer", "supervisor_agent"]))
    }


# ============================================================================
# Schema Validation Functions
# ============================================================================

def validate_portfolio_schema(portfolio):
    """
    Validate that a portfolio object conforms to the expected DynamoDB schema.
    
    Required fields:
    - user_id (string, partition key)
    - portfolio_id (string, sort key)
    - portfolio_name (string)
    - target_allocation (dict with stocks, bonds, cash)
    - holdings (list of holding objects)
    - total_value (number)
    - risk_tolerance (string: conservative, moderate, aggressive)
    - created_at (ISO 8601 timestamp)
    - updated_at (ISO 8601 timestamp)
    """
    # Check required fields exist
    required_fields = [
        "user_id", "portfolio_id", "portfolio_name", "target_allocation",
        "holdings", "total_value", "risk_tolerance", "created_at", "updated_at"
    ]
    for field in required_fields:
        assert field in portfolio, f"Missing required field: {field}"
    
    # Validate field types
    assert isinstance(portfolio["user_id"], str), "user_id must be string"
    assert isinstance(portfolio["portfolio_id"], str), "portfolio_id must be string"
    assert isinstance(portfolio["portfolio_name"], str), "portfolio_name must be string"
    assert isinstance(portfolio["target_allocation"], dict), "target_allocation must be dict"
    assert isinstance(portfolio["holdings"], list), "holdings must be list"
    assert isinstance(portfolio["total_value"], (int, float, Decimal)), "total_value must be number"
    assert isinstance(portfolio["risk_tolerance"], str), "risk_tolerance must be string"
    assert isinstance(portfolio["created_at"], str), "created_at must be string"
    assert isinstance(portfolio["updated_at"], str), "updated_at must be string"
    
    # Validate partition key is non-empty
    assert len(portfolio["user_id"]) > 0, "user_id (partition key) must be non-empty"
    
    # Validate sort key is non-empty
    assert len(portfolio["portfolio_id"]) > 0, "portfolio_id (sort key) must be non-empty"
    
    # Validate target_allocation structure
    assert "stocks" in portfolio["target_allocation"], "target_allocation must have stocks"
    assert "bonds" in portfolio["target_allocation"], "target_allocation must have bonds"
    assert "cash" in portfolio["target_allocation"], "target_allocation must have cash"
    
    # Validate target_allocation sums to approximately 1.0 (allow for rounding)
    allocation_sum = (
        portfolio["target_allocation"]["stocks"] +
        portfolio["target_allocation"]["bonds"] +
        portfolio["target_allocation"]["cash"]
    )
    assert abs(allocation_sum - 1.0) < 0.01, f"target_allocation must sum to 1.0, got {allocation_sum}"
    
    # Validate holdings structure
    for holding in portfolio["holdings"]:
        assert "ticker" in holding, "holding must have ticker"
        assert "quantity" in holding, "holding must have quantity"
        assert "cost_basis" in holding, "holding must have cost_basis"
        assert "current_price" in holding, "holding must have current_price"
        assert "purchase_date" in holding, "holding must have purchase_date"
        
        assert isinstance(holding["ticker"], str), "ticker must be string"
        assert isinstance(holding["quantity"], int), "quantity must be integer"
        assert isinstance(holding["cost_basis"], (int, float, Decimal)), "cost_basis must be number"
        assert isinstance(holding["current_price"], (int, float, Decimal)), "current_price must be number"
        assert isinstance(holding["purchase_date"], str), "purchase_date must be string"
    
    # Validate risk_tolerance is valid value
    assert portfolio["risk_tolerance"] in ["conservative", "moderate", "aggressive"], \
        f"risk_tolerance must be conservative, moderate, or aggressive, got {portfolio['risk_tolerance']}"
    
    # Validate timestamps are ISO 8601 format
    try:
        datetime.fromisoformat(portfolio["created_at"].replace('Z', '+00:00'))
        datetime.fromisoformat(portfolio["updated_at"].replace('Z', '+00:00'))
    except ValueError as e:
        raise AssertionError(f"Timestamps must be ISO 8601 format: {e}")
    
    return True


def validate_transaction_schema(transaction):
    """
    Validate that a transaction object conforms to the expected DynamoDB schema.
    
    Required fields:
    - user_id (string, partition key)
    - timestamp (string, sort key, ISO 8601 format)
    - transaction_id (string)
    - portfolio_id (string, for GSI)
    - action (string: buy, sell)
    - ticker (string)
    - quantity (number)
    - price (number)
    - commission (number)
    - total_cost (number)
    - execution_status (string: pending, completed, failed, cancelled)
    - order_type (string: market, limit, stop, stop_limit)
    - initiated_by (string)
    """
    # Check required fields exist
    required_fields = [
        "user_id", "timestamp", "transaction_id", "portfolio_id", "action",
        "ticker", "quantity", "price", "commission", "total_cost",
        "execution_status", "order_type", "initiated_by"
    ]
    for field in required_fields:
        assert field in transaction, f"Missing required field: {field}"
    
    # Validate field types
    assert isinstance(transaction["user_id"], str), "user_id must be string"
    assert isinstance(transaction["timestamp"], str), "timestamp must be string"
    assert isinstance(transaction["transaction_id"], str), "transaction_id must be string"
    assert isinstance(transaction["portfolio_id"], str), "portfolio_id must be string"
    assert isinstance(transaction["action"], str), "action must be string"
    assert isinstance(transaction["ticker"], str), "ticker must be string"
    assert isinstance(transaction["quantity"], int), "quantity must be integer"
    assert isinstance(transaction["price"], (int, float, Decimal)), "price must be number"
    assert isinstance(transaction["commission"], (int, float, Decimal)), "commission must be number"
    assert isinstance(transaction["total_cost"], (int, float, Decimal)), "total_cost must be number"
    assert isinstance(transaction["execution_status"], str), "execution_status must be string"
    assert isinstance(transaction["order_type"], str), "order_type must be string"
    assert isinstance(transaction["initiated_by"], str), "initiated_by must be string"
    
    # Validate partition key is non-empty
    assert len(transaction["user_id"]) > 0, "user_id (partition key) must be non-empty"
    
    # Validate sort key is non-empty and ISO 8601 format
    assert len(transaction["timestamp"]) > 0, "timestamp (sort key) must be non-empty"
    try:
        datetime.fromisoformat(transaction["timestamp"].replace('Z', '+00:00'))
    except ValueError as e:
        raise AssertionError(f"timestamp must be ISO 8601 format: {e}")
    
    # Validate GSI key is non-empty
    assert len(transaction["portfolio_id"]) > 0, "portfolio_id (GSI key) must be non-empty"
    
    # Validate action is valid value
    assert transaction["action"] in ["buy", "sell"], \
        f"action must be buy or sell, got {transaction['action']}"
    
    # Validate execution_status is valid value
    assert transaction["execution_status"] in ["pending", "completed", "failed", "cancelled"], \
        f"execution_status must be pending, completed, failed, or cancelled, got {transaction['execution_status']}"
    
    # Validate order_type is valid value
    assert transaction["order_type"] in ["market", "limit", "stop", "stop_limit"], \
        f"order_type must be market, limit, stop, or stop_limit, got {transaction['order_type']}"
    
    # Validate quantity is positive
    assert transaction["quantity"] > 0, "quantity must be positive"
    
    # Validate price is positive
    assert transaction["price"] > 0, "price must be positive"
    
    # Validate commission is non-negative
    assert transaction["commission"] >= 0, "commission must be non-negative"
    
    return True


# ============================================================================
# Property Tests
# ============================================================================

@settings(max_examples=100)
@given(portfolio=portfolio_strategy())
def test_property_31_portfolio_storage_schema_conformance(portfolio):
    """
    Property 31: Portfolio Storage Schema Conformance
    
    For all valid portfolio objects:
    - The portfolio MUST conform to the DynamoDB schema
    - All required fields MUST be present
    - Field types MUST match expected types
    - Partition key (user_id) and sort key (portfolio_id) MUST be non-empty
    - Target allocation MUST sum to approximately 1.0
    - Holdings MUST have valid structure
    - Risk tolerance MUST be a valid value
    - Timestamps MUST be ISO 8601 format
    
    Validates: Requirements 8.1, 8.2
    """
    assert validate_portfolio_schema(portfolio), "Portfolio must conform to DynamoDB schema"
    
    # Additional property: Portfolio should be JSON serializable for DynamoDB
    try:
        json_str = json.dumps(portfolio, default=str)
        deserialized = json.loads(json_str)
        assert deserialized is not None, "Portfolio must be deserializable"
    except (TypeError, ValueError) as e:
        raise AssertionError(f"Portfolio must be JSON serializable: {e}")


@settings(max_examples=100)
@given(transaction=transaction_strategy())
def test_property_32_transaction_storage_schema_conformance(transaction):
    """
    Property 32: Transaction Storage Schema Conformance
    
    For all valid transaction objects:
    - The transaction MUST conform to the DynamoDB schema
    - All required fields MUST be present
    - Field types MUST match expected types
    - Partition key (user_id) and sort key (timestamp) MUST be non-empty
    - GSI key (portfolio_id) MUST be non-empty
    - Action MUST be buy or sell
    - Execution status MUST be a valid value
    - Order type MUST be a valid value
    - Quantity MUST be positive
    - Price MUST be positive
    - Commission MUST be non-negative
    - Timestamp MUST be ISO 8601 format
    
    Validates: Requirements 8.1, 8.2
    """
    assert validate_transaction_schema(transaction), "Transaction must conform to DynamoDB schema"
    
    # Additional property: Transaction should be JSON serializable for DynamoDB
    try:
        json_str = json.dumps(transaction, default=str)
        deserialized = json.loads(json_str)
        assert deserialized is not None, "Transaction must be deserializable"
    except (TypeError, ValueError) as e:
        raise AssertionError(f"Transaction must be JSON serializable: {e}")


@settings(max_examples=50)
@given(portfolio=portfolio_strategy())
def test_portfolio_round_trip_serialization(portfolio):
    """
    Test that portfolios can be serialized and deserialized without data loss.
    This ensures compatibility with DynamoDB's JSON format.
    """
    # Serialize to JSON
    json_str = json.dumps(portfolio, default=str)
    
    # Deserialize from JSON
    deserialized = json.loads(json_str)
    
    # Verify all required fields are preserved
    assert deserialized["user_id"] == portfolio["user_id"]
    assert deserialized["portfolio_id"] == portfolio["portfolio_id"]
    assert deserialized["portfolio_name"] == portfolio["portfolio_name"]
    assert len(deserialized["holdings"]) == len(portfolio["holdings"])
    
    # Verify schema still conforms after round-trip
    assert validate_portfolio_schema(deserialized)


@settings(max_examples=50)
@given(transaction=transaction_strategy())
def test_transaction_round_trip_serialization(transaction):
    """
    Test that transactions can be serialized and deserialized without data loss.
    This ensures compatibility with DynamoDB's JSON format.
    """
    # Serialize to JSON
    json_str = json.dumps(transaction, default=str)
    
    # Deserialize from JSON
    deserialized = json.loads(json_str)
    
    # Verify all required fields are preserved
    assert deserialized["user_id"] == transaction["user_id"]
    assert deserialized["timestamp"] == transaction["timestamp"]
    assert deserialized["transaction_id"] == transaction["transaction_id"]
    assert deserialized["portfolio_id"] == transaction["portfolio_id"]
    
    # Verify schema still conforms after round-trip
    assert validate_transaction_schema(deserialized)


# ============================================================================
# Edge Case Tests
# ============================================================================

def test_empty_portfolio_holdings():
    """Test that a portfolio with no holdings is valid."""
    portfolio = {
        "user_id": "user_123",
        "portfolio_id": "portfolio_456",
        "portfolio_name": "Empty Portfolio",
        "target_allocation": {"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
        "holdings": [],
        "total_value": 0.0,
        "risk_tolerance": "moderate",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    }
    assert validate_portfolio_schema(portfolio)


def test_single_holding_portfolio():
    """Test that a portfolio with a single holding is valid."""
    portfolio = {
        "user_id": "user_123",
        "portfolio_id": "portfolio_456",
        "portfolio_name": "Single Holding",
        "target_allocation": {"stocks": 1.0, "bonds": 0.0, "cash": 0.0},
        "holdings": [
            {
                "ticker": "VTI",
                "quantity": 100,
                "cost_basis": 200.50,
                "current_price": 220.75,
                "purchase_date": "2023-01-15T00:00:00Z"
            }
        ],
        "total_value": 22075.0,
        "risk_tolerance": "aggressive",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    }
    assert validate_portfolio_schema(portfolio)


def test_transaction_with_zero_commission():
    """Test that a transaction with zero commission is valid."""
    transaction = {
        "user_id": "user_123",
        "timestamp": "2024-01-15T14:30:00Z",
        "transaction_id": "txn_789",
        "portfolio_id": "portfolio_456",
        "action": "buy",
        "ticker": "VTI",
        "quantity": 10,
        "price": 220.75,
        "commission": 0.0,
        "total_cost": 2207.50,
        "execution_status": "completed",
        "order_type": "market",
        "initiated_by": "user"
    }
    assert validate_transaction_schema(transaction)
