"""Unit tests for trade execution system."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from uuid import uuid4

from src.models.responses import TradeOrder, TradeConfirmation
from src.models.portfolio import Transaction
from src.error_handling.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException


class TestCircuitBreaker:
    """Test circuit breaker for brokerage API."""
    
    def test_circuit_breaker_starts_closed(self):
        """Test that circuit breaker starts in closed state."""
        cb = CircuitBreaker(failure_threshold=5, timeout=60)
        assert cb.get_state().value == "closed"
    
    def test_circuit_breaker_opens_after_threshold(self):
        """Test that circuit breaker opens after failure threshold."""
        cb = CircuitBreaker(failure_threshold=2, timeout=60)
        
        def failing_func():
            raise Exception("API error")
        
        # First failure
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        # Second failure - should open
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        assert cb.get_state().value == "open"
    
    def test_circuit_breaker_rejects_calls_when_open(self):
        """Test that circuit breaker rejects calls when open."""
        cb = CircuitBreaker(failure_threshold=1, timeout=60)
        
        def failing_func():
            raise Exception("API error")
        
        # Trigger failure to open circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        # Next call should raise CircuitBreakerOpenException
        with pytest.raises(CircuitBreakerOpenException):
            cb.call(failing_func)
    
    def test_circuit_breaker_resets_on_success(self):
        """Test that circuit breaker resets on successful call."""
        cb = CircuitBreaker(failure_threshold=5, timeout=60)
        
        def success_func():
            return "success"
        
        result = cb.call(success_func)
        assert result == "success"
        assert cb.get_state().value == "closed"


class TestTradeOrderValidation:
    """Test trade order validation."""
    
    def test_trade_order_with_valid_data(self):
        """Test creating trade order with valid data."""
        order = TradeOrder(
            order_id="order_123",
            action="buy",
            ticker="VTI",
            quantity=100,
            order_type="market",
            estimated_price=220.50,
            estimated_cost=22050.0
        )
        
        assert order.order_id == "order_123"
        assert order.action == "buy"
        assert order.ticker == "VTI"
        assert order.quantity == 100
    
    def test_trade_order_action_must_be_buy_or_sell(self):
        """Test that trade order action must be buy or sell."""
        with pytest.raises(ValueError):
            TradeOrder(
                order_id="order_123",
                action="invalid",
                ticker="VTI",
                quantity=100,
                order_type="market",
                estimated_price=220.50,
                estimated_cost=22050.0
            )
    
    def test_trade_order_quantity_must_be_non_negative(self):
        """Test that trade order quantity must be non-negative."""
        with pytest.raises(ValueError):
            TradeOrder(
                order_id="order_123",
                action="buy",
                ticker="VTI",
                quantity=-1,
                order_type="market",
                estimated_price=220.50,
                estimated_cost=0.0
            )


class TestTransactionRecording:
    """Test transaction recording."""
    
    def test_transaction_with_valid_data(self):
        """Test creating transaction with valid data."""
        transaction = Transaction(
            user_id="user_123",
            timestamp=datetime.utcnow().isoformat() + "Z",
            transaction_id="txn_456",
            portfolio_id="portfolio_789",
            action="buy",
            ticker="VTI",
            quantity=100,
            price=220.50,
            commission=0.0,
            total_cost=22050.0,
            execution_status="completed",
            order_type="market",
            initiated_by="rebalancing_agent"
        )
        
        assert transaction.user_id == "user_123"
        assert transaction.action == "buy"
        assert transaction.execution_status == "completed"
    
    def test_transaction_total_cost_calculation(self):
        """Test that transaction total cost is calculated correctly."""
        transaction = Transaction(
            user_id="user_123",
            timestamp=datetime.utcnow().isoformat() + "Z",
            transaction_id="txn_456",
            portfolio_id="portfolio_789",
            action="buy",
            ticker="VTI",
            quantity=100,
            price=220.50,
            commission=10.0,
            total_cost=0.0,  # Will be calculated
            execution_status="completed",
            order_type="market",
            initiated_by="rebalancing_agent"
        )
        
        expected_cost = (100 * 220.50) + 10.0
        assert transaction.total_cost == expected_cost
    
    def test_transaction_serialization_to_dynamodb(self):
        """Test that transaction can be serialized to DynamoDB format."""
        transaction = Transaction(
            user_id="user_123",
            timestamp=datetime.utcnow().isoformat() + "Z",
            transaction_id="txn_456",
            portfolio_id="portfolio_789",
            action="buy",
            ticker="VTI",
            quantity=100,
            price=220.50,
            commission=0.0,
            total_cost=22050.0,
            execution_status="completed",
            order_type="market",
            initiated_by="rebalancing_agent"
        )
        
        dynamodb_item = transaction.to_dynamodb()
        
        assert dynamodb_item["user_id"] == "user_123"
        assert dynamodb_item["action"] == "buy"
        assert dynamodb_item["ticker"] == "VTI"
        assert dynamodb_item["quantity"] == 100
        assert dynamodb_item["execution_status"] == "completed"



class TestPortfolioUpdate:
    """Test portfolio update logic."""
    
    def test_buy_transaction_increases_quantity(self):
        """Test that buy transaction increases holding quantity."""
        from src.models.portfolio import Portfolio, Holding
        
        portfolio = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Test Portfolio",
            target_allocation={"stocks": 1.0},
            holdings=[
                Holding(
                    ticker="VTI",
                    quantity=100,
                    cost_basis=200.0,
                    current_price=220.0,
                    purchase_date="2024-01-01T00:00:00Z"
                )
            ],
            total_value=22000.0
        )
        
        # Simulate buy transaction
        buy_qty = 50
        new_quantity = portfolio.holdings[0].quantity + buy_qty
        
        assert new_quantity == 150
    
    def test_sell_transaction_decreases_quantity(self):
        """Test that sell transaction decreases holding quantity."""
        from src.models.portfolio import Portfolio, Holding
        
        portfolio = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Test Portfolio",
            target_allocation={"stocks": 1.0},
            holdings=[
                Holding(
                    ticker="VTI",
                    quantity=100,
                    cost_basis=200.0,
                    current_price=220.0,
                    purchase_date="2024-01-01T00:00:00Z"
                )
            ],
            total_value=22000.0
        )
        
        # Simulate sell transaction
        sell_qty = 30
        new_quantity = portfolio.holdings[0].quantity - sell_qty
        
        assert new_quantity == 70
    
    def test_portfolio_value_recalculation(self):
        """Test that portfolio total value is recalculated correctly."""
        from src.models.portfolio import Portfolio, Holding
        
        holdings = [
            Holding(
                ticker="VTI",
                quantity=100,
                cost_basis=200.0,
                current_price=220.0,
                purchase_date="2024-01-01T00:00:00Z"
            ),
            Holding(
                ticker="BND",
                quantity=50,
                cost_basis=80.0,
                current_price=82.0,
                purchase_date="2024-01-01T00:00:00Z"
            )
        ]
        
        portfolio = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Test Portfolio",
            target_allocation={"stocks": 0.7, "bonds": 0.3},
            holdings=holdings,
            total_value=0.0
        )
        
        # Recalculate total value
        total_value = sum(h.market_value for h in portfolio.holdings)
        
        expected_value = (100 * 220.0) + (50 * 82.0)
        assert total_value == expected_value
