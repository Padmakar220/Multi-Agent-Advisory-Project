"""Property-based tests for portfolio MCP tools.

Feature: multi-agent-advisory-ai-system
"""

import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import Mock, MagicMock, patch
from decimal import Decimal
from datetime import datetime

from src.mcp_tools import GetPortfolioTool, GetCostBasisTool
from src.models.portfolio import Portfolio, Holding
from src.models.responses import CostBasisInfo


# Strategy for generating valid holdings
@st.composite
def holding_strategy(draw):
    """Generate valid Holding objects."""
    ticker = draw(st.text(min_size=1, max_size=5, alphabet=st.characters(whitelist_categories=('Lu',))))
    quantity = draw(st.integers(min_value=1, max_value=10000))
    cost_basis = draw(st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False))
    current_price = draw(st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False))
    purchase_date = draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2024, 12, 31))).isoformat()
    
    return Holding(
        ticker=ticker,
        quantity=quantity,
        cost_basis=cost_basis,
        current_price=current_price,
        purchase_date=purchase_date
    )


# Strategy for generating valid portfolios
@st.composite
def portfolio_strategy(draw):
    """Generate valid Portfolio objects."""
    user_id = draw(st.text(min_size=1, max_size=50))
    portfolio_id = draw(st.text(min_size=1, max_size=50))
    portfolio_name = draw(st.text(min_size=1, max_size=100))
    
    # Generate target allocation that sums to 1.0
    num_classes = draw(st.integers(min_value=2, max_value=5))
    allocations = draw(st.lists(
        st.floats(min_value=0.1, max_value=0.8),
        min_size=num_classes,
        max_size=num_classes
    ))
    total = sum(allocations)
    normalized = [a / total for a in allocations]
    
    asset_classes = ['stocks', 'bonds', 'cash', 'real_estate', 'commodities'][:num_classes]
    target_allocation = dict(zip(asset_classes, normalized))
    
    holdings = draw(st.lists(holding_strategy(), min_size=1, max_size=10))
    risk_tolerance = draw(st.sampled_from(['conservative', 'moderate', 'aggressive']))
    
    return Portfolio(
        user_id=user_id,
        portfolio_id=portfolio_id,
        portfolio_name=portfolio_name,
        target_allocation=target_allocation,
        holdings=holdings,
        risk_tolerance=risk_tolerance
    )


class TestGetPortfolioToolProperties:
    """Property-based tests for GetPortfolioTool."""
    
    @settings(max_examples=100)
    @given(portfolio=portfolio_strategy())
    def test_property_5_agent_data_retrieval_success(self, portfolio):
        """
        Property 5: Agent Data Retrieval Success
        
        For any valid request requiring data from DynamoDB (portfolio holdings),
        the agent should successfully retrieve the data and the retrieved data
        should match the stored data.
        
        **Validates: Requirements 2.1, 8.1**
        """
        # Mock DynamoDB table
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': portfolio.to_dynamodb()
        }
        
        # Create tool with mocked table
        tool = GetPortfolioTool()
        tool.table = mock_table
        
        # Execute retrieval
        retrieved_portfolio = tool.execute(portfolio.user_id, portfolio.portfolio_id)
        
        # Verify data matches
        assert retrieved_portfolio.user_id == portfolio.user_id
        assert retrieved_portfolio.portfolio_id == portfolio.portfolio_id
        assert retrieved_portfolio.portfolio_name == portfolio.portfolio_name
        assert retrieved_portfolio.risk_tolerance == portfolio.risk_tolerance
        assert len(retrieved_portfolio.holdings) == len(portfolio.holdings)
        
        # Verify target allocation matches
        for asset_class, allocation in portfolio.target_allocation.items():
            assert abs(retrieved_portfolio.target_allocation[asset_class] - allocation) < 0.0001
        
        # Verify holdings match
        for i, holding in enumerate(portfolio.holdings):
            retrieved_holding = retrieved_portfolio.holdings[i]
            assert retrieved_holding.ticker == holding.ticker
            assert retrieved_holding.quantity == holding.quantity
            assert abs(retrieved_holding.cost_basis - holding.cost_basis) < 0.01
            assert abs(retrieved_holding.current_price - holding.current_price) < 0.01
    
    @settings(max_examples=50, deadline=1000)
    @given(portfolio=portfolio_strategy())
    def test_property_33_portfolio_data_retrieval_performance(self, portfolio):
        """
        Property 33: Portfolio Data Retrieval Performance
        
        For any portfolio data request, the retrieval from DynamoDB should
        complete within 100 milliseconds.
        
        **Validates: Requirements 8.3**
        """
        import time
        
        # Mock DynamoDB table with realistic delay
        mock_table = Mock()
        
        def mock_get_item(**kwargs):
            # Simulate realistic DynamoDB latency (10-50ms)
            time.sleep(0.01)  # 10ms
            return {'Item': portfolio.to_dynamodb()}
        
        mock_table.get_item = mock_get_item
        
        # Create tool with mocked table
        tool = GetPortfolioTool()
        tool.table = mock_table
        
        # Measure retrieval time
        start_time = time.time()
        retrieved_portfolio = tool.execute(portfolio.user_id, portfolio.portfolio_id)
        end_time = time.time()
        
        retrieval_time_ms = (end_time - start_time) * 1000
        
        # Should complete within 100ms
        assert retrieval_time_ms < 100, \
            f"Portfolio retrieval took {retrieval_time_ms:.2f}ms, should be < 100ms"
        
        # Verify data was retrieved
        assert retrieved_portfolio.portfolio_id == portfolio.portfolio_id
    
    @settings(max_examples=100)
    @given(
        user_id=st.text(min_size=1, max_size=50),
        portfolio_id=st.text(min_size=1, max_size=50)
    )
    def test_property_portfolio_not_found_error(self, user_id, portfolio_id):
        """
        Property: Portfolio not found should raise ValueError.
        
        For any request for a non-existent portfolio, the tool should
        raise a ValueError with a descriptive message.
        """
        # Mock DynamoDB table returning no item
        mock_table = Mock()
        mock_table.get_item.return_value = {}
        
        # Create tool with mocked table
        tool = GetPortfolioTool()
        tool.table = mock_table
        
        # Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            tool.execute(user_id, portfolio_id)
        
        # Error message should mention portfolio not found
        assert "not found" in str(exc_info.value).lower()
        assert user_id in str(exc_info.value)
        assert portfolio_id in str(exc_info.value)


class TestGetCostBasisToolProperties:
    """Property-based tests for GetCostBasisTool."""
    
    @settings(max_examples=100)
    @given(portfolio=portfolio_strategy())
    def test_property_34_cost_basis_data_completeness(self, portfolio):
        """
        Property 34: Cost Basis Data Completeness
        
        For any security position in a portfolio, cost basis information
        should exist in DynamoDB with purchase date and cost per share.
        
        **Validates: Requirements 8.4**
        """
        # Select a random holding from the portfolio
        holding = portfolio.holdings[0]
        
        # Mock DynamoDB table
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': portfolio.to_dynamodb()
        }
        
        # Create tool with mocked table
        tool = GetCostBasisTool()
        tool.table = mock_table
        
        # Execute retrieval
        cost_basis_info = tool.execute(
            portfolio.user_id,
            portfolio.portfolio_id,
            holding.ticker
        )
        
        # Verify all required fields are present
        assert cost_basis_info.ticker == holding.ticker
        assert cost_basis_info.quantity == holding.quantity
        assert abs(cost_basis_info.cost_per_share - holding.cost_basis) < 0.01
        assert cost_basis_info.purchase_date == holding.purchase_date
        
        # Verify total cost basis is calculated correctly
        expected_total = holding.quantity * holding.cost_basis
        assert abs(cost_basis_info.total_cost_basis - expected_total) < 0.01
    
    @settings(max_examples=100)
    @given(
        portfolio=portfolio_strategy(),
        invalid_ticker=st.text(min_size=1, max_size=10)
    )
    def test_property_cost_basis_ticker_not_found(self, portfolio, invalid_ticker):
        """
        Property: Cost basis for non-existent ticker should raise ValueError.
        
        For any request for a ticker not in the portfolio, the tool should
        raise a ValueError.
        """
        # Ensure invalid_ticker is not in portfolio
        portfolio_tickers = {h.ticker for h in portfolio.holdings}
        if invalid_ticker in portfolio_tickers:
            return  # Skip this test case
        
        # Mock DynamoDB table
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': portfolio.to_dynamodb()
        }
        
        # Create tool with mocked table
        tool = GetCostBasisTool()
        tool.table = mock_table
        
        # Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            tool.execute(portfolio.user_id, portfolio.portfolio_id, invalid_ticker)
        
        # Error message should mention ticker not found
        assert "not found" in str(exc_info.value).lower()
        assert invalid_ticker in str(exc_info.value)
    
    @settings(max_examples=100)
    @given(portfolio=portfolio_strategy())
    def test_property_cost_basis_round_trip_consistency(self, portfolio):
        """
        Property: Cost basis retrieval should be consistent.
        
        For any portfolio, retrieving cost basis multiple times should
        return the same data.
        """
        holding = portfolio.holdings[0]
        
        # Mock DynamoDB table
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': portfolio.to_dynamodb()
        }
        
        # Create tool with mocked table
        tool = GetCostBasisTool()
        tool.table = mock_table
        
        # Retrieve cost basis multiple times
        result1 = tool.execute(portfolio.user_id, portfolio.portfolio_id, holding.ticker)
        result2 = tool.execute(portfolio.user_id, portfolio.portfolio_id, holding.ticker)
        result3 = tool.execute(portfolio.user_id, portfolio.portfolio_id, holding.ticker)
        
        # All results should be identical
        assert result1.ticker == result2.ticker == result3.ticker
        assert result1.quantity == result2.quantity == result3.quantity
        assert result1.cost_per_share == result2.cost_per_share == result3.cost_per_share
        assert result1.purchase_date == result2.purchase_date == result3.purchase_date
        assert result1.total_cost_basis == result2.total_cost_basis == result3.total_cost_basis


class TestMCPToolValidation:
    """Test input validation for MCP tools."""
    
    def test_get_portfolio_empty_user_id(self):
        """GetPortfolioTool should reject empty user_id."""
        tool = GetPortfolioTool()
        
        with pytest.raises(ValueError) as exc_info:
            tool.execute("", "portfolio_123")
        
        assert "user_id" in str(exc_info.value).lower()
        assert "empty" in str(exc_info.value).lower()
    
    def test_get_portfolio_empty_portfolio_id(self):
        """GetPortfolioTool should reject empty portfolio_id."""
        tool = GetPortfolioTool()
        
        with pytest.raises(ValueError) as exc_info:
            tool.execute("user_123", "")
        
        assert "portfolio_id" in str(exc_info.value).lower()
        assert "empty" in str(exc_info.value).lower()
    
    def test_get_cost_basis_empty_ticker(self):
        """GetCostBasisTool should reject empty ticker."""
        tool = GetCostBasisTool()
        
        with pytest.raises(ValueError) as exc_info:
            tool.execute("user_123", "portfolio_123", "")
        
        assert "ticker" in str(exc_info.value).lower()
        assert "empty" in str(exc_info.value).lower()
