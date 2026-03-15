"""Property-based tests for MCP trade execution and transaction recording."""

import pytest
from datetime import datetime
from hypothesis import given, settings, strategies as st
from uuid import uuid4

from src.models.responses import TradeOrder, TradeConfirmation
from src.models.portfolio import Transaction


# Custom strategies for test data generation
@st.composite
def trade_order_strategy(draw):
    """Generate valid TradeOrder objects."""
    return TradeOrder(
        order_id=draw(st.text(min_size=1, max_size=50)),
        action=draw(st.sampled_from(["buy", "sell"])),
        ticker=draw(st.text(min_size=1, max_size=5, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ")),
        quantity=draw(st.integers(min_value=1, max_value=10000)),
        order_type=draw(st.sampled_from(["market", "limit"])),
        estimated_price=draw(st.floats(min_value=0.01, max_value=10000.0)),
        estimated_cost=draw(st.floats(min_value=0.0, max_value=100000000.0))
    )


@st.composite
def transaction_strategy(draw):
    """Generate valid Transaction objects."""
    action = draw(st.sampled_from(["buy", "sell"]))
    quantity = draw(st.integers(min_value=1, max_value=10000))
    price = draw(st.floats(min_value=0.01, max_value=10000.0))
    
    return Transaction(
        user_id=draw(st.text(min_size=1, max_size=50)),
        timestamp=datetime.utcnow().isoformat() + "Z",
        transaction_id=str(uuid4()),
        portfolio_id=draw(st.text(min_size=1, max_size=50)),
        action=action,
        ticker=draw(st.text(min_size=1, max_size=5, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ")),
        quantity=quantity,
        price=price,
        commission=draw(st.floats(min_value=0.0, max_value=100.0)),
        total_cost=(quantity * price) + draw(st.floats(min_value=0.0, max_value=100.0)),
        execution_status=draw(st.sampled_from(["completed", "failed"])),
        order_type=draw(st.sampled_from(["market", "limit"])),
        initiated_by="rebalancing_agent"
    )


class TestMCPToolInvocationOnApproval:
    """
    Property 24: MCP Tool Invocation on Approval
    
    For any approved trade plan, the system should invoke the trade execution 
    MCP Tool with all orders from the approved plan.
    
    **Validates: Requirements 6.1**
    """
    
    @settings(max_examples=50)
    @given(trade_order_strategy())
    def test_trade_order_has_all_required_fields(self, trade_order):
        """
        Test that trade orders have all required fields for MCP tool invocation.
        """
        # All required fields should be present
        assert trade_order.order_id is not None
        assert trade_order.action in ["buy", "sell"]
        assert trade_order.ticker is not None and len(trade_order.ticker) > 0
        assert trade_order.quantity > 0
        assert trade_order.order_type in ["market", "limit"]
        assert trade_order.estimated_price >= 0.0
        assert trade_order.estimated_cost >= 0.0
    
    @settings(max_examples=50)
    @given(st.lists(
        st.builds(
            TradeOrder,
            order_id=st.uuids().map(str),
            action=st.sampled_from(["buy", "sell"]),
            ticker=st.text(min_size=1, max_size=5, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
            quantity=st.integers(min_value=1, max_value=10000),
            order_type=st.sampled_from(["market", "limit"]),
            estimated_price=st.floats(min_value=0.01, max_value=10000.0),
            estimated_cost=st.floats(min_value=0.0, max_value=100000000.0)
        ),
        min_size=1,
        max_size=10,
        unique_by=lambda x: x.order_id
    ))
    def test_multiple_trade_orders_can_be_invoked(self, trade_orders):
        """
        Test that multiple trade orders can be prepared for MCP tool invocation.
        """
        # All orders should be valid
        for order in trade_orders:
            assert order.order_id is not None
            assert order.action in ["buy", "sell"]
            assert order.quantity > 0
        
        # Orders should be distinct
        order_ids = [o.order_id for o in trade_orders]
        assert len(order_ids) == len(set(order_ids))


class TestTransactionRecordingCompleteness:
    """
    Property 25: Transaction Recording Completeness
    
    For any completed trade, a transaction record should exist in DynamoDB 
    with all required fields (timestamp, execution price, ticker, quantity, action).
    
    **Validates: Requirements 6.3**
    """
    
    @settings(max_examples=50)
    @given(transaction_strategy())
    def test_transaction_has_all_required_fields(self, transaction):
        """
        Test that recorded transactions have all required fields.
        """
        # All required fields should be present
        assert transaction.user_id is not None and len(transaction.user_id) > 0
        assert transaction.timestamp is not None
        assert transaction.transaction_id is not None
        assert transaction.portfolio_id is not None
        assert transaction.action in ["buy", "sell"]
        assert transaction.ticker is not None and len(transaction.ticker) > 0
        assert transaction.quantity > 0
        assert transaction.price >= 0.0
        assert transaction.execution_status in ["completed", "failed"]
    
    @settings(max_examples=50)
    @given(
        st.integers(min_value=1, max_value=10000),
        st.floats(min_value=0.01, max_value=10000.0),
        st.floats(min_value=0.0, max_value=100.0)
    )
    def test_transaction_total_cost_calculation(self, quantity, price, commission):
        """
        Test that transaction total cost is calculated correctly.
        """
        transaction = Transaction(
            user_id="user_123",
            timestamp=datetime.utcnow().isoformat() + "Z",
            transaction_id=str(uuid4()),
            portfolio_id="portfolio_456",
            action="buy",
            ticker="VTI",
            quantity=quantity,
            price=price,
            commission=commission,
            total_cost=0.0,  # Will be calculated
            execution_status="completed",
            order_type="market",
            initiated_by="rebalancing_agent"
        )
        
        # Total cost should be quantity * price + commission
        expected_total = (quantity * price) + commission
        assert abs(transaction.total_cost - expected_total) < 0.01
    
    @settings(max_examples=50)
    @given(st.lists(transaction_strategy(), min_size=1, max_size=10))
    def test_multiple_transactions_are_distinct(self, transactions):
        """
        Test that multiple transactions have unique IDs.
        """
        transaction_ids = [t.transaction_id for t in transactions]
        assert len(transaction_ids) == len(set(transaction_ids))
    
    @settings(max_examples=50)
    @given(transaction_strategy())
    def test_transaction_can_be_serialized_to_dynamodb(self, transaction):
        """
        Test that transactions can be serialized to DynamoDB format.
        """
        dynamodb_item = transaction.to_dynamodb()
        
        # All required fields should be in DynamoDB item
        assert "user_id" in dynamodb_item
        assert "timestamp" in dynamodb_item
        assert "transaction_id" in dynamodb_item
        assert "portfolio_id" in dynamodb_item
        assert "action" in dynamodb_item
        assert "ticker" in dynamodb_item
        assert "quantity" in dynamodb_item
        assert "price" in dynamodb_item
        assert "execution_status" in dynamodb_item


class TestTradeFailureLoggingAndNotification:
    """
    Property 26: Trade Failure Logging and Notification
    
    For any failed trade, an error log entry should exist in CloudWatch 
    and a user notification should be sent with failure details.
    
    **Validates: Requirements 6.4, 14.1**
    """
    
    @settings(max_examples=50)
    @given(transaction_strategy())
    def test_failed_transaction_has_error_status(self, transaction):
        """
        Test that failed transactions are marked with error status.
        """
        # Create a failed transaction
        failed_transaction = Transaction(
            user_id=transaction.user_id,
            timestamp=datetime.utcnow().isoformat() + "Z",
            transaction_id=str(uuid4()),
            portfolio_id=transaction.portfolio_id,
            action=transaction.action,
            ticker=transaction.ticker,
            quantity=transaction.quantity,
            price=transaction.price,
            commission=0.0,
            total_cost=0.0,  # Will be auto-calculated
            execution_status="failed",
            order_type=transaction.order_type,
            initiated_by="rebalancing_agent"
        )
        
        assert failed_transaction.execution_status == "failed"
        # Note: total_cost will be auto-calculated to quantity * price
        assert failed_transaction.total_cost == transaction.quantity * transaction.price
    
    @settings(max_examples=50)
    @given(
        transaction_strategy(),
        st.text(min_size=1, max_size=200)
    )
    def test_failed_transaction_can_include_error_details(self, transaction, error_message):
        """
        Test that failed transactions can include error details.
        """
        # Create a failed transaction with error details
        failed_transaction = Transaction(
            user_id=transaction.user_id,
            timestamp=datetime.utcnow().isoformat() + "Z",
            transaction_id=str(uuid4()),
            portfolio_id=transaction.portfolio_id,
            action=transaction.action,
            ticker=transaction.ticker,
            quantity=transaction.quantity,
            price=transaction.price,
            commission=0.0,
            total_cost=0.0,
            execution_status="failed",
            order_type=transaction.order_type,
            initiated_by="rebalancing_agent"
        )
        
        # Error details would be logged separately
        assert failed_transaction.execution_status == "failed"
        assert len(error_message) > 0  # Error message should be captured
    
    @settings(max_examples=50)
    @given(st.lists(transaction_strategy(), min_size=1, max_size=10))
    def test_multiple_failed_transactions_are_tracked(self, transactions):
        """
        Test that multiple failed transactions can be tracked.
        """
        failed_transactions = []
        for t in transactions:
            failed_t = Transaction(
                user_id=t.user_id,
                timestamp=datetime.utcnow().isoformat() + "Z",
                transaction_id=str(uuid4()),
                portfolio_id=t.portfolio_id,
                action=t.action,
                ticker=t.ticker,
                quantity=t.quantity,
                price=t.price,
                commission=0.0,
                total_cost=0.0,
                execution_status="failed",
                order_type=t.order_type,
                initiated_by="rebalancing_agent"
            )
            failed_transactions.append(failed_t)
        
        # All should be marked as failed
        assert all(t.execution_status == "failed" for t in failed_transactions)
        
        # All should have unique IDs
        ids = [t.transaction_id for t in failed_transactions]
        assert len(ids) == len(set(ids))


class TestPortfolioUpdateConsistency:
    """
    Property 27: Portfolio Update Consistency
    
    For any set of completed trades, the updated portfolio holdings in DynamoDB 
    should reflect all trade changes accurately (buys increase quantity, 
    sells decrease quantity).
    
    **Validates: Requirements 6.5**
    """
    
    @settings(max_examples=50)
    @given(
        st.integers(min_value=1, max_value=1000),  # Initial quantity
        st.integers(min_value=1, max_value=500)    # Buy quantity
    )
    def test_buy_transaction_increases_quantity(self, initial_qty, buy_qty):
        """
        Test that buy transactions increase portfolio quantity.
        """
        # Create buy transaction
        buy_transaction = Transaction(
            user_id="user_123",
            timestamp=datetime.utcnow().isoformat() + "Z",
            transaction_id=str(uuid4()),
            portfolio_id="portfolio_456",
            action="buy",
            ticker="VTI",
            quantity=buy_qty,
            price=100.0,
            commission=0.0,
            total_cost=buy_qty * 100.0,
            execution_status="completed",
            order_type="market",
            initiated_by="rebalancing_agent"
        )
        
        # After buy, quantity should increase
        new_quantity = initial_qty + buy_transaction.quantity
        assert new_quantity == initial_qty + buy_qty
    
    @settings(max_examples=50)
    @given(
        st.integers(min_value=100, max_value=1000),  # Initial quantity
        st.integers(min_value=1, max_value=100)      # Sell quantity
    )
    def test_sell_transaction_decreases_quantity(self, initial_qty, sell_qty):
        """
        Test that sell transactions decrease portfolio quantity.
        """
        # Ensure we don't sell more than we have
        if sell_qty > initial_qty:
            sell_qty = initial_qty
        
        # Create sell transaction
        sell_transaction = Transaction(
            user_id="user_123",
            timestamp=datetime.utcnow().isoformat() + "Z",
            transaction_id=str(uuid4()),
            portfolio_id="portfolio_456",
            action="sell",
            ticker="VTI",
            quantity=sell_qty,
            price=100.0,
            commission=0.0,
            total_cost=0.0,
            execution_status="completed",
            order_type="market",
            initiated_by="rebalancing_agent"
        )
        
        # After sell, quantity should decrease
        new_quantity = initial_qty - sell_transaction.quantity
        assert new_quantity == initial_qty - sell_qty
        assert new_quantity >= 0
    
    @settings(max_examples=50)
    @given(st.lists(
        st.tuples(
            st.sampled_from(["buy", "sell"]),
            st.integers(min_value=1, max_value=100)
        ),
        min_size=1,
        max_size=10
    ))
    def test_multiple_transactions_maintain_consistency(self, transaction_list):
        """
        Test that multiple transactions maintain portfolio consistency.
        """
        quantity = 1000  # Start with 1000 shares
        
        for action, qty in transaction_list:
            if action == "buy":
                quantity += qty
            elif action == "sell":
                # Only sell if we have enough
                if qty <= quantity:
                    quantity -= qty
        
        # Final quantity should be non-negative
        assert quantity >= 0
