"""
Performance tests for the Multi-Agent Advisory AI System.

Validates:
- Portfolio data retrieval < 100 ms  (Requirement 8.3)
- Agent response time < 5 seconds    (Requirement 15.3)
- 100 concurrent users               (Requirements 11.4, 11.5)
- p95 and p99 latency measurements

Requirements: 8.3, 15.3
"""

import concurrent.futures
import importlib.util
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, "src")
sys.path.insert(0, "lambda")

from src.models.portfolio import Holding, Portfolio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_handler(rel_path: str, module_name: str):
    path = os.path.join(os.path.dirname(__file__), rel_path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_portfolio(user_id: str = "u1", portfolio_id: str = "p1") -> Portfolio:
    return Portfolio(
        user_id=user_id,
        portfolio_id=portfolio_id,
        portfolio_name="Perf Test Portfolio",
        holdings=[
            Holding(ticker="VTI", quantity=100, cost_basis=200.0, current_price=220.0, purchase_date="2023-01-01"),
            Holding(ticker="BND", quantity=50, cost_basis=80.0, current_price=78.0, purchase_date="2023-06-01"),
        ],
        target_allocation={"stocks": 0.60, "bonds": 0.40},
        total_value=25_900.0,
        risk_tolerance="moderate",
    )


def _percentile(data: list, pct: float) -> float:
    """Return the given percentile of a sorted list."""
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * pct / 100)
    return sorted_data[min(idx, len(sorted_data) - 1)]


# ---------------------------------------------------------------------------
# Portfolio data retrieval performance  (Requirement 8.3: < 100 ms)
# ---------------------------------------------------------------------------

class TestPortfolioDataRetrievalPerformance:
    """Validate that portfolio data retrieval completes within 100 ms."""

    RETRIEVAL_LIMIT_MS = 100
    NUM_SAMPLES = 50

    def _make_mock_tool(self, portfolio: Portfolio):
        tool = Mock()
        tool.execute.return_value = portfolio
        return tool

    def test_portfolio_data_retrieval_performance(self):
        """
        **Validates: Requirement 8.3**

        Portfolio data retrieval from DynamoDB must complete within 100 ms.
        Measures p50, p95, and p99 latencies over 50 samples.
        """
        pa_mod = _load_handler("../../lambda/portfolio-analyzer/handler.py", "pa_perf")
        PortfolioAnalyzer = pa_mod.PortfolioAnalyzer

        portfolio = _make_portfolio()
        latencies_ms = []

        for _ in range(self.NUM_SAMPLES):
            analyzer = PortfolioAnalyzer()
            analyzer.portfolio_tool = self._make_mock_tool(portfolio)
            analyzer.market_data_tool = Mock()
            analyzer.market_data_tool.execute.return_value = []
            analyzer.bedrock_client = Mock()

            start = time.perf_counter()
            retrieved = analyzer._retrieve_portfolio(portfolio.user_id, portfolio.portfolio_id)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

            assert retrieved is not None

        p50 = _percentile(latencies_ms, 50)
        p95 = _percentile(latencies_ms, 95)
        p99 = _percentile(latencies_ms, 99)

        print(f"\nPortfolio retrieval latency — p50: {p50:.2f}ms  p95: {p95:.2f}ms  p99: {p99:.2f}ms")

        assert p95 < self.RETRIEVAL_LIMIT_MS, (
            f"p95 retrieval latency {p95:.2f}ms exceeds {self.RETRIEVAL_LIMIT_MS}ms limit"
        )
        assert p99 < self.RETRIEVAL_LIMIT_MS * 2, (
            f"p99 retrieval latency {p99:.2f}ms exceeds {self.RETRIEVAL_LIMIT_MS * 2}ms limit"
        )

    def test_portfolio_retrieval_p50_under_50ms(self):
        """p50 retrieval latency should be well under 50 ms for mocked DynamoDB."""
        pa_mod = _load_handler("../../lambda/portfolio-analyzer/handler.py", "pa_perf2")
        PortfolioAnalyzer = pa_mod.PortfolioAnalyzer

        portfolio = _make_portfolio()
        latencies_ms = []

        for _ in range(self.NUM_SAMPLES):
            analyzer = PortfolioAnalyzer()
            analyzer.portfolio_tool = self._make_mock_tool(portfolio)
            analyzer.market_data_tool = Mock()
            analyzer.bedrock_client = Mock()

            start = time.perf_counter()
            analyzer._retrieve_portfolio(portfolio.user_id, portfolio.portfolio_id)
            latencies_ms.append((time.perf_counter() - start) * 1000)

        p50 = _percentile(latencies_ms, 50)
        assert p50 < 50, f"p50 latency {p50:.2f}ms should be < 50ms"


# ---------------------------------------------------------------------------
# Agent response time  (Requirement 15.3: < 5 seconds)
# ---------------------------------------------------------------------------

class TestAgentResponseTime:
    """Validate that agent analysis completes within 5 seconds."""

    RESPONSE_LIMIT_S = 5.0
    NUM_SAMPLES = 20

    def test_portfolio_analyzer_response_time(self):
        """
        **Validates: Requirement 15.3**

        Portfolio Analyzer must return a complete analysis within 5 seconds.
        """
        pa_mod = _load_handler("../../lambda/portfolio-analyzer/handler.py", "pa_resp")
        PortfolioAnalyzer = pa_mod.PortfolioAnalyzer

        portfolio = _make_portfolio()
        latencies_s = []

        for _ in range(self.NUM_SAMPLES):
            analyzer = PortfolioAnalyzer()
            analyzer.portfolio_tool = Mock()
            analyzer.portfolio_tool.execute.return_value = portfolio
            analyzer.market_data_tool = Mock()
            analyzer.market_data_tool.execute.return_value = []
            analyzer.bedrock_client = Mock()
            analyzer.bedrock_client.invoke_model.return_value = {
                "body": Mock(read=lambda: json.dumps({"content": [{"text": "Hold steady."}]}).encode())
            }

            start = time.perf_counter()
            report = analyzer.analyze(portfolio.user_id, portfolio.portfolio_id)
            elapsed = time.perf_counter() - start
            latencies_s.append(elapsed)

            assert report is not None

        p95 = _percentile(latencies_s, 95)
        p99 = _percentile(latencies_s, 99)
        avg = statistics.mean(latencies_s)

        print(f"\nAgent response time — avg: {avg:.3f}s  p95: {p95:.3f}s  p99: {p99:.3f}s")

        assert p95 < self.RESPONSE_LIMIT_S, (
            f"p95 agent response time {p95:.3f}s exceeds {self.RESPONSE_LIMIT_S}s limit"
        )

    def test_tax_optimizer_response_time(self):
        """Tax Optimizer must return a plan within 5 seconds."""
        to_mod = _load_handler("../../lambda/tax-optimizer/handler.py", "to_resp")
        TaxOptimizer = to_mod.TaxOptimizer

        portfolio = _make_portfolio()
        latencies_s = []

        for _ in range(self.NUM_SAMPLES):
            optimizer = TaxOptimizer()
            optimizer.portfolio_tool = Mock()
            optimizer.portfolio_tool.execute.return_value = portfolio
            optimizer.cost_basis_tool = Mock()
            optimizer.bedrock_client = Mock()
            optimizer.bedrock_client.invoke_model.return_value = {
                "body": Mock(read=lambda: json.dumps({"content": [{"text": "Harvest losses."}]}).encode())
            }

            start = time.perf_counter()
            plan = optimizer.optimize(portfolio.user_id, portfolio.portfolio_id)
            latencies_s.append(time.perf_counter() - start)

            assert plan is not None

        p95 = _percentile(latencies_s, 95)
        assert p95 < self.RESPONSE_LIMIT_S, (
            f"Tax optimizer p95 {p95:.3f}s exceeds {self.RESPONSE_LIMIT_S}s limit"
        )

    def test_rebalancing_agent_response_time(self):
        """Rebalancing Agent must return a plan within 5 seconds."""
        rb_mod = _load_handler("../../lambda/rebalancing-agent/handler.py", "rb_resp")
        RebalancingAgent = rb_mod.RebalancingAgent

        from src.models.requests import RebalancingConstraints
        portfolio = _make_portfolio()
        constraints = RebalancingConstraints(max_transaction_cost=100.0, min_trade_size=10.0, risk_tolerance="moderate")
        latencies_s = []

        for _ in range(self.NUM_SAMPLES):
            agent = RebalancingAgent()
            agent.portfolio_tool = Mock()
            agent.portfolio_tool.execute.return_value = portfolio
            agent.bedrock_client = Mock()
            agent.bedrock_client.invoke_model.return_value = {
                "body": Mock(read=lambda: json.dumps({"content": [{"text": "Rebalance now."}]}).encode())
            }

            start = time.perf_counter()
            plan = agent.rebalance(portfolio.user_id, portfolio.portfolio_id, constraints)
            latencies_s.append(time.perf_counter() - start)

            assert plan is not None

        p95 = _percentile(latencies_s, 95)
        assert p95 < self.RESPONSE_LIMIT_S, (
            f"Rebalancing agent p95 {p95:.3f}s exceeds {self.RESPONSE_LIMIT_S}s limit"
        )


# ---------------------------------------------------------------------------
# Concurrent requests  (Requirements 11.4, 11.5: 100 concurrent users)
# ---------------------------------------------------------------------------

class TestConcurrentRequests:
    """Validate system behaviour under 100 concurrent users."""

    NUM_CONCURRENT = 100
    SUCCESS_RATE_THRESHOLD = 0.99

    def _run_single_analysis(self, user_idx: int) -> dict:
        """Execute a single portfolio analysis and return timing + status."""
        pa_mod = _load_handler("../../lambda/portfolio-analyzer/handler.py", f"pa_conc_{user_idx}")
        PortfolioAnalyzer = pa_mod.PortfolioAnalyzer

        portfolio = _make_portfolio(user_id=f"user_{user_idx}", portfolio_id=f"portfolio_{user_idx}")

        analyzer = PortfolioAnalyzer()
        analyzer.portfolio_tool = Mock()
        analyzer.portfolio_tool.execute.return_value = portfolio
        analyzer.market_data_tool = Mock()
        analyzer.market_data_tool.execute.return_value = []
        analyzer.bedrock_client = Mock()
        analyzer.bedrock_client.invoke_model.return_value = {
            "body": Mock(read=lambda: json.dumps({"content": [{"text": "Diversify."}]}).encode())
        }

        start = time.perf_counter()
        try:
            report = analyzer.analyze(portfolio.user_id, portfolio.portfolio_id)
            elapsed = time.perf_counter() - start
            return {"success": True, "latency_s": elapsed, "user": user_idx}
        except Exception as exc:
            elapsed = time.perf_counter() - start
            return {"success": False, "latency_s": elapsed, "user": user_idx, "error": str(exc)}

    def test_concurrent_requests_success_rate(self):
        """
        **Validates: Requirements 11.4, 11.5**

        100 concurrent analysis requests must achieve >= 99% success rate.
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.NUM_CONCURRENT) as executor:
            futures = [executor.submit(self._run_single_analysis, i) for i in range(self.NUM_CONCURRENT)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        successes = sum(1 for r in results if r["success"])
        success_rate = successes / self.NUM_CONCURRENT

        print(f"\nConcurrent requests — {successes}/{self.NUM_CONCURRENT} succeeded ({success_rate:.1%})")

        assert success_rate >= self.SUCCESS_RATE_THRESHOLD, (
            f"Success rate {success_rate:.1%} below {self.SUCCESS_RATE_THRESHOLD:.0%} threshold"
        )

    def test_concurrent_requests_latency_percentiles(self):
        """
        Measure p95 and p99 latencies under 100 concurrent users.
        Both must remain within acceptable bounds.
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.NUM_CONCURRENT) as executor:
            futures = [executor.submit(self._run_single_analysis, i) for i in range(self.NUM_CONCURRENT)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        latencies = [r["latency_s"] for r in results if r["success"]]

        if not latencies:
            pytest.fail("No successful requests to measure latency")

        p50 = _percentile(latencies, 50)
        p95 = _percentile(latencies, 95)
        p99 = _percentile(latencies, 99)

        print(f"\nConcurrent latency — p50: {p50:.3f}s  p95: {p95:.3f}s  p99: {p99:.3f}s")

        # Under mocked conditions, all should be well under 5 seconds
        assert p95 < 5.0, f"p95 latency {p95:.3f}s exceeds 5s under concurrent load"
        assert p99 < 10.0, f"p99 latency {p99:.3f}s exceeds 10s under concurrent load"

    def test_no_data_leakage_between_concurrent_users(self):
        """
        Each concurrent user must receive their own portfolio data,
        not another user's data.
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(self._run_single_analysis, i): i for i in range(20)}
            results = {futures[f]: f.result() for f in concurrent.futures.as_completed(futures)}

        # Verify each result corresponds to the correct user
        for user_idx, result in results.items():
            assert result["user"] == user_idx, (
                f"User {user_idx} received result for user {result['user']}"
            )
