"""
Property-based tests for monitoring and observability metrics.

Tests validate that:
- Performance metrics are emitted correctly for all agent operations
- Request counts are tracked accurately per agent type
- Metrics conform to CloudWatch requirements
"""

import pytest
from hypothesis import given, strategies as st, assume
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import time
from typing import Dict, List

from src.utils.cloudwatch_metrics import CloudWatchMetrics, MetricsTimer, MetricUnit


# ============================================================================
# Strategies for generating test data
# ============================================================================

@st.composite
def agent_response_time_strategy(draw):
    """Generate realistic agent response times in milliseconds."""
    # Agent response times typically range from 100ms to 30 seconds
    return draw(st.integers(min_value=100, max_value=30000))


@st.composite
def workflow_duration_strategy(draw):
    """Generate realistic workflow durations in seconds."""
    # Workflows typically take 5 seconds to 5 minutes
    return draw(st.integers(min_value=5, max_value=300))


@st.composite
def agent_type_strategy(draw):
    """Generate valid agent types."""
    return draw(st.sampled_from([
        "portfolio_analyzer",
        "tax_optimizer",
        "rebalancing_agent",
        "supervisor"
    ]))


@st.composite
def request_count_strategy(draw):
    """Generate realistic request counts."""
    # Request counts per hour typically range from 1 to 10000
    return draw(st.integers(min_value=1, max_value=10000))


@st.composite
def metric_dimensions_strategy(draw):
    """Generate valid metric dimensions."""
    return draw(st.dictionaries(
        keys=st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"),
        values=st.text(min_size=1, max_size=100),
        min_size=0,
        max_size=10
    ))


# ============================================================================
# Property 62: Performance Metrics Emission
# ============================================================================

class TestPerformanceMetricsEmissionProperties:
    """
    **Validates: Requirements 15.1**
    
    Property 62: Performance Metrics Emission
    
    For any agent response or workflow execution, performance metrics 
    (response time, duration) should be emitted to CloudWatch.
    """

    @pytest.fixture
    def metrics_client(self):
        """Create a mocked CloudWatch metrics client."""
        with patch('boto3.client') as mock_boto_client:
            mock_cloudwatch = MagicMock()
            mock_boto_client.return_value = mock_cloudwatch
            client = CloudWatchMetrics(namespace="TestMetrics")
            client.cloudwatch = mock_cloudwatch
            yield client

    @given(
        response_time=agent_response_time_strategy(),
        agent_type=agent_type_strategy()
    )
    def test_property_62_agent_response_time_emitted(self, metrics_client, response_time, agent_type):
        """
        For any agent response time value, when emitted, a metric should be 
        recorded in CloudWatch with the correct value and agent type dimension.
        """
        # Emit the metric
        metrics_client.emit_agent_response_time(
            agent_type=agent_type,
            response_time_ms=response_time
        )
        
        # Verify the metric was emitted
        assert metrics_client.cloudwatch.put_metric_data.called
        
        # Extract the call arguments
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        assert call_args is not None
        
        # Verify namespace
        assert call_args[1]['Namespace'] == "TestMetrics"
        
        # Verify metric data
        metric_data = call_args[1]['MetricData']
        assert len(metric_data) > 0
        
        # Find the AgentResponseTime metric
        agent_response_metric = None
        for metric in metric_data:
            if metric.get('MetricName') == 'AgentResponseTime':
                agent_response_metric = metric
                break
        
        assert agent_response_metric is not None, "AgentResponseTime metric not found"
        assert agent_response_metric['Value'] == response_time
        assert agent_response_metric['Unit'] == 'Milliseconds'
        
        # Verify agent type dimension
        dimensions = {d['Name']: d['Value'] for d in agent_response_metric.get('Dimensions', [])}
        assert dimensions.get('AgentType') == agent_type

    @given(
        workflow_duration=workflow_duration_strategy(),
        workflow_type=st.sampled_from(["rebalancing", "tax_optimization", "analysis"])
    )
    def test_property_62_workflow_duration_emitted(self, metrics_client, workflow_duration, workflow_type):
        """
        For any workflow duration value, when emitted, a metric should be 
        recorded in CloudWatch with the correct value and workflow type dimension.
        """
        # Emit the metric
        metrics_client.emit_workflow_duration(
            workflow_type=workflow_type,
            duration_seconds=workflow_duration
        )
        
        # Verify the metric was emitted
        assert metrics_client.cloudwatch.put_metric_data.called
        
        # Extract the call arguments
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        assert call_args is not None
        
        # Verify metric data
        metric_data = call_args[1]['MetricData']
        assert len(metric_data) > 0
        
        # Find the WorkflowDuration metric
        workflow_metric = None
        for metric in metric_data:
            if metric.get('MetricName') == 'WorkflowDuration':
                workflow_metric = metric
                break
        
        assert workflow_metric is not None, "WorkflowDuration metric not found"
        assert workflow_metric['Value'] == workflow_duration
        assert workflow_metric['Unit'] == 'Seconds'
        
        # Verify workflow type dimension
        dimensions = {d['Name']: d['Value'] for d in workflow_metric.get('Dimensions', [])}
        assert dimensions.get('WorkflowType') == workflow_type

    @given(
        success_count=st.integers(min_value=0, max_value=100),
        order_type=st.sampled_from(["market", "limit"])
    )
    def test_property_62_trade_execution_success_emitted(self, metrics_client, success_count, order_type):
        """
        For any trade execution success status, when emitted, a metric should be 
        recorded in CloudWatch with the correct value and order type dimension.
        """
        # Emit the metric for success
        metrics_client.emit_trade_execution_success(
            order_type=order_type,
            success=True
        )
        
        # Verify the metric was emitted
        assert metrics_client.cloudwatch.put_metric_data.called
        
        # Extract the call arguments
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        assert call_args is not None
        
        # Verify metric data
        metric_data = call_args[1]['MetricData']
        assert len(metric_data) > 0
        
        # Find the TradeExecutionSuccess metric
        trade_metric = None
        for metric in metric_data:
            if metric.get('MetricName') == 'TradeExecutionSuccess':
                trade_metric = metric
                break
        
        assert trade_metric is not None, "TradeExecutionSuccess metric not found"
        assert trade_metric['Value'] == 1.0  # Success = 1.0
        assert trade_metric['Unit'] == 'Count'
        
        # Verify order type dimension
        dimensions = {d['Name']: d['Value'] for d in trade_metric.get('Dimensions', [])}
        assert dimensions.get('OrderType') == order_type
        assert dimensions.get('Status') == 'success'

    @given(
        query_latency=st.integers(min_value=1, max_value=5000),
        table_name=st.sampled_from(["Portfolios", "Transactions", "AgentSessions", "MarketDataCache"])
    )
    def test_property_62_dynamodb_query_latency_emitted(self, metrics_client, query_latency, table_name):
        """
        For any DynamoDB query latency value, when emitted, a metric should be 
        recorded in CloudWatch with the correct value and table name dimension.
        """
        # Emit the metric
        metrics_client.emit_dynamodb_query_latency(
            table_name=table_name,
            latency_ms=query_latency
        )
        
        # Verify the metric was emitted
        assert metrics_client.cloudwatch.put_metric_data.called
        
        # Extract the call arguments
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        assert call_args is not None
        
        # Verify metric data
        metric_data = call_args[1]['MetricData']
        assert len(metric_data) > 0
        
        # Find the DynamoDBQueryLatency metric
        latency_metric = None
        for metric in metric_data:
            if metric.get('MetricName') == 'DynamoDBQueryLatency':
                latency_metric = metric
                break
        
        assert latency_metric is not None, "DynamoDBQueryLatency metric not found"
        assert latency_metric['Value'] == query_latency
        assert latency_metric['Unit'] == 'Milliseconds'
        
        # Verify table name dimension
        dimensions = {d['Name']: d['Value'] for d in latency_metric.get('Dimensions', [])}
        assert dimensions.get('TableName') == table_name

    @given(
        response_time=agent_response_time_strategy(),
        agent_type=agent_type_strategy()
    )
    def test_property_62_metric_has_timestamp(self, metrics_client, response_time, agent_type):
        """
        For any emitted metric, the metric should include a timestamp 
        indicating when it was recorded.
        """
        # Emit the metric
        metrics_client.emit_agent_response_time(
            response_time_ms=response_time,
            agent_type=agent_type
        )
        
        # Verify the metric was emitted
        assert metrics_client.cloudwatch.put_metric_data.called
        
        # Extract the call arguments
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        # Verify each metric has a timestamp
        for metric in metric_data:
            assert 'Timestamp' in metric
            assert isinstance(metric['Timestamp'], datetime)
            # Timestamp should be recent (within last minute)
            time_diff = datetime.utcnow() - metric['Timestamp']
            assert time_diff.total_seconds() < 60

    @given(
        response_time=agent_response_time_strategy(),
        agent_type=agent_type_strategy()
    )
    def test_property_62_metric_with_custom_dimensions(self, metrics_client, response_time, agent_type):
        """
        For any metric with custom dimensions, all dimensions should be 
        included in the emitted metric.
        """
        # Emit the metric using emit_metric directly to test custom dimensions
        custom_dimensions = {"CustomKey": "CustomValue"}
        metrics_client.emit_metric(
            metric_name="TestMetric",
            value=response_time,
            unit=MetricUnit.MILLISECONDS,
            dimensions=custom_dimensions
        )
        
        # Verify the metric was emitted
        assert metrics_client.cloudwatch.put_metric_data.called
        
        # Extract the call arguments
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        # Find the TestMetric metric
        test_metric = None
        for metric in metric_data:
            if metric.get('MetricName') == 'TestMetric':
                test_metric = metric
                break
        
        assert test_metric is not None
        
        # Verify all custom dimensions are present
        dimensions = {d['Name']: d['Value'] for d in test_metric.get('Dimensions', [])}
        for key, value in custom_dimensions.items():
            assert dimensions.get(key) == value


# ============================================================================
# Property 63: Request Count Tracking
# ============================================================================

class TestRequestCountTrackingProperties:
    """
    **Validates: Requirements 15.2**
    
    Property 63: Request Count Tracking
    
    For any one-hour time period, the system should track and record 
    the number of requests processed per agent type.
    """

    @pytest.fixture
    def metrics_client(self):
        """Create a mocked CloudWatch metrics client."""
        with patch('boto3.client') as mock_boto_client:
            mock_cloudwatch = MagicMock()
            mock_boto_client.return_value = mock_cloudwatch
            client = CloudWatchMetrics(namespace="TestMetrics")
            client.cloudwatch = mock_cloudwatch
            yield client

    @given(
        request_count=request_count_strategy(),
        agent_type=agent_type_strategy()
    )
    def test_property_63_request_count_emitted(self, metrics_client, request_count, agent_type):
        """
        For any request count value, when emitted, a metric should be 
        recorded in CloudWatch with the correct count and agent type dimension.
        """
        # Emit the metric
        metrics_client.emit_request_count(
            agent_type=agent_type,
            count=request_count
        )
        
        # Verify the metric was emitted
        assert metrics_client.cloudwatch.put_metric_data.called
        
        # Extract the call arguments
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        assert call_args is not None
        
        # Verify metric data
        metric_data = call_args[1]['MetricData']
        assert len(metric_data) > 0
        
        # Find the RequestCount metric
        request_metric = None
        for metric in metric_data:
            if metric.get('MetricName') == 'RequestCount':
                request_metric = metric
                break
        
        assert request_metric is not None, "RequestCount metric not found"
        assert request_metric['Value'] == request_count
        assert request_metric['Unit'] == 'Count'
        
        # Verify agent type dimension
        dimensions = {d['Name']: d['Value'] for d in request_metric.get('Dimensions', [])}
        assert dimensions.get('AgentType') == agent_type

    @given(
        counts=st.lists(
            st.tuples(agent_type_strategy(), request_count_strategy()),
            min_size=1,
            max_size=4,
            unique_by=lambda x: x[0]  # Unique agent types
        )
    )
    def test_property_63_multiple_agent_types_tracked(self, metrics_client, counts):
        """
        For any set of agent types, each agent type's request count should be 
        tracked independently and emitted as separate metrics.
        """
        # Emit metrics for each agent type
        for agent_type, count in counts:
            metrics_client.emit_request_count(
                agent_type=agent_type,
                count=count
            )
        
        # Verify metrics were emitted
        assert metrics_client.cloudwatch.put_metric_data.call_count >= len(counts)
        
        # Collect all emitted metrics
        all_metrics = []
        for call in metrics_client.cloudwatch.put_metric_data.call_args_list:
            metric_data = call[1]['MetricData']
            all_metrics.extend(metric_data)
        
        # Verify each agent type has a RequestCount metric
        emitted_agent_types = set()
        for metric in all_metrics:
            if metric.get('MetricName') == 'RequestCount':
                dimensions = {d['Name']: d['Value'] for d in metric.get('Dimensions', [])}
                agent_type = dimensions.get('AgentType')
                if agent_type:
                    emitted_agent_types.add(agent_type)
        
        # All agent types should have been tracked
        for agent_type, _ in counts:
            assert agent_type in emitted_agent_types

    @given(
        request_count=request_count_strategy(),
        agent_type=agent_type_strategy()
    )
    def test_property_63_request_count_is_non_negative(self, metrics_client, request_count, agent_type):
        """
        For any request count metric, the value should be non-negative 
        (request counts cannot be negative).
        """
        # Emit the metric
        metrics_client.emit_request_count(
            agent_type=agent_type,
            count=request_count
        )
        
        # Extract the emitted metric
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        # Find the RequestCount metric
        request_metric = None
        for metric in metric_data:
            if metric.get('MetricName') == 'RequestCount':
                request_metric = metric
                break
        
        assert request_metric is not None
        assert request_metric['Value'] >= 0

    @given(
        request_count=request_count_strategy(),
        agent_type=agent_type_strategy()
    )
    def test_property_63_request_count_metric_unit_is_count(self, metrics_client, request_count, agent_type):
        """
        For any request count metric, the unit should be 'Count' 
        to indicate it's a count-based metric.
        """
        # Emit the metric
        metrics_client.emit_request_count(
            agent_type=agent_type,
            count=request_count
        )
        
        # Extract the emitted metric
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        # Find the RequestCount metric
        request_metric = None
        for metric in metric_data:
            if metric.get('MetricName') == 'RequestCount':
                request_metric = metric
                break
        
        assert request_metric is not None
        assert request_metric['Unit'] == 'Count'

    @given(
        request_count=request_count_strategy(),
        agent_type=agent_type_strategy()
    )
    def test_property_63_request_count_has_timestamp(self, metrics_client, request_count, agent_type):
        """
        For any request count metric, the metric should include a timestamp 
        indicating when the count was recorded.
        """
        # Emit the metric
        metrics_client.emit_request_count(
            agent_type=agent_type,
            count=request_count
        )
        
        # Extract the emitted metric
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        # Find the RequestCount metric
        request_metric = None
        for metric in metric_data:
            if metric.get('MetricName') == 'RequestCount':
                request_metric = metric
                break
        
        assert request_metric is not None
        assert 'Timestamp' in request_metric
        assert isinstance(request_metric['Timestamp'], datetime)


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================

class TestMetricsEmissionEdgeCases:
    """Test edge cases for metrics emission."""

    @pytest.fixture
    def metrics_client(self):
        """Create a mocked CloudWatch metrics client."""
        with patch('boto3.client') as mock_boto_client:
            mock_cloudwatch = MagicMock()
            mock_boto_client.return_value = mock_cloudwatch
            client = CloudWatchMetrics(namespace="TestMetrics")
            client.cloudwatch = mock_cloudwatch
            yield client

    def test_zero_response_time(self, metrics_client):
        """Test that zero response time is handled correctly."""
        metrics_client.emit_agent_response_time(
            agent_type="portfolio_analyzer",
            response_time_ms=0
        )
        
        assert metrics_client.cloudwatch.put_metric_data.called
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        agent_response_metric = None
        for metric in metric_data:
            if metric.get('MetricName') == 'AgentResponseTime':
                agent_response_metric = metric
                break
        
        assert agent_response_metric is not None
        assert agent_response_metric['Value'] == 0

    def test_zero_request_count(self, metrics_client):
        """Test that zero request count is handled correctly."""
        metrics_client.emit_request_count(
            agent_type="portfolio_analyzer",
            count=0
        )
        
        assert metrics_client.cloudwatch.put_metric_data.called
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        request_metric = None
        for metric in metric_data:
            if metric.get('MetricName') == 'RequestCount':
                request_metric = metric
                break
        
        assert request_metric is not None
        assert request_metric['Value'] == 0

    def test_batch_metrics_emission(self, metrics_client):
        """Test that multiple metrics can be emitted in a batch."""
        metrics = [
            {
                'MetricName': 'AgentResponseTime',
                'Value': 1500,
                'Unit': 'Milliseconds',
                'Dimensions': [{'Name': 'AgentType', 'Value': 'portfolio_analyzer'}]
            },
            {
                'MetricName': 'RequestCount',
                'Value': 100,
                'Unit': 'Count',
                'Dimensions': [{'Name': 'AgentType', 'Value': 'portfolio_analyzer'}]
            }
        ]
        
        metrics_client.emit_batch_metrics(metrics)
        
        assert metrics_client.cloudwatch.put_metric_data.called
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        assert len(metric_data) >= 2

    def test_metrics_with_empty_dimensions(self, metrics_client):
        """Test that metrics can be emitted with empty custom dimensions."""
        metrics_client.emit_agent_response_time(
            agent_type="portfolio_analyzer",
            response_time_ms=1000
        )
        
        assert metrics_client.cloudwatch.put_metric_data.called
        call_args = metrics_client.cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        agent_response_metric = None
        for metric in metric_data:
            if metric.get('MetricName') == 'AgentResponseTime':
                agent_response_metric = metric
                break
        
        assert agent_response_metric is not None
        # Should still have at least the AgentType dimension
        dimensions = {d['Name']: d['Value'] for d in agent_response_metric.get('Dimensions', [])}
        assert 'AgentType' in dimensions
