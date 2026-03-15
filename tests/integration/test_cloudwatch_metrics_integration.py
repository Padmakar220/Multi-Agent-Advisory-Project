"""Integration tests for CloudWatch metrics utility."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.utils.cloudwatch_metrics import (
    CloudWatchMetrics,
    MetricUnit,
    MetricsTimer,
    create_metrics_client
)


class TestCloudWatchMetricsIntegration:
    """Integration tests for CloudWatch metrics."""
    
    @pytest.fixture
    def metrics_client(self):
        """Create a metrics client with mocked CloudWatch."""
        with patch("src.utils.cloudwatch_metrics.boto3.client") as mock_boto:
            mock_cw = MagicMock()
            mock_boto.return_value = mock_cw
            client = CloudWatchMetrics()
            client.cloudwatch = mock_cw
            yield client
    
    def test_agent_response_time_metric_emission(self, metrics_client):
        """Test emitting agent response time metrics."""
        # Emit metrics for different agents
        metrics_client.emit_agent_response_time("portfolio_analyzer", 250.5)
        metrics_client.emit_agent_response_time("tax_optimizer", 180.0)
        metrics_client.emit_agent_response_time("rebalancing_agent", 320.0)
        
        # Verify all metrics were emitted
        assert metrics_client.cloudwatch.put_metric_data.call_count == 3
    
    def test_workflow_duration_metric_emission(self, metrics_client):
        """Test emitting workflow duration metrics."""
        # Emit metrics for different workflows
        metrics_client.emit_workflow_duration("rebalancing", 45.5)
        metrics_client.emit_workflow_duration("tax_optimization", 30.0)
        
        # Verify metrics were emitted
        assert metrics_client.cloudwatch.put_metric_data.call_count == 2
    
    def test_trade_execution_metrics(self, metrics_client):
        """Test emitting trade execution metrics."""
        # Emit success and failure metrics
        metrics_client.emit_trade_execution_success("market", True)
        metrics_client.emit_trade_execution_success("limit", False)
        metrics_client.emit_trade_execution_success("market", True)
        
        # Verify metrics were emitted
        assert metrics_client.cloudwatch.put_metric_data.call_count == 3
    
    def test_dynamodb_query_latency_metrics(self, metrics_client):
        """Test emitting DynamoDB query latency metrics."""
        # Emit metrics for different operations
        metrics_client.emit_dynamodb_query_latency("Portfolios", 85.5, "query")
        metrics_client.emit_dynamodb_query_latency("Transactions", 120.0, "scan")
        metrics_client.emit_dynamodb_query_latency("AgentSessions", 45.0, "get_item")
        
        # Verify metrics were emitted
        assert metrics_client.cloudwatch.put_metric_data.call_count == 3
    
    def test_batch_metrics_emission(self, metrics_client):
        """Test emitting multiple metrics in a batch."""
        metrics = [
            {
                "metric_name": "AgentResponseTime",
                "value": 250.0,
                "unit": MetricUnit.MILLISECONDS,
                "dimensions": {"AgentType": "portfolio_analyzer"}
            },
            {
                "metric_name": "WorkflowDuration",
                "value": 45.0,
                "unit": MetricUnit.SECONDS,
                "dimensions": {"WorkflowType": "rebalancing"}
            },
            {
                "metric_name": "TradeExecutionSuccess",
                "value": 1.0,
                "unit": MetricUnit.COUNT,
                "dimensions": {"OrderType": "market", "Status": "success"}
            }
        ]
        
        count = metrics_client.emit_batch_metrics(metrics)
        
        assert count == 3
        metrics_client.cloudwatch.put_metric_data.assert_called_once()
    
    def test_metrics_with_user_tracking(self, metrics_client):
        """Test emitting metrics with user ID tracking."""
        user_id = "user_123"
        
        metrics_client.emit_agent_response_time(
            "portfolio_analyzer",
            250.0,
            user_id=user_id
        )
        
        metrics_client.emit_workflow_duration(
            "rebalancing",
            45.0,
            user_id=user_id
        )
        
        # Verify metrics were emitted
        assert metrics_client.cloudwatch.put_metric_data.call_count == 2
    
    def test_metrics_timer_integration(self, metrics_client):
        """Test using MetricsTimer for automatic metric emission."""
        import time
        
        with MetricsTimer(
            metrics_client,
            "AgentResponseTime",
            dimensions={"AgentType": "portfolio_analyzer"}
        ):
            time.sleep(0.05)
        
        # Verify metric was emitted
        metrics_client.cloudwatch.put_metric_data.assert_called_once()
        
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]
        
        assert metric_data["MetricName"] == "AgentResponseTime"
        assert metric_data["Value"] > 40  # At least 40ms
    
    def test_complete_workflow_metrics(self, metrics_client):
        """Test emitting metrics for a complete workflow."""
        user_id = "user_456"
        
        # Emit metrics for portfolio analysis
        metrics_client.emit_agent_response_time("portfolio_analyzer", 280.0, user_id)
        metrics_client.emit_dynamodb_query_latency("Portfolios", 75.0, "query", user_id)
        
        # Emit metrics for tax optimization
        metrics_client.emit_agent_response_time("tax_optimizer", 200.0, user_id)
        metrics_client.emit_dynamodb_query_latency("Portfolios", 85.0, "query", user_id)
        
        # Emit metrics for rebalancing
        metrics_client.emit_agent_response_time("rebalancing_agent", 250.0, user_id)
        
        # Emit workflow duration
        metrics_client.emit_workflow_duration("rebalancing", 50.0, user_id)
        
        # Emit trade execution metrics
        metrics_client.emit_trade_execution_success("market", True, user_id)
        metrics_client.emit_trade_execution_success("market", True, user_id)
        
        # Verify all metrics were emitted
        assert metrics_client.cloudwatch.put_metric_data.call_count == 8
    
    def test_error_handling_in_metrics(self, metrics_client):
        """Test error handling when emitting metrics."""
        from botocore.exceptions import ClientError
        
        # Simulate CloudWatch API error
        error_response = {"Error": {"Code": "ValidationError"}}
        metrics_client.cloudwatch.put_metric_data.side_effect = ClientError(
            error_response, "PutMetricData"
        )
        
        # Should return False on error
        result = metrics_client.emit_agent_response_time("portfolio_analyzer", 250.0)
        assert result is False
    
    def test_metric_validation(self, metrics_client):
        """Test metric validation."""
        # Invalid metric name
        assert metrics_client.emit_metric("", 100.0, MetricUnit.COUNT) is False
        
        # Invalid value type
        assert metrics_client.emit_metric("TestMetric", "invalid", MetricUnit.COUNT) is False
        
        # Invalid response time
        assert metrics_client.emit_agent_response_time("agent", -100.0) is False
        
        # Invalid workflow duration
        assert metrics_client.emit_workflow_duration("workflow", -50.0) is False
        
        # Invalid query latency
        assert metrics_client.emit_dynamodb_query_latency("table", -75.0) is False
        
        # Invalid request count
        assert metrics_client.emit_request_count("agent", -5) is False
