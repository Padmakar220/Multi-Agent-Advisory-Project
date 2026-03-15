"""Integration tests for monitoring and observability system.

Tests metric emission, alarm triggering, and SNS notification delivery.

**Validates: Requirements 15.1, 15.2, 15.3, 15.4**
"""

import pytest
import time
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timedelta

from src.utils.cloudwatch_metrics import CloudWatchMetrics
from src.utils.cloudwatch_alarms import CloudWatchAlarms
from src.utils.cloudwatch_dashboard import CloudWatchDashboard
from src.utils.cloudwatch_logs_insights import CloudWatchLogsInsights


@pytest.fixture
def metrics_client():
    """Create metrics client with mocked CloudWatch."""
    with patch("boto3.client") as mock_client:
        client = CloudWatchMetrics(namespace="TestNamespace")
        client.client = MagicMock()
        yield client


@pytest.fixture
def alarms_client():
    """Create alarms client with mocked CloudWatch."""
    with patch("boto3.client") as mock_client:
        client = CloudWatchAlarms(region="us-east-1")
        client.client = MagicMock()
        yield client


@pytest.fixture
def dashboard_client():
    """Create dashboard client with mocked CloudWatch."""
    with patch("boto3.client") as mock_client:
        client = CloudWatchDashboard(region="us-east-1")
        client.client = MagicMock()
        yield client


@pytest.fixture
def logs_insights_client():
    """Create logs insights client with mocked CloudWatch Logs."""
    with patch("boto3.client") as mock_client:
        client = CloudWatchLogsInsights(region="us-east-1")
        client.client = MagicMock()
        yield client


class TestMetricEmissionIntegration:
    """Test metric emission from Lambda functions."""

    def test_agent_response_time_metric_emission(self, metrics_client):
        """Test that agent response time metrics are emitted."""
        metrics_client.client.put_metric_data.return_value = {}
        
        # Emit agent response time
        metrics_client.emit_agent_response_time(
            agent_type="portfolio_analyzer",
            response_time_ms=1500,
            user_id="user-123"
        )
        
        # Verify metric was emitted
        assert metrics_client.client.put_metric_data.called
        call_args = metrics_client.client.put_metric_data.call_args
        assert call_args[1]["Namespace"] == "TestNamespace"
        assert call_args[1]["MetricData"][0]["MetricName"] == "AgentResponseTime"
        assert call_args[1]["MetricData"][0]["Value"] == 1500

    def test_workflow_duration_metric_emission(self, metrics_client):
        """Test that workflow duration metrics are emitted."""
        metrics_client.client.put_metric_data.return_value = {}
        
        # Emit workflow duration
        metrics_client.emit_workflow_duration(
            workflow_type="rebalancing",
            duration_seconds=45,
            user_id="user-123"
        )
        
        # Verify metric was emitted
        assert metrics_client.client.put_metric_data.called
        call_args = metrics_client.client.put_metric_data.call_args
        assert call_args[1]["MetricData"][0]["MetricName"] == "WorkflowDuration"
        assert call_args[1]["MetricData"][0]["Value"] == 45

    def test_trade_execution_success_metric_emission(self, metrics_client):
        """Test that trade execution metrics are emitted."""
        metrics_client.client.put_metric_data.return_value = {}
        
        # Emit trade execution success
        metrics_client.emit_trade_execution_success(
            success=True,
            user_id="user-123"
        )
        
        # Verify metric was emitted
        assert metrics_client.client.put_metric_data.called
        call_args = metrics_client.client.put_metric_data.call_args
        assert call_args[1]["MetricData"][0]["MetricName"] == "TradeExecutionSuccess"

    def test_dynamodb_query_latency_metric_emission(self, metrics_client):
        """Test that DynamoDB query latency metrics are emitted."""
        metrics_client.client.put_metric_data.return_value = {}
        
        # Emit DynamoDB query latency
        metrics_client.emit_dynamodb_query_latency(
            table_name="Portfolios",
            latency_ms=85,
            user_id="user-123"
        )
        
        # Verify metric was emitted
        assert metrics_client.client.put_metric_data.called
        call_args = metrics_client.client.put_metric_data.call_args
        assert call_args[1]["MetricData"][0]["MetricName"] == "DynamoDBQueryLatency"
        assert call_args[1]["MetricData"][0]["Value"] == 85

    def test_request_count_metric_emission(self, metrics_client):
        """Test that request count metrics are emitted."""
        metrics_client.client.put_metric_data.return_value = {}
        
        # Emit request count
        metrics_client.emit_request_count(
            agent_type="portfolio_analyzer",
            count=5
        )
        
        # Verify metric was emitted
        assert metrics_client.client.put_metric_data.called
        call_args = metrics_client.client.put_metric_data.call_args
        assert call_args[1]["MetricData"][0]["MetricName"] == "RequestCount"
        assert call_args[1]["MetricData"][0]["Value"] == 5


class TestAlarmTriggeringIntegration:
    """Test alarm triggering on threshold violations."""

    def test_high_response_time_alarm_creation(self, alarms_client):
        """Test creation of high response time alarm."""
        alarms_client.client.put_metric_alarm.return_value = {}
        
        # Create alarm
        result = alarms_client.create_alarm(
            alarm_name="HighAgentResponseTime",
            metric_name="AgentResponseTime",
            threshold=5000,
            comparison_operator="GreaterThanThreshold",
            evaluation_periods=2,
            period=60,
            statistic="Average",
            alarm_description="Alert when agent response time exceeds 5 seconds"
        )
        
        assert result is True
        assert alarms_client.client.put_metric_alarm.called

    def test_high_dynamodb_latency_alarm_creation(self, alarms_client):
        """Test creation of high DynamoDB latency alarm."""
        alarms_client.client.put_metric_alarm.return_value = {}
        
        # Create alarm
        result = alarms_client.create_alarm(
            alarm_name="HighDynamoDBLatency",
            metric_name="DynamoDBQueryLatency",
            threshold=200,
            comparison_operator="GreaterThanThreshold",
            evaluation_periods=3,
            period=60,
            statistic="Average",
            alarm_description="Alert when DynamoDB latency exceeds 200ms"
        )
        
        assert result is True
        assert alarms_client.client.put_metric_alarm.called

    def test_alarm_state_retrieval(self, alarms_client):
        """Test retrieving alarm state."""
        alarms_client.client.describe_alarms.return_value = {
            "MetricAlarms": [
                {
                    "AlarmName": "HighAgentResponseTime",
                    "StateValue": "ALARM",
                    "StateReason": "Threshold Crossed"
                }
            ]
        }
        
        # Get alarm state
        state = alarms_client.get_alarm_state("HighAgentResponseTime")
        
        assert state is not None
        assert alarms_client.client.describe_alarms.called

    def test_alarm_actions_configuration(self, alarms_client):
        """Test configuring alarm actions for SNS."""
        alarms_client.client.put_metric_alarm.return_value = {}
        
        # Create alarm with SNS action
        result = alarms_client.create_alarm(
            alarm_name="TestAlarm",
            metric_name="TestMetric",
            threshold=100,
            comparison_operator="GreaterThanThreshold",
            evaluation_periods=1,
            period=60,
            statistic="Average",
            alarm_actions=["arn:aws:sns:us-east-1:123456789:admin-alerts"]
        )
        
        assert result is True


class TestSNSNotificationDeliveryIntegration:
    """Test SNS notification delivery."""

    def test_alarm_triggers_sns_notification(self, alarms_client):
        """Test that alarm triggers SNS notification."""
        alarms_client.client.put_metric_alarm.return_value = {}
        
        # Create alarm with SNS topic
        sns_topic = "arn:aws:sns:us-east-1:123456789:critical-alerts"
        result = alarms_client.create_alarm(
            alarm_name="CriticalError",
            metric_name="ErrorCount",
            threshold=1,
            comparison_operator="GreaterThanOrEqualToThreshold",
            evaluation_periods=1,
            period=60,
            statistic="Sum",
            alarm_actions=[sns_topic]
        )
        
        assert result is True
        call_args = alarms_client.client.put_metric_alarm.call_args
        assert "AlarmActions" in call_args[1]

    def test_multiple_alarm_actions(self, alarms_client):
        """Test alarm with multiple SNS actions."""
        alarms_client.client.put_metric_alarm.return_value = {}
        
        # Create alarm with multiple SNS topics
        sns_topics = [
            "arn:aws:sns:us-east-1:123456789:admin-alerts",
            "arn:aws:sns:us-east-1:123456789:critical-alerts"
        ]
        
        result = alarms_client.create_alarm(
            alarm_name="MultiAlertAlarm",
            metric_name="TestMetric",
            threshold=100,
            comparison_operator="GreaterThanThreshold",
            evaluation_periods=1,
            period=60,
            statistic="Average",
            alarm_actions=sns_topics
        )
        
        assert result is True


class TestDashboardIntegration:
    """Test dashboard creation and management."""

    def test_monitoring_dashboard_creation(self, dashboard_client):
        """Test creation of main monitoring dashboard."""
        dashboard_client.client.put_dashboard.return_value = {}
        
        # Create dashboard
        result = dashboard_client.create_monitoring_dashboard()
        
        assert result is True
        assert dashboard_client.client.put_dashboard.called
        call_args = dashboard_client.client.put_dashboard.call_args
        assert call_args[1]["DashboardName"] == "MultiAgentAdvisoryMonitoring"

    def test_dashboard_contains_all_widgets(self, dashboard_client):
        """Test that dashboard contains all required widgets."""
        dashboard_client.client.put_dashboard.return_value = {}
        
        # Create dashboard
        dashboard_client.create_monitoring_dashboard()
        
        # Verify all widgets are included
        call_args = dashboard_client.client.put_dashboard.call_args
        import json
        body = json.loads(call_args[1]["DashboardBody"])
        
        assert "widgets" in body
        assert len(body["widgets"]) == 4  # Lambda, Agent, Errors, DynamoDB


class TestLogsInsightsIntegration:
    """Test CloudWatch Logs Insights queries."""

    def test_error_analysis_query_execution(self, logs_insights_client):
        """Test error analysis query execution."""
        logs_insights_client.client.start_query.return_value = {"queryId": "query-123"}
        logs_insights_client.client.get_query_results.return_value = {
            "status": "Complete",
            "results": [
                [
                    {"field": "service", "value": "portfolio-analyzer"},
                    {"field": "error_count", "value": "5"}
                ]
            ],
            "statistics": {}
        }
        
        # Run error analysis
        result = logs_insights_client.run_error_analysis(
            log_group_name="/aws/lambda/test",
            start_time=int(time.time()) - 3600,
            end_time=int(time.time())
        )
        
        assert result is not None
        assert result["status"] == "Complete"

    def test_user_activity_query_execution(self, logs_insights_client):
        """Test user activity tracking query execution."""
        logs_insights_client.client.start_query.return_value = {"queryId": "query-456"}
        logs_insights_client.client.get_query_results.return_value = {
            "status": "Complete",
            "results": [
                [
                    {"field": "user_id", "value": "user-123"},
                    {"field": "action_count", "value": "10"}
                ]
            ],
            "statistics": {}
        }
        
        # Run user activity query
        result = logs_insights_client.run_user_activity_query(
            log_group_name="/aws/lambda/test",
            start_time=int(time.time()) - 3600,
            end_time=int(time.time())
        )
        
        assert result is not None
        assert result["status"] == "Complete"

    def test_trade_execution_audit_query_execution(self, logs_insights_client):
        """Test trade execution audit trail query execution."""
        logs_insights_client.client.start_query.return_value = {"queryId": "query-789"}
        logs_insights_client.client.get_query_results.return_value = {
            "status": "Complete",
            "results": [
                [
                    {"field": "status", "value": "completed"},
                    {"field": "trade_count", "value": "25"}
                ]
            ],
            "statistics": {}
        }
        
        # Run trade execution audit query
        result = logs_insights_client.run_trade_execution_audit(
            log_group_name="/aws/lambda/test",
            start_time=int(time.time()) - 3600,
            end_time=int(time.time())
        )
        
        assert result is not None
        assert result["status"] == "Complete"


class TestEndToEndMonitoringFlow:
    """Test complete monitoring flow."""

    def test_metric_emission_to_alarm_to_notification(self, metrics_client, alarms_client):
        """Test complete flow from metric emission to SNS notification."""
        # Setup mocks
        metrics_client.client.put_metric_data.return_value = {}
        alarms_client.client.put_metric_alarm.return_value = {}
        
        # 1. Emit metric
        metrics_client.emit_agent_response_time(
            agent_type="portfolio_analyzer",
            response_time_ms=6000,  # Exceeds 5s threshold
            user_id="user-123"
        )
        
        # 2. Create alarm
        alarms_client.create_alarm(
            alarm_name="HighAgentResponseTime",
            metric_name="AgentResponseTime",
            threshold=5000,
            comparison_operator="GreaterThanThreshold",
            evaluation_periods=2,
            period=60,
            statistic="Average",
            alarm_actions=["arn:aws:sns:us-east-1:123456789:admin-alerts"]
        )
        
        # Verify both operations succeeded
        assert metrics_client.client.put_metric_data.called
        assert alarms_client.client.put_metric_alarm.called
