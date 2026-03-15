"""Unit tests for CloudWatch metrics utility."""

import pytest
import time
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock, call
from botocore.exceptions import ClientError

from src.utils.cloudwatch_metrics import (
    CloudWatchMetrics,
    MetricUnit,
    MetricsTimer,
    create_metrics_client
)


class TestMetricUnit:
    """Tests for MetricUnit enum."""
    
    def test_metric_unit_values(self):
        """Test that MetricUnit enum has correct values."""
        assert MetricUnit.MILLISECONDS.value == "Milliseconds"
        assert MetricUnit.SECONDS.value == "Seconds"
        assert MetricUnit.COUNT.value == "Count"
        assert MetricUnit.PERCENT.value == "Percent"


class TestCloudWatchMetrics:
    """Tests for CloudWatchMetrics class."""
    
    @pytest.fixture
    def metrics_client(self):
        """Create a metrics client with mocked CloudWatch."""
        with patch("src.utils.cloudwatch_metrics.boto3.client") as mock_boto:
            mock_cw = MagicMock()
            mock_boto.return_value = mock_cw
            client = CloudWatchMetrics()
            client.cloudwatch = mock_cw
            yield client
    
    def test_initialization(self):
        """Test CloudWatchMetrics initialization."""
        with patch("src.utils.cloudwatch_metrics.boto3.client"):
            client = CloudWatchMetrics(namespace="TestNamespace")
            assert client.namespace == "TestNamespace"
    
    def test_initialization_default_namespace(self):
        """Test CloudWatchMetrics initialization with default namespace."""
        with patch("src.utils.cloudwatch_metrics.boto3.client"):
            client = CloudWatchMetrics()
            assert client.namespace == "MultiAgentAdvisorySystem"
    
    def test_emit_metric_success(self, metrics_client):
        """Test successful metric emission."""
        result = metrics_client.emit_metric(
            metric_name="TestMetric",
            value=100.0,
            unit=MetricUnit.COUNT
        )
        
        assert result is True
        metrics_client.cloudwatch.put_metric_data.assert_called_once()
        
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        assert call_args[1]["Namespace"] == "MultiAgentAdvisorySystem"
        assert call_args[1]["MetricData"][0]["MetricName"] == "TestMetric"
        assert call_args[1]["MetricData"][0]["Value"] == 100.0
        assert call_args[1]["MetricData"][0]["Unit"] == "Count"
    
    def test_emit_metric_with_dimensions(self, metrics_client):
        """Test metric emission with dimensions."""
        dimensions = {"AgentType": "portfolio_analyzer", "Status": "success"}
        
        result = metrics_client.emit_metric(
            metric_name="AgentResponseTime",
            value=250.5,
            unit=MetricUnit.MILLISECONDS,
            dimensions=dimensions
        )
        
        assert result is True
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]
        
        assert len(metric_data["Dimensions"]) == 2
        dim_dict = {d["Name"]: d["Value"] for d in metric_data["Dimensions"]}
        assert dim_dict["AgentType"] == "portfolio_analyzer"
        assert dim_dict["Status"] == "success"
    
    def test_emit_metric_with_timestamp(self, metrics_client):
        """Test metric emission with custom timestamp."""
        custom_time = datetime(2024, 1, 15, 10, 30, 0)
        
        result = metrics_client.emit_metric(
            metric_name="TestMetric",
            value=50.0,
            unit=MetricUnit.COUNT,
            timestamp=custom_time
        )
        
        assert result is True
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        assert call_args[1]["MetricData"][0]["Timestamp"] == custom_time
    
    def test_emit_metric_invalid_name(self, metrics_client):
        """Test metric emission with invalid metric name."""
        result = metrics_client.emit_metric(
            metric_name="",
            value=100.0,
            unit=MetricUnit.COUNT
        )
        
        assert result is False
        metrics_client.cloudwatch.put_metric_data.assert_not_called()
    
    def test_emit_metric_invalid_value_type(self, metrics_client):
        """Test metric emission with invalid value type."""
        result = metrics_client.emit_metric(
            metric_name="TestMetric",
            value="not_a_number",
            unit=MetricUnit.COUNT
        )
        
        assert result is False
        metrics_client.cloudwatch.put_metric_data.assert_not_called()
    
    def test_emit_metric_negative_value_warning(self, metrics_client):
        """Test that negative values trigger warning but still emit."""
        result = metrics_client.emit_metric(
            metric_name="TestMetric",
            value=-10.0,
            unit=MetricUnit.COUNT
        )
        
        assert result is True
        metrics_client.cloudwatch.put_metric_data.assert_called_once()
    
    def test_emit_metric_cloudwatch_error(self, metrics_client):
        """Test handling of CloudWatch API errors."""
        error_response = {"Error": {"Code": "ValidationError"}}
        metrics_client.cloudwatch.put_metric_data.side_effect = ClientError(
            error_response, "PutMetricData"
        )
        
        result = metrics_client.emit_metric(
            metric_name="TestMetric",
            value=100.0,
            unit=MetricUnit.COUNT
        )
        
        assert result is False
    
    def test_emit_metric_unexpected_error(self, metrics_client):
        """Test handling of unexpected errors."""
        metrics_client.cloudwatch.put_metric_data.side_effect = Exception("Unexpected error")
        
        result = metrics_client.emit_metric(
            metric_name="TestMetric",
            value=100.0,
            unit=MetricUnit.COUNT
        )
        
        assert result is False
    
    def test_emit_batch_metrics_success(self, metrics_client):
        """Test successful batch metric emission."""
        metrics = [
            {
                "metric_name": "Metric1",
                "value": 100.0,
                "unit": MetricUnit.COUNT
            },
            {
                "metric_name": "Metric2",
                "value": 200.0,
                "unit": MetricUnit.MILLISECONDS,
                "dimensions": {"Type": "test"}
            }
        ]
        
        result = metrics_client.emit_batch_metrics(metrics)
        
        assert result == 2
        metrics_client.cloudwatch.put_metric_data.assert_called_once()
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        assert len(call_args[1]["MetricData"]) == 2
    
    def test_emit_batch_metrics_empty(self, metrics_client):
        """Test batch emission with empty list."""
        result = metrics_client.emit_batch_metrics([])
        
        assert result == 0
        metrics_client.cloudwatch.put_metric_data.assert_not_called()
    
    def test_emit_batch_metrics_large_batch(self, metrics_client):
        """Test batch emission with more than 20 metrics."""
        metrics = [
            {
                "metric_name": f"Metric{i}",
                "value": float(i),
                "unit": MetricUnit.COUNT
            }
            for i in range(25)
        ]
        
        result = metrics_client.emit_batch_metrics(metrics)
        
        assert result == 25
        # Should be called twice (20 + 5)
        assert metrics_client.cloudwatch.put_metric_data.call_count == 2
    
    def test_emit_batch_metrics_invalid_metric(self, metrics_client):
        """Test batch emission with invalid metric."""
        metrics = [
            {
                "metric_name": "ValidMetric",
                "value": 100.0,
                "unit": MetricUnit.COUNT
            },
            {
                "metric_name": "InvalidMetric",
                # Missing 'value' and 'unit'
            }
        ]
        
        result = metrics_client.emit_batch_metrics(metrics)
        
        assert result == 1  # Only valid metric emitted
    
    def test_emit_agent_response_time(self, metrics_client):
        """Test AgentResponseTime metric emission."""
        result = metrics_client.emit_agent_response_time(
            agent_type="portfolio_analyzer",
            response_time_ms=250.5
        )
        
        assert result is True
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]
        
        assert metric_data["MetricName"] == "AgentResponseTime"
        assert metric_data["Value"] == 250.5
        assert metric_data["Unit"] == "Milliseconds"
        
        dim_dict = {d["Name"]: d["Value"] for d in metric_data["Dimensions"]}
        assert dim_dict["AgentType"] == "portfolio_analyzer"
    
    def test_emit_agent_response_time_slow_warning(self, metrics_client):
        """Test that slow agent response triggers warning."""
        result = metrics_client.emit_agent_response_time(
            agent_type="tax_optimizer",
            response_time_ms=6000.0
        )
        
        assert result is True
        metrics_client.cloudwatch.put_metric_data.assert_called_once()
    
    def test_emit_agent_response_time_invalid(self, metrics_client):
        """Test AgentResponseTime with invalid response time."""
        result = metrics_client.emit_agent_response_time(
            agent_type="portfolio_analyzer",
            response_time_ms=-100.0
        )
        
        assert result is False
    
    def test_emit_workflow_duration(self, metrics_client):
        """Test WorkflowDuration metric emission."""
        result = metrics_client.emit_workflow_duration(
            workflow_type="rebalancing",
            duration_seconds=45.5
        )
        
        assert result is True
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]
        
        assert metric_data["MetricName"] == "WorkflowDuration"
        assert metric_data["Value"] == 45.5
        assert metric_data["Unit"] == "Seconds"
        
        dim_dict = {d["Name"]: d["Value"] for d in metric_data["Dimensions"]}
        assert dim_dict["WorkflowType"] == "rebalancing"
    
    def test_emit_workflow_duration_long_warning(self, metrics_client):
        """Test that long workflow triggers warning."""
        result = metrics_client.emit_workflow_duration(
            workflow_type="tax_optimization",
            duration_seconds=1000.0
        )
        
        assert result is True
        metrics_client.cloudwatch.put_metric_data.assert_called_once()
    
    def test_emit_workflow_duration_invalid(self, metrics_client):
        """Test WorkflowDuration with invalid duration."""
        result = metrics_client.emit_workflow_duration(
            workflow_type="rebalancing",
            duration_seconds=-10.0
        )
        
        assert result is False
    
    def test_emit_trade_execution_success(self, metrics_client):
        """Test TradeExecutionSuccess metric emission for successful trade."""
        result = metrics_client.emit_trade_execution_success(
            order_type="market",
            success=True
        )
        
        assert result is True
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]
        
        assert metric_data["MetricName"] == "TradeExecutionSuccess"
        assert metric_data["Value"] == 1.0
        assert metric_data["Unit"] == "Count"
        
        dim_dict = {d["Name"]: d["Value"] for d in metric_data["Dimensions"]}
        assert dim_dict["OrderType"] == "market"
        assert dim_dict["Status"] == "success"
    
    def test_emit_trade_execution_failure(self, metrics_client):
        """Test TradeExecutionSuccess metric emission for failed trade."""
        result = metrics_client.emit_trade_execution_success(
            order_type="limit",
            success=False
        )
        
        assert result is True
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]
        
        assert metric_data["Value"] == 0.0
        
        dim_dict = {d["Name"]: d["Value"] for d in metric_data["Dimensions"]}
        assert dim_dict["Status"] == "failure"
    
    def test_emit_dynamodb_query_latency(self, metrics_client):
        """Test DynamoDBQueryLatency metric emission."""
        result = metrics_client.emit_dynamodb_query_latency(
            table_name="Portfolios",
            latency_ms=85.5,
            operation="query"
        )
        
        assert result is True
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]
        
        assert metric_data["MetricName"] == "DynamoDBQueryLatency"
        assert metric_data["Value"] == 85.5
        assert metric_data["Unit"] == "Milliseconds"
        
        dim_dict = {d["Name"]: d["Value"] for d in metric_data["Dimensions"]}
        assert dim_dict["TableName"] == "Portfolios"
        assert dim_dict["Operation"] == "query"
    
    def test_emit_dynamodb_query_latency_high_warning(self, metrics_client):
        """Test that high DynamoDB latency triggers warning."""
        result = metrics_client.emit_dynamodb_query_latency(
            table_name="Transactions",
            latency_ms=250.0,
            operation="scan"
        )
        
        assert result is True
        metrics_client.cloudwatch.put_metric_data.assert_called_once()
    
    def test_emit_dynamodb_query_latency_invalid(self, metrics_client):
        """Test DynamoDBQueryLatency with invalid latency."""
        result = metrics_client.emit_dynamodb_query_latency(
            table_name="Portfolios",
            latency_ms=-50.0
        )
        
        assert result is False
    
    def test_emit_request_count(self, metrics_client):
        """Test request count metric emission."""
        result = metrics_client.emit_request_count(
            agent_type="portfolio_analyzer",
            count=5
        )
        
        assert result is True
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]
        
        assert metric_data["MetricName"] == "RequestCount"
        assert metric_data["Value"] == 5.0
        assert metric_data["Unit"] == "Count"
    
    def test_emit_request_count_default(self, metrics_client):
        """Test request count with default count of 1."""
        result = metrics_client.emit_request_count(
            agent_type="tax_optimizer"
        )
        
        assert result is True
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        assert call_args[1]["MetricData"][0]["Value"] == 1.0
    
    def test_emit_request_count_invalid(self, metrics_client):
        """Test request count with invalid count."""
        result = metrics_client.emit_request_count(
            agent_type="portfolio_analyzer",
            count=-5
        )
        
        assert result is False


class TestMetricsTimer:
    """Tests for MetricsTimer context manager."""
    
    @pytest.fixture
    def metrics_client(self):
        """Create a metrics client with mocked CloudWatch."""
        with patch("src.utils.cloudwatch_metrics.boto3.client") as mock_boto:
            mock_cw = MagicMock()
            mock_boto.return_value = mock_cw
            client = CloudWatchMetrics()
            client.cloudwatch = mock_cw
            yield client
    
    def test_metrics_timer_milliseconds(self, metrics_client):
        """Test MetricsTimer with milliseconds unit."""
        with MetricsTimer(
            metrics_client,
            "TestMetric",
            unit=MetricUnit.MILLISECONDS
        ) as timer:
            time.sleep(0.1)  # Sleep for 100ms
        
        duration = timer.get_duration()
        assert duration is not None
        assert 90 < duration < 150  # Allow some variance
        
        metrics_client.cloudwatch.put_metric_data.assert_called_once()
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        assert call_args[1]["MetricData"][0]["Unit"] == "Milliseconds"
    
    def test_metrics_timer_seconds(self, metrics_client):
        """Test MetricsTimer with seconds unit."""
        with MetricsTimer(
            metrics_client,
            "TestMetric",
            unit=MetricUnit.SECONDS
        ) as timer:
            time.sleep(0.05)  # Sleep for 50ms
        
        duration = timer.get_duration()
        assert duration is not None
        assert 0.04 < duration < 0.15
        
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        assert call_args[1]["MetricData"][0]["Unit"] == "Seconds"
    
    def test_metrics_timer_with_dimensions(self, metrics_client):
        """Test MetricsTimer with dimensions."""
        dimensions = {"AgentType": "portfolio_analyzer"}
        
        with MetricsTimer(
            metrics_client,
            "AgentResponseTime",
            dimensions=dimensions
        ):
            time.sleep(0.01)
        
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]
        
        dim_dict = {d["Name"]: d["Value"] for d in metric_data["Dimensions"]}
        assert dim_dict["AgentType"] == "portfolio_analyzer"
    
    def test_metrics_timer_get_duration_before_exit(self, metrics_client):
        """Test getting duration before timer exits."""
        timer = MetricsTimer(metrics_client, "TestMetric")
        
        assert timer.get_duration() is None
    
    def test_metrics_timer_multiple_uses(self, metrics_client):
        """Test using same timer multiple times."""
        timer = MetricsTimer(metrics_client, "TestMetric")
        
        with timer:
            time.sleep(0.01)
        
        first_duration = timer.get_duration()
        
        with timer:
            time.sleep(0.02)
        
        second_duration = timer.get_duration()
        
        assert second_duration > first_duration


class TestCreateMetricsClient:
    """Tests for create_metrics_client factory function."""
    
    def test_create_metrics_client_default(self):
        """Test creating metrics client with default namespace."""
        with patch("src.utils.cloudwatch_metrics.boto3.client"):
            client = create_metrics_client()
            assert isinstance(client, CloudWatchMetrics)
            assert client.namespace == "MultiAgentAdvisorySystem"
    
    def test_create_metrics_client_custom_namespace(self):
        """Test creating metrics client with custom namespace."""
        with patch("src.utils.cloudwatch_metrics.boto3.client"):
            client = create_metrics_client(namespace="CustomNamespace")
            assert client.namespace == "CustomNamespace"
