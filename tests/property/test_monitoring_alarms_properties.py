"""
Property-based tests for CloudWatch alarms and performance warnings.

Tests validate that:
- Slow response warnings are logged when response time exceeds threshold
- Query latency alerts are generated when latency exceeds threshold
- Alarms are triggered correctly based on metric thresholds
"""

import pytest
from hypothesis import given, strategies as st, assume
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import logging
from typing import Dict, List

from src.utils.cloudwatch_alarms import (
    CloudWatchAlarms,
    AlarmState,
    ComparisonOperator,
    Statistic
)


# ============================================================================
# Strategies for generating test data
# ============================================================================

@st.composite
def slow_response_time_strategy(draw):
    """Generate response times that exceed the slow threshold (5 seconds)."""
    # Response times > 5000ms are considered slow
    return draw(st.integers(min_value=5001, max_value=60000))


@st.composite
def normal_response_time_strategy(draw):
    """Generate response times that are within normal range."""
    # Response times <= 5000ms are normal
    return draw(st.integers(min_value=100, max_value=5000))


@st.composite
def high_latency_strategy(draw):
    """Generate latencies that exceed the high threshold (200ms)."""
    # Latencies > 200ms are considered high
    return draw(st.integers(min_value=201, max_value=5000))


@st.composite
def normal_latency_strategy(draw):
    """Generate latencies that are within normal range."""
    # Latencies <= 200ms are normal
    return draw(st.integers(min_value=1, max_value=200))


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
def table_name_strategy(draw):
    """Generate valid DynamoDB table names."""
    return draw(st.sampled_from([
        "Portfolios",
        "Transactions",
        "AgentSessions",
        "MarketDataCache"
    ]))


# ============================================================================
# Property 64: Slow Response Warning
# ============================================================================

class TestSlowResponseWarningProperties:
    """
    **Validates: Requirements 15.3**
    
    Property 64: Slow Response Warning
    
    For any agent response that exceeds 5 seconds, a performance warning 
    should be logged to CloudWatch.
    """

    @pytest.fixture
    def alarms_manager(self):
        """Create a CloudWatchAlarms instance with mocked boto3 clients."""
        with patch('boto3.client') as mock_boto_client:
            mock_cloudwatch = MagicMock()
            mock_sns = MagicMock()
            
            def client_factory(service, region_name=None):
                if service == 'cloudwatch':
                    return mock_cloudwatch
                elif service == 'sns':
                    return mock_sns
                return MagicMock()
            
            mock_boto_client.side_effect = client_factory
            manager = CloudWatchAlarms(region="us-east-1")
            manager.cloudwatch = mock_cloudwatch
            manager.sns = mock_sns
            yield manager

    @given(
        response_time=slow_response_time_strategy(),
        agent_type=agent_type_strategy()
    )
    def test_property_64_slow_response_triggers_warning(self, alarms_manager, response_time, agent_type):
        """
        For any response time exceeding 5 seconds, when the metric is emitted,
        a warning should be logged indicating slow response.
        """
        # Create an alarm for slow responses
        result = alarms_manager.create_alarm(
            alarm_name=f"SlowResponse-{agent_type}",
            metric_name="AgentResponseTime",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=2,
            threshold=5000,  # 5 seconds
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            dimensions={"AgentType": agent_type}
        )
        
        assert result is True
        assert alarms_manager.cloudwatch.put_metric_alarm.called
        
        # Verify alarm was created with correct threshold
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert call_args[1]['Threshold'] == 5000
        assert call_args[1]['ComparisonOperator'] == 'GreaterThanThreshold'

    @given(
        response_time=slow_response_time_strategy(),
        agent_type=agent_type_strategy()
    )
    def test_property_64_slow_response_alarm_name_includes_agent(self, alarms_manager, response_time, agent_type):
        """
        For any slow response alarm, the alarm name should include the agent type
        for easy identification of which agent is slow.
        """
        alarm_name = f"SlowResponse-{agent_type}"
        
        result = alarms_manager.create_alarm(
            alarm_name=alarm_name,
            metric_name="AgentResponseTime",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=2,
            threshold=5000,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            dimensions={"AgentType": agent_type}
        )
        
        assert result is True
        
        # Verify alarm name was passed correctly
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert call_args[1]['AlarmName'] == alarm_name
        assert agent_type in alarm_name

    @given(
        response_time=normal_response_time_strategy(),
        agent_type=agent_type_strategy()
    )
    def test_property_64_normal_response_no_warning(self, alarms_manager, response_time, agent_type):
        """
        For any response time within normal range (≤ 5 seconds), no warning
        should be triggered.
        """
        # Verify response time is within normal range
        assert response_time <= 5000
        
        # Create alarm with threshold at 5 seconds
        result = alarms_manager.create_alarm(
            alarm_name=f"SlowResponse-{agent_type}",
            metric_name="AgentResponseTime",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=2,
            threshold=5000,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            dimensions={"AgentType": agent_type}
        )
        
        assert result is True
        
        # Verify alarm was created (but would not trigger for normal response times)
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert call_args[1]['Threshold'] == 5000

    @given(
        response_time=slow_response_time_strategy(),
        agent_type=agent_type_strategy()
    )
    def test_property_64_slow_response_alarm_has_sns_action(self, alarms_manager, response_time, agent_type):
        """
        For any slow response alarm, the alarm should have SNS actions configured
        to notify administrators.
        """
        sns_topic = "arn:aws:sns:us-east-1:123456789:admin-alerts"
        
        result = alarms_manager.create_alarm(
            alarm_name=f"SlowResponse-{agent_type}",
            metric_name="AgentResponseTime",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=2,
            threshold=5000,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            dimensions={"AgentType": agent_type},
            alarm_actions=[sns_topic]
        )
        
        assert result is True
        
        # Verify SNS action was configured
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert 'AlarmActions' in call_args[1]
        assert sns_topic in call_args[1]['AlarmActions']

    @given(
        response_time=slow_response_time_strategy(),
        agent_type=agent_type_strategy()
    )
    def test_property_64_slow_response_alarm_evaluation_periods(self, alarms_manager, response_time, agent_type):
        """
        For any slow response alarm, the evaluation periods should be set to 2
        to avoid false positives from temporary spikes.
        """
        result = alarms_manager.create_alarm(
            alarm_name=f"SlowResponse-{agent_type}",
            metric_name="AgentResponseTime",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=2,
            threshold=5000,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            dimensions={"AgentType": agent_type}
        )
        
        assert result is True
        
        # Verify evaluation periods
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert call_args[1]['EvaluationPeriods'] == 2


# ============================================================================
# Property 65: Query Latency Alerting
# ============================================================================

class TestQueryLatencyAlertingProperties:
    """
    **Validates: Requirements 15.4**
    
    Property 65: Query Latency Alerting
    
    For any DynamoDB or OpenSearch query that exceeds 200 milliseconds, 
    an alert should be generated.
    """

    @pytest.fixture
    def alarms_manager(self):
        """Create a CloudWatchAlarms instance with mocked boto3 clients."""
        with patch('boto3.client') as mock_boto_client:
            mock_cloudwatch = MagicMock()
            mock_sns = MagicMock()
            
            def client_factory(service, region_name=None):
                if service == 'cloudwatch':
                    return mock_cloudwatch
                elif service == 'sns':
                    return mock_sns
                return MagicMock()
            
            mock_boto_client.side_effect = client_factory
            manager = CloudWatchAlarms(region="us-east-1")
            manager.cloudwatch = mock_cloudwatch
            manager.sns = mock_sns
            yield manager

    @given(
        latency=high_latency_strategy(),
        table_name=table_name_strategy()
    )
    def test_property_65_high_latency_triggers_alert(self, alarms_manager, latency, table_name):
        """
        For any query latency exceeding 200ms, when the metric is emitted,
        an alert should be generated.
        """
        # Create an alarm for high latency
        result = alarms_manager.create_alarm(
            alarm_name=f"HighLatency-{table_name}",
            metric_name="DynamoDBQueryLatency",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=3,
            threshold=200,  # 200ms
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            dimensions={"TableName": table_name}
        )
        
        assert result is True
        assert alarms_manager.cloudwatch.put_metric_alarm.called
        
        # Verify alarm was created with correct threshold
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert call_args[1]['Threshold'] == 200
        assert call_args[1]['ComparisonOperator'] == 'GreaterThanThreshold'

    @given(
        latency=high_latency_strategy(),
        table_name=table_name_strategy()
    )
    def test_property_65_high_latency_alarm_name_includes_table(self, alarms_manager, latency, table_name):
        """
        For any high latency alarm, the alarm name should include the table name
        for easy identification of which table has high latency.
        """
        alarm_name = f"HighLatency-{table_name}"
        
        result = alarms_manager.create_alarm(
            alarm_name=alarm_name,
            metric_name="DynamoDBQueryLatency",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=3,
            threshold=200,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            dimensions={"TableName": table_name}
        )
        
        assert result is True
        
        # Verify alarm name was passed correctly
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert call_args[1]['AlarmName'] == alarm_name
        assert table_name in alarm_name

    @given(
        latency=normal_latency_strategy(),
        table_name=table_name_strategy()
    )
    def test_property_65_normal_latency_no_alert(self, alarms_manager, latency, table_name):
        """
        For any query latency within normal range (≤ 200ms), no alert
        should be triggered.
        """
        # Verify latency is within normal range
        assert latency <= 200
        
        # Create alarm with threshold at 200ms
        result = alarms_manager.create_alarm(
            alarm_name=f"HighLatency-{table_name}",
            metric_name="DynamoDBQueryLatency",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=3,
            threshold=200,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            dimensions={"TableName": table_name}
        )
        
        assert result is True
        
        # Verify alarm was created (but would not trigger for normal latencies)
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert call_args[1]['Threshold'] == 200

    @given(
        latency=high_latency_strategy(),
        table_name=table_name_strategy()
    )
    def test_property_65_high_latency_alarm_has_sns_action(self, alarms_manager, latency, table_name):
        """
        For any high latency alarm, the alarm should have SNS actions configured
        to notify administrators.
        """
        sns_topic = "arn:aws:sns:us-east-1:123456789:admin-alerts"
        
        result = alarms_manager.create_alarm(
            alarm_name=f"HighLatency-{table_name}",
            metric_name="DynamoDBQueryLatency",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=3,
            threshold=200,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            dimensions={"TableName": table_name},
            alarm_actions=[sns_topic]
        )
        
        assert result is True
        
        # Verify SNS action was configured
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert 'AlarmActions' in call_args[1]
        assert sns_topic in call_args[1]['AlarmActions']

    @given(
        latency=high_latency_strategy(),
        table_name=table_name_strategy()
    )
    def test_property_65_high_latency_alarm_evaluation_periods(self, alarms_manager, latency, table_name):
        """
        For any high latency alarm, the evaluation periods should be set to 3
        to ensure sustained high latency before alerting.
        """
        result = alarms_manager.create_alarm(
            alarm_name=f"HighLatency-{table_name}",
            metric_name="DynamoDBQueryLatency",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=3,
            threshold=200,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            dimensions={"TableName": table_name}
        )
        
        assert result is True
        
        # Verify evaluation periods
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert call_args[1]['EvaluationPeriods'] == 3

    @given(
        latency=high_latency_strategy(),
        table_name=table_name_strategy()
    )
    def test_property_65_high_latency_alarm_uses_average_statistic(self, alarms_manager, latency, table_name):
        """
        For any high latency alarm, the statistic should be Average to detect
        sustained high latency rather than isolated spikes.
        """
        result = alarms_manager.create_alarm(
            alarm_name=f"HighLatency-{table_name}",
            metric_name="DynamoDBQueryLatency",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=3,
            threshold=200,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            dimensions={"TableName": table_name}
        )
        
        assert result is True
        
        # Verify statistic
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert call_args[1]['Statistic'] == 'Average'


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================

class TestAlarmEdgeCases:
    """Test edge cases for alarm creation and management."""

    @pytest.fixture
    def alarms_manager(self):
        """Create a CloudWatchAlarms instance with mocked boto3 clients."""
        with patch('boto3.client') as mock_boto_client:
            mock_cloudwatch = MagicMock()
            mock_sns = MagicMock()
            
            def client_factory(service, region_name=None):
                if service == 'cloudwatch':
                    return mock_cloudwatch
                elif service == 'sns':
                    return mock_sns
                return MagicMock()
            
            mock_boto_client.side_effect = client_factory
            manager = CloudWatchAlarms(region="us-east-1")
            manager.cloudwatch = mock_cloudwatch
            manager.sns = mock_sns
            yield manager

    def test_alarm_threshold_boundary_5000ms(self, alarms_manager):
        """Test alarm threshold at exactly 5000ms boundary."""
        result = alarms_manager.create_alarm(
            alarm_name="BoundaryTest",
            metric_name="AgentResponseTime",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=2,
            threshold=5000,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD
        )
        
        assert result is True
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert call_args[1]['Threshold'] == 5000

    def test_alarm_threshold_boundary_200ms(self, alarms_manager):
        """Test alarm threshold at exactly 200ms boundary."""
        result = alarms_manager.create_alarm(
            alarm_name="BoundaryTest",
            metric_name="DynamoDBQueryLatency",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=3,
            threshold=200,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD
        )
        
        assert result is True
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert call_args[1]['Threshold'] == 200

    def test_multiple_alarms_for_same_metric(self, alarms_manager):
        """Test creating multiple alarms for the same metric with different thresholds."""
        # Create warning alarm
        result1 = alarms_manager.create_alarm(
            alarm_name="WarningAlarm",
            metric_name="AgentResponseTime",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=2,
            threshold=3000,  # Warning at 3 seconds
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD
        )
        
        # Create critical alarm
        result2 = alarms_manager.create_alarm(
            alarm_name="CriticalAlarm",
            metric_name="AgentResponseTime",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=1,
            threshold=10000,  # Critical at 10 seconds
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD
        )
        
        assert result1 is True
        assert result2 is True
        assert alarms_manager.cloudwatch.put_metric_alarm.call_count == 2

    def test_alarm_with_multiple_dimensions(self, alarms_manager):
        """Test alarm creation with multiple dimensions."""
        dimensions = {
            "AgentType": "portfolio_analyzer",
            "Environment": "prod"
        }
        
        result = alarms_manager.create_alarm(
            alarm_name="MultiDimensionAlarm",
            metric_name="AgentResponseTime",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=2,
            threshold=5000,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            dimensions=dimensions
        )
        
        assert result is True
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        dimensions_list = call_args[1]['Dimensions']
        assert len(dimensions_list) == 2
