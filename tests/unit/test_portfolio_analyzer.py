"""Unit tests for Portfolio Analyzer Agent."""

import pytest
import json
import sys
import os
import importlib.util
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import sys
import os
import importlib.util

# Load the handler module directly
handler_path = os.path.join(os.path.dirname(__file__), '../../lambda/portfolio-analyzer/handler.py')
spec = importlib.util.spec_from_file_location("portfolio_analyzer_handler", handler_path)
handler_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler_module)

PortfolioAnalyzer = handler_module.PortfolioAnalyzer
lambda_handler = handler_module.lambda_handler

from src.models.portfolio import Portfolio, Holding
from src.models.responses import (
    AnalysisReport,
    PerformanceMetrics,
    RiskMetrics,
    AllocationDrift,
    MarketInsight,
)


@pytest.fixture
def sample_portfolio():
    """Create a sample portfolio for testing."""
    return Portfolio(
        user_id="user_123",
        portfolio_id="portfolio_456",
        portfolio_name="Test Portfolio",
        target_allocation={"stocks": 0.60, "bonds": 0.30, "cash": 0.10},
        holdings=[
            Holding(
                ticker="VTI",
                quantity=100,
                cost_basis=200.0,
                current_price=220.0,
                purchase_date="2023-01-15"
            ),
            Holding(
                ticker="BND",
                quantity=50,
                cost_basis=80.0,
                current_price=78.0,
                purchase_date="2023-02-20"
            ),
        ],
        total_value=24900.0,
        risk_tolerance="moderate"
    )


@pytest.fixture
def analyzer():
    """Create a PortfolioAnalyzer instance with mocked dependencies."""
    analyzer = PortfolioAnalyzer()
    analyzer.portfolio_tool = Mock()
    analyzer.market_data_tool = Mock()
    analyzer.bedrock_client = Mock()
    return analyzer


class TestPortfolioAnalyzerPerformanceMetrics:
    """Test performance metrics calculation."""
    
    def test_calculate_performance_metrics_with_holdings(self, analyzer, sample_portfolio):
        """Test performance metrics calculation with holdings."""
        metrics = analyzer._calculate_performance_metrics(sample_portfolio)
        
        assert isinstance(metrics, PerformanceMetrics)
        assert metrics.total_return > 0  # Portfolio has gains
        assert metrics.annualized_return >= 0
        assert metrics.sharpe_ratio >= 0
        assert metrics.max_drawdown <= 0
    
    def test_calculate_performance_metrics_empty_portfolio(self, analyzer):
        """Test performance metrics for empty portfolio."""
        empty_portfolio = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Empty Portfolio",
            target_allocation={"stocks": 1.0},
            holdings=[],
            total_value=0.0
        )
        
        metrics = analyzer._calculate_performance_metrics(empty_portfolio)
        
        assert metrics.total_return == 0.0
        assert metrics.annualized_return == 0.0
        assert metrics.sharpe_ratio == 0.0
        assert metrics.max_drawdown == 0.0
    
    def test_calculate_performance_metrics_zero_cost_basis(self, analyzer):
        """Test performance metrics when cost basis is zero."""
        portfolio = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Test Portfolio",
            target_allocation={"stocks": 1.0},
            holdings=[
                Holding(
                    ticker="VTI",
                    quantity=100,
                    cost_basis=0.0,
                    current_price=220.0,
                    purchase_date="2023-01-15"
                )
            ],
            total_value=22000.0
        )
        
        metrics = analyzer._calculate_performance_metrics(portfolio)
        
        assert metrics.total_return == 0.0


class TestPortfolioAnalyzerRiskMetrics:
    """Test risk metrics calculation."""
    
    def test_calculate_risk_metrics_with_holdings(self, analyzer, sample_portfolio):
        """Test risk metrics calculation with holdings."""
        metrics = analyzer._calculate_risk_metrics(sample_portfolio)
        
        assert isinstance(metrics, RiskMetrics)
        assert metrics.portfolio_volatility >= 0
        assert metrics.beta >= 0
        assert metrics.var_95 <= 0
        assert len(metrics.concentration_risk) > 0
    
    def test_calculate_risk_metrics_concentration(self, analyzer, sample_portfolio):
        """Test concentration risk calculation."""
        metrics = analyzer._calculate_risk_metrics(sample_portfolio)
        
        # Check that concentration risk sums to approximately 1.0
        total_concentration = sum(metrics.concentration_risk.values())
        assert abs(total_concentration - 1.0) < 0.01
    
    def test_calculate_risk_metrics_empty_portfolio(self, analyzer):
        """Test risk metrics for empty portfolio."""
        empty_portfolio = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Empty Portfolio",
            target_allocation={"stocks": 1.0},
            holdings=[]
        )
        
        metrics = analyzer._calculate_risk_metrics(empty_portfolio)
        
        assert metrics.portfolio_volatility == 0.0
        assert metrics.beta == 1.0
        assert metrics.var_95 == 0.0
        assert len(metrics.concentration_risk) == 0


class TestPortfolioAnalyzerAllocationDrift:
    """Test allocation drift calculation."""
    
    def test_calculate_allocation_drift_within_threshold(self, analyzer, sample_portfolio):
        """Test allocation drift when within rebalancing threshold."""
        drift = analyzer._calculate_allocation_drift(sample_portfolio)
        
        assert isinstance(drift, AllocationDrift)
        assert len(drift.current_allocation) > 0
        assert len(drift.target_allocation) > 0
        assert len(drift.drift_percentage) > 0
        assert isinstance(drift.rebalancing_needed, bool)
    
    def test_calculate_allocation_drift_sums_to_one(self, analyzer, sample_portfolio):
        """Test that allocations sum to approximately 1.0."""
        drift = analyzer._calculate_allocation_drift(sample_portfolio)
        
        current_sum = sum(drift.current_allocation.values())
        target_sum = sum(drift.target_allocation.values())
        
        assert abs(current_sum - 1.0) < 0.01
        assert abs(target_sum - 1.0) < 0.01
    
    def test_calculate_allocation_drift_empty_portfolio(self, analyzer):
        """Test allocation drift for empty portfolio."""
        empty_portfolio = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Empty Portfolio",
            target_allocation={"stocks": 0.6, "bonds": 0.4},
            holdings=[]
        )
        
        drift = analyzer._calculate_allocation_drift(empty_portfolio)
        
        # For empty portfolio, current allocation should match target
        assert drift.current_allocation == empty_portfolio.target_allocation
        # All drifts should be 0
        for value in drift.drift_percentage.values():
            assert value == 0.0


class TestPortfolioAnalyzerMarketContext:
    """Test market context retrieval."""
    
    def test_query_market_context_success(self, analyzer, sample_portfolio):
        """Test successful market context retrieval."""
        # Mock market data tool
        mock_market_data = [
            Mock(
                title="Tech Rally",
                content="Technology stocks rallying",
                ticker="VTI",
                sector="technology",
                timestamp="2024-01-15T10:00:00Z",
                source="news_api",
                similarity_score=0.95
            )
        ]
        
        analyzer.market_data_tool.execute = Mock(return_value=mock_market_data)
        
        context = analyzer._query_market_context(sample_portfolio)
        
        assert isinstance(context, list)
        assert len(context) > 0
        assert all(isinstance(item, MarketInsight) for item in context)
    
    def test_query_market_context_empty_portfolio(self, analyzer):
        """Test market context for empty portfolio."""
        empty_portfolio = Portfolio(
            user_id="user_123",
            portfolio_id="portfolio_456",
            portfolio_name="Empty Portfolio",
            target_allocation={"stocks": 1.0},
            holdings=[]
        )
        
        context = analyzer._query_market_context(empty_portfolio)
        
        assert isinstance(context, list)
        assert len(context) == 0
    
    def test_query_market_context_handles_errors(self, analyzer, sample_portfolio):
        """Test that market context retrieval handles errors gracefully."""
        analyzer.market_data_tool.execute = Mock(side_effect=Exception("API Error"))
        
        context = analyzer._query_market_context(sample_portfolio)
        
        # Should return empty list on error
        assert isinstance(context, list)


class TestPortfolioAnalyzerRecommendations:
    """Test recommendation generation."""
    
    def test_build_analysis_prompt(self, analyzer, sample_portfolio):
        """Test prompt building for Bedrock."""
        performance_metrics = PerformanceMetrics(
            total_return=0.10,
            annualized_return=0.10,
            sharpe_ratio=1.5,
            max_drawdown=-0.05
        )
        risk_metrics = RiskMetrics(
            portfolio_volatility=0.12,
            beta=1.0,
            var_95=-0.02,
            concentration_risk={"VTI": 0.88, "BND": 0.12}
        )
        allocation_drift = AllocationDrift(
            current_allocation={"stocks": 0.88, "bonds": 0.12},
            target_allocation={"stocks": 0.60, "bonds": 0.30, "cash": 0.10},
            drift_percentage={"stocks": 0.28, "bonds": 0.18, "cash": 0.10},
            rebalancing_needed=True
        )
        
        prompt = analyzer._build_analysis_prompt(
            sample_portfolio,
            performance_metrics,
            risk_metrics,
            allocation_drift,
            []
        )
        
        assert isinstance(prompt, str)
        assert "VTI" in prompt
        assert "BND" in prompt
        assert "10.00%" in prompt
    
    def test_parse_recommendations(self, analyzer):
        """Test parsing recommendations from Bedrock response."""
        response = """Here are my recommendations:

1. Rebalance your portfolio to match target allocation
2. Consider increasing bond allocation for stability
3. Monitor technology sector concentration
4. Review quarterly performance metrics"""
        
        recommendations = analyzer._parse_recommendations(response)
        
        assert isinstance(recommendations, list)
        assert len(recommendations) > 0
        assert all(isinstance(rec, str) for rec in recommendations)
    
    def test_parse_recommendations_with_bullets(self, analyzer):
        """Test parsing recommendations with bullet points."""
        response = """- Rebalance portfolio
- Increase bond allocation
- Monitor concentration"""
        
        recommendations = analyzer._parse_recommendations(response)
        
        assert len(recommendations) >= 3


class TestPortfolioAnalyzerIntegration:
    """Integration tests for Portfolio Analyzer."""
    
    def test_analyze_complete_workflow(self, sample_portfolio):
        """Test complete analysis workflow."""
        # Setup mocks
        analyzer = PortfolioAnalyzer()
        analyzer.portfolio_tool = Mock()
        analyzer.portfolio_tool.execute.return_value = sample_portfolio
        analyzer.market_data_tool = Mock()
        analyzer.market_data_tool.execute.return_value = []
        analyzer.bedrock_client = Mock()
        analyzer.bedrock_client.invoke_model.return_value = {
            "body": MagicMock(read=lambda: json.dumps({
                "content": [{"text": "Recommendation 1\nRecommendation 2"}]
            }))
        }
        
        report = analyzer.analyze("user_123", "portfolio_456")
        
        assert isinstance(report, AnalysisReport)
        assert report.portfolio_id == "portfolio_456"
        assert report.performance_metrics is not None
        assert report.risk_metrics is not None
        assert report.allocation_drift is not None
        assert len(report.recommendations) > 0


class TestLambdaHandler:
    """Test Lambda handler function."""
    
    def test_lambda_handler_success(self):
        """Test successful Lambda handler invocation."""
        # Setup mock
        with patch.object(PortfolioAnalyzer, 'analyze') as mock_analyze:
            mock_report = Mock()
            mock_report.portfolio_id = "portfolio_456"
            mock_report.timestamp = "2024-01-15T10:00:00Z"
            mock_report.performance_metrics = Mock(
                total_return=0.10,
                annualized_return=0.10,
                sharpe_ratio=1.5,
                max_drawdown=-0.05
            )
            mock_report.risk_metrics = Mock(
                portfolio_volatility=0.12,
                beta=1.0,
                var_95=-0.02,
                concentration_risk={}
            )
            mock_report.allocation_drift = Mock(
                current_allocation={},
                target_allocation={},
                drift_percentage={},
                rebalancing_needed=False
            )
            mock_report.market_context = []
            mock_report.recommendations = ["Recommendation 1"]
            
            mock_analyze.return_value = mock_report
            
            event = {
                "user_id": "user_123",
                "portfolio_id": "portfolio_456",
                "analysis_type": "comprehensive"
            }
            
            response = lambda_handler(event, None)
            
            assert response["statusCode"] == 200
            body = json.loads(response["body"])
            assert body["status"] == "success"
            assert body["portfolio_id"] == "portfolio_456"
    
    def test_lambda_handler_missing_parameters(self):
        """Test Lambda handler with missing parameters."""
        event = {"user_id": "user_123"}  # Missing portfolio_id
        
        response = lambda_handler(event, None)
        
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["status"] == "error"
        assert body["error_code"] == "VALIDATION_ERROR"
    
    @patch.object(PortfolioAnalyzer, 'analyze')
    def test_lambda_handler_portfolio_not_found(self, mock_analyze):
        """Test Lambda handler when portfolio not found."""
        mock_analyze.side_effect = ValueError("Portfolio not found")
        
        event = {
            "user_id": "user_123",
            "portfolio_id": "nonexistent"
        }
        
        response = lambda_handler(event, None)
        
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["status"] == "error"
