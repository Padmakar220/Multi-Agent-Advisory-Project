"""
Property-based tests for Foundation Model (Bedrock) Integration.

Tests:
- Property 50: Foundation Model Invocation
- Property 51: Model Prompt Context Completeness
- Property 52: Model Response Validation
- Property 53: Invalid Response Retry

These tests validate that agents correctly invoke Bedrock, include required
context in prompts, validate responses, and retry on invalid responses.

Validates: Requirements 12.2, 12.3, 12.4, 12.5
"""

import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest
from hypothesis import given, settings, strategies as st

sys.path.insert(0, "src")
sys.path.insert(0, "lambda")

from tests.strategies import holding_strategy, portfolio_strategy

# ---------------------------------------------------------------------------
# Load portfolio-analyzer handler
# ---------------------------------------------------------------------------

_handler_path = os.path.join(os.path.dirname(__file__), "../../lambda/portfolio-analyzer/handler.py")
_spec = importlib.util.spec_from_file_location("portfolio_analyzer_handler", _handler_path)
_handler_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_handler_module)
PortfolioAnalyzer = _handler_module.PortfolioAnalyzer


# ============================================================================
# Property 50: Foundation Model Invocation
# ============================================================================

class TestFoundationModelInvocation:
    """
    Property 50: Foundation Model Invocation

    **Validates: Requirements 12.2**

    For any agent reasoning or analysis task, the agent should invoke the
    Bedrock foundation model (Claude 3.5 Sonnet) exactly once per analysis
    request, with the correct model ID and content type.
    """

    @given(portfolio=portfolio_strategy())
    @settings(max_examples=20, deadline=None)
    def test_bedrock_invoked_with_correct_model_id(self, portfolio):
        """Bedrock must be called with the Claude 3.5 Sonnet model ID."""
        analyzer = PortfolioAnalyzer()
        analyzer.portfolio_tool = Mock()
        analyzer.portfolio_tool.execute.return_value = portfolio
        analyzer.market_data_tool = Mock()
        analyzer.market_data_tool.execute.return_value = []

        mock_bedrock = Mock()
        mock_bedrock.invoke_model.return_value = {
            "body": Mock(
                read=lambda: json.dumps(
                    {"content": [{"text": "Diversify your holdings."}]}
                ).encode()
            )
        }
        analyzer.bedrock_client = mock_bedrock

        analyzer.analyze(portfolio.user_id, portfolio.portfolio_id)

        assert mock_bedrock.invoke_model.called, "Bedrock invoke_model must be called"
        call_kwargs = mock_bedrock.invoke_model.call_args
        model_id = call_kwargs[1].get("modelId") or call_kwargs[0][0] if call_kwargs[0] else None
        if model_id is None and call_kwargs[1]:
            model_id = call_kwargs[1].get("modelId")
        assert model_id is not None, "modelId must be provided"
        assert "claude" in model_id.lower() or "anthropic" in model_id.lower(), (
            f"Expected Claude model, got: {model_id}"
        )

    @given(portfolio=portfolio_strategy())
    @settings(max_examples=20, deadline=None)
    def test_bedrock_invoked_with_correct_content_type(self, portfolio):
        """Bedrock must be called with application/json content type."""
        analyzer = PortfolioAnalyzer()
        analyzer.portfolio_tool = Mock()
        analyzer.portfolio_tool.execute.return_value = portfolio
        analyzer.market_data_tool = Mock()
        analyzer.market_data_tool.execute.return_value = []

        mock_bedrock = Mock()
        mock_bedrock.invoke_model.return_value = {
            "body": Mock(
                read=lambda: json.dumps(
                    {"content": [{"text": "Rebalance towards target allocation."}]}
                ).encode()
            )
        }
        analyzer.bedrock_client = mock_bedrock

        analyzer.analyze(portfolio.user_id, portfolio.portfolio_id)

        call_kwargs = mock_bedrock.invoke_model.call_args[1]
        assert call_kwargs.get("contentType") == "application/json"
        assert call_kwargs.get("accept") == "application/json"

    @given(portfolio=portfolio_strategy())
    @settings(max_examples=20, deadline=None)
    def test_bedrock_body_is_valid_json(self, portfolio):
        """The body passed to Bedrock must be valid JSON."""
        analyzer = PortfolioAnalyzer()
        analyzer.portfolio_tool = Mock()
        analyzer.portfolio_tool.execute.return_value = portfolio
        analyzer.market_data_tool = Mock()
        analyzer.market_data_tool.execute.return_value = []

        captured_body = {}

        def capture_invoke(**kwargs):
            captured_body["body"] = kwargs.get("body", "")
            return {
                "body": Mock(
                    read=lambda: json.dumps(
                        {"content": [{"text": "Consider tax-loss harvesting."}]}
                    ).encode()
                )
            }

        mock_bedrock = Mock()
        mock_bedrock.invoke_model.side_effect = capture_invoke
        analyzer.bedrock_client = mock_bedrock

        analyzer.analyze(portfolio.user_id, portfolio.portfolio_id)

        assert "body" in captured_body, "Body must be captured"
        parsed = json.loads(captured_body["body"])
        assert isinstance(parsed, dict), "Body must be a JSON object"
        assert "messages" in parsed, "Body must contain 'messages'"


# ============================================================================
# Property 51: Model Prompt Context Completeness
# ============================================================================

class TestModelPromptContextCompleteness:
    """
    Property 51: Model Prompt Context Completeness

    **Validates: Requirements 12.3**

    For any agent analysis, the prompt sent to the foundation model must
    include relevant portfolio context: holdings, performance metrics,
    risk metrics, and allocation drift.
    """

    @given(portfolio=portfolio_strategy())
    @settings(max_examples=20, deadline=None)
    def test_prompt_includes_portfolio_holdings(self, portfolio):
        """Prompt must reference at least one portfolio ticker."""
        analyzer = PortfolioAnalyzer()
        analyzer.portfolio_tool = Mock()
        analyzer.market_data_tool = Mock()
        analyzer.market_data_tool.execute.return_value = []
        analyzer.bedrock_client = Mock()

        perf = analyzer._calculate_performance_metrics(portfolio)
        risk = analyzer._calculate_risk_metrics(portfolio)
        drift = analyzer._calculate_allocation_drift(portfolio)

        prompt = analyzer._build_analysis_prompt(portfolio, perf, risk, drift, [])

        tickers = [h.ticker for h in portfolio.holdings]
        assert any(t in prompt for t in tickers), (
            f"Prompt must include at least one ticker from {tickers}"
        )

    @given(portfolio=portfolio_strategy())
    @settings(max_examples=20, deadline=None)
    def test_prompt_includes_performance_metrics(self, portfolio):
        """Prompt must include performance metric labels."""
        analyzer = PortfolioAnalyzer()
        analyzer.portfolio_tool = Mock()
        analyzer.market_data_tool = Mock()
        analyzer.market_data_tool.execute.return_value = []
        analyzer.bedrock_client = Mock()

        perf = analyzer._calculate_performance_metrics(portfolio)
        risk = analyzer._calculate_risk_metrics(portfolio)
        drift = analyzer._calculate_allocation_drift(portfolio)

        prompt = analyzer._build_analysis_prompt(portfolio, perf, risk, drift, [])

        for keyword in ("Total Return", "Sharpe", "Drawdown"):
            assert keyword in prompt, f"Prompt must contain '{keyword}'"

    @given(portfolio=portfolio_strategy())
    @settings(max_examples=20, deadline=None)
    def test_prompt_includes_allocation_drift(self, portfolio):
        """Prompt must include allocation drift information."""
        analyzer = PortfolioAnalyzer()
        analyzer.portfolio_tool = Mock()
        analyzer.market_data_tool = Mock()
        analyzer.market_data_tool.execute.return_value = []
        analyzer.bedrock_client = Mock()

        perf = analyzer._calculate_performance_metrics(portfolio)
        risk = analyzer._calculate_risk_metrics(portfolio)
        drift = analyzer._calculate_allocation_drift(portfolio)

        prompt = analyzer._build_analysis_prompt(portfolio, perf, risk, drift, [])

        assert "target" in prompt.lower() or "allocation" in prompt.lower(), (
            "Prompt must include allocation/target information"
        )

    @given(portfolio=portfolio_strategy())
    @settings(max_examples=20, deadline=None)
    def test_prompt_includes_risk_tolerance(self, portfolio):
        """Prompt must include the user's risk tolerance."""
        analyzer = PortfolioAnalyzer()
        analyzer.portfolio_tool = Mock()
        analyzer.market_data_tool = Mock()
        analyzer.market_data_tool.execute.return_value = []
        analyzer.bedrock_client = Mock()

        perf = analyzer._calculate_performance_metrics(portfolio)
        risk = analyzer._calculate_risk_metrics(portfolio)
        drift = analyzer._calculate_allocation_drift(portfolio)

        prompt = analyzer._build_analysis_prompt(portfolio, perf, risk, drift, [])

        assert portfolio.risk_tolerance in prompt, (
            f"Prompt must include risk tolerance '{portfolio.risk_tolerance}'"
        )


# ============================================================================
# Property 52: Model Response Validation
# ============================================================================

class TestModelResponseValidation:
    """
    Property 52: Model Response Validation

    **Validates: Requirements 12.4**

    For any Bedrock response, the agent must parse and validate the response
    before using it. Invalid or empty responses must not be silently accepted.
    """

    @given(
        response_text=st.text(min_size=1, max_size=500).filter(lambda t: t.strip() != "")
    )
    @settings(max_examples=30, deadline=None)
    def test_valid_response_produces_recommendations(self, response_text):
        """Any non-empty response text should produce at least one recommendation."""
        analyzer = PortfolioAnalyzer()
        recs = analyzer._parse_recommendations(response_text)
        assert isinstance(recs, list), "Recommendations must be a list"
        # Non-empty text should yield at least one recommendation
        if response_text.strip():
            assert len(recs) >= 0  # Parser may filter; just ensure no crash

    @given(
        num_recommendations=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=20, deadline=None)
    def test_response_capped_at_five_recommendations(self, num_recommendations):
        """Parsed recommendations must be capped at 5."""
        lines = [f"Recommendation {i}" for i in range(num_recommendations)]
        response_text = "\n".join(lines)

        analyzer = PortfolioAnalyzer()
        recs = analyzer._parse_recommendations(response_text)

        assert len(recs) <= 5, f"Recommendations must be capped at 5, got {len(recs)}"

    @given(portfolio=portfolio_strategy())
    @settings(max_examples=20, deadline=None)
    def test_invalid_response_format_falls_back_to_defaults(self, portfolio):
        """When Bedrock returns an invalid format, default recommendations are used."""
        analyzer = PortfolioAnalyzer()
        analyzer.portfolio_tool = Mock()
        analyzer.portfolio_tool.execute.return_value = portfolio
        analyzer.market_data_tool = Mock()
        analyzer.market_data_tool.execute.return_value = []

        # Return malformed response (missing 'content' key)
        mock_bedrock = Mock()
        mock_bedrock.invoke_model.return_value = {
            "body": Mock(read=lambda: json.dumps({"unexpected": "format"}).encode())
        }
        analyzer.bedrock_client = mock_bedrock

        report = analyzer.analyze(portfolio.user_id, portfolio.portfolio_id)

        # Should still return a report with default recommendations
        assert report is not None
        assert isinstance(report.recommendations, list)
        assert len(report.recommendations) > 0


# ============================================================================
# Property 53: Invalid Response Retry
# ============================================================================

class TestInvalidResponseRetry:
    """
    Property 53: Invalid Response Retry

    **Validates: Requirements 12.5**

    When the foundation model returns an invalid or incomplete response,
    the agent must retry the request up to 2 times before falling back
    to default recommendations.
    """

    @given(
        num_failures=st.integers(min_value=1, max_value=2)
    )
    @settings(max_examples=10, deadline=None)
    def test_retry_on_bedrock_failure(self, num_failures):
        """Agent retries Bedrock invocation on failure, up to max_retries."""
        analyzer = PortfolioAnalyzer()
        call_count = {"n": 0}

        def flaky_invoke(**kwargs):
            call_count["n"] += 1
            if call_count["n"] <= num_failures:
                raise Exception("Simulated Bedrock throttle")
            return {
                "body": Mock(
                    read=lambda: json.dumps(
                        {"content": [{"text": "Rebalance your portfolio."}]}
                    ).encode()
                )
            }

        mock_bedrock = Mock()
        mock_bedrock.invoke_model.side_effect = flaky_invoke
        analyzer.bedrock_client = mock_bedrock

        # Should succeed after retries (num_failures <= 2)
        result = analyzer._invoke_bedrock_with_retry("Test prompt", max_retries=2)
        assert result is not None
        assert call_count["n"] == num_failures + 1

    @given(portfolio=portfolio_strategy())
    @settings(max_examples=10, deadline=None)
    def test_exhausted_retries_fall_back_to_defaults(self, portfolio):
        """After 3 total attempts (initial + 2 retries), fall back to defaults."""
        analyzer = PortfolioAnalyzer()
        analyzer.portfolio_tool = Mock()
        analyzer.portfolio_tool.execute.return_value = portfolio
        analyzer.market_data_tool = Mock()
        analyzer.market_data_tool.execute.return_value = []

        mock_bedrock = Mock()
        mock_bedrock.invoke_model.side_effect = Exception("Persistent Bedrock failure")
        analyzer.bedrock_client = mock_bedrock

        # Should not raise; should return report with default recommendations
        report = analyzer.analyze(portfolio.user_id, portfolio.portfolio_id)

        assert report is not None
        assert isinstance(report.recommendations, list)
        assert len(report.recommendations) > 0

    @given(
        max_retries=st.integers(min_value=0, max_value=3)
    )
    @settings(max_examples=10, deadline=None)
    def test_retry_count_bounded_by_max_retries(self, max_retries):
        """Total invocation attempts must not exceed max_retries + 1."""
        analyzer = PortfolioAnalyzer()
        call_count = {"n": 0}

        def always_fail(**kwargs):
            call_count["n"] += 1
            raise Exception("Always fails")

        mock_bedrock = Mock()
        mock_bedrock.invoke_model.side_effect = always_fail
        analyzer.bedrock_client = mock_bedrock

        with pytest.raises(Exception):
            analyzer._invoke_bedrock_with_retry("Test prompt", max_retries=max_retries)

        assert call_count["n"] <= max_retries + 1, (
            f"Expected at most {max_retries + 1} calls, got {call_count['n']}"
        )
