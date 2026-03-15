"""
Unit tests for CloudWatch Alarms management module.

Tests the CloudWatchAlarms class for creating, managing, and monitoring alarms.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime

from src.utils.cloudwatch_alarms import (
    CloudWatchAlarms,
    AlarmState,
    ComparisonOperator,
    Statistic,
    create_alarms_manager
)


class TestCloudWatchAlarms:
    """Test CloudWatchAlarms class."""

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

    def test_initialization(self):
        """Test CloudWatchAlarms initialization."""
        with patch('boto3.client'):
            manager = CloudWatchAlarms(region="us-west-2")
            assert manager.region == "us-west-2"

    def test_create_alarm_success(self, alarms_manager):
        """Test successful alarm creation."""
        result = alarms_manager.create_alarm(
            alarm_name="TestAlarm",
            metric_name="TestMetric",
            namespace="TestNamespace",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=2,
            threshold=100.0,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Test alarm"
        )
        
        assert result is True
        assert alarms_manager.cloudwatch.put_metric_alarm.called

    def test_create_alarm_with_dimensions(self, alarms_manager):
        """Test alarm creation with dimensions."""
        dimensions = {"AgentType": "portfolio_analyzer"}
        
        result = alarms_manager.create_alarm(
            alarm_name="TestAlarm",
            metric_name="AgentResponseTime",
            namespace="MultiAgentAdvisorySystem",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=2,
            threshold=5000.0,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            dimensions=dimensions
        )
        
        assert result is True
        
        # Verify dimensions were passed correctly
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert 'Dimensions' in call_args[1]
        dimensions_list = call_args[1]['Dimensions']
        assert len(dimensions_list) == 1
        assert dimensions_list[0]['Name'] == 'AgentType'
        assert dimensions_list[0]['Value'] == 'portfolio_analyzer'

    def test_create_alarm_with_actions(self, alarms_manager):
        """Test alarm creation with SNS actions."""
        alarm_actions = ["arn:aws:sns:us-east-1:123456789:admin-alerts"]
        
        result = alarms_manager.create_alarm(
            alarm_name="TestAlarm",
            metric_name="TestMetric",
            namespace="TestNamespace",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=2,
            threshold=100.0,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_actions=alarm_actions
        )
        
        assert result is True
        
        # Verify alarm actions were passed
        call_args = alarms_manager.cloudwatch.put_metric_alarm.call_args
        assert 'AlarmActions' in call_args[1]
        assert call_args[1]['AlarmActions'] == alarm_actions

    def test_create_alarm_error(self, alarms_manager):
        """Test alarm creation with error."""
        alarms_manager.cloudwatch.put_metric_alarm.side_effect = Exception("API Error")
        
        result = alarms_manager.create_alarm(
            alarm_name="TestAlarm",
            metric_name="TestMetric",
            namespace="TestNamespace",
            statistic=Statistic.AVERAGE,
            period=300,
            evaluation_periods=2,
            threshold=100.0,
            comparison_operator=ComparisonOperator.GREATER_THAN_THRESHOLD
        )
        
        assert result is False

    def test_delete_alarm_success(self, alarms_manager):
        """Test successful alarm deletion."""
        result = alarms_manager.delete_alarm("TestAlarm")
        
        assert result is True
        alarms_manager.cloudwatch.delete_alarms.assert_called_once_with(
            AlarmNames=["TestAlarm"]
        )

    def test_delete_alarm_error(self, alarms_manager):
        """Test alarm deletion with error."""
        alarms_manager.cloudwatch.delete_alarms.side_effect = Exception("API Error")
        
        result = alarms_manager.delete_alarm("TestAlarm")
        
        assert result is False

    def test_get_alarm_state_ok(self, alarms_manager):
        """Test getting alarm state when OK."""
        alarms_manager.cloudwatch.describe_alarms.return_value = {
            'MetricAlarms': [
                {
                    'AlarmName': 'TestAlarm',
                    'StateValue': 'OK'
                }
            ]
        }
        
        state = alarms_manager.get_alarm_state("TestAlarm")
        
        assert state == AlarmState.OK

    def test_get_alarm_state_alarm(self, alarms_manager):
        """Test getting alarm state when ALARM."""
        alarms_manager.cloudwatch.describe_alarms.return_value = {
            'MetricAlarms': [
                {
                    'AlarmName': 'TestAlarm',
                    'StateValue': 'ALARM'
                }
            ]
        }
        
        state = alarms_manager.get_alarm_state("TestAlarm")
        
        assert state == AlarmState.ALARM

    def test_get_alarm_state_not_found(self, alarms_manager):
        """Test getting alarm state when alarm not found."""
        alarms_manager.cloudwatch.describe_alarms.return_value = {
            'MetricAlarms': []
        }
        
        state = alarms_manager.get_alarm_state("NonExistentAlarm")
        
        assert state is None

    def test_list_alarms(self, alarms_manager):
        """Test listing alarms."""
        alarms_manager.cloudwatch.describe_alarms.return_value = {
            'MetricAlarms': [
                {
                    'AlarmName': 'Alarm1',
                    'MetricName': 'Metric1',
                    'Namespace': 'Namespace1',
                    'StateValue': 'OK',
                    'Threshold': 100.0,
                    'ComparisonOperator': 'GreaterThanThreshold',
                    'EvaluationPeriods': 2,
                    'Period': 300
                },
                {
                    'AlarmName': 'Alarm2',
                    'MetricName': 'Metric2',
                    'Namespace': 'Namespace2',
                    'StateValue': 'ALARM',
                    'Threshold': 200.0,
                    'ComparisonOperator': 'LessThanThreshold',
                    'EvaluationPeriods': 1,
                    'Period': 60
                }
            ]
        }
        
        alarms = alarms_manager.list_alarms()
        
        assert len(alarms) == 2
        assert alarms[0]['AlarmName'] == 'Alarm1'
        assert alarms[1]['AlarmName'] == 'Alarm2'

    def test_list_alarms_with_state_filter(self, alarms_manager):
        """Test listing alarms with state filter."""
        alarms_manager.cloudwatch.describe_alarms.return_value = {
            'MetricAlarms': [
                {
                    'AlarmName': 'Alarm1',
                    'MetricName': 'Metric1',
                    'Namespace': 'Namespace1',
                    'StateValue': 'ALARM',
                    'Threshold': 100.0,
                    'ComparisonOperator': 'GreaterThanThreshold',
                    'EvaluationPeriods': 2,
                    'Period': 300
                }
            ]
        }
        
        alarms = alarms_manager.list_alarms(state_filter=AlarmState.ALARM)
        
        assert len(alarms) == 1
        assert alarms[0]['State'] == 'ALARM'
        
        # Verify state filter was passed
        call_args = alarms_manager.cloudwatch.describe_alarms.call_args
        assert call_args[1]['StateValue'] == 'ALARM'

    def test_enable_alarm_actions(self, alarms_manager):
        """Test enabling alarm actions."""
        alarm_names = ["Alarm1", "Alarm2"]
        
        result = alarms_manager.enable_alarm_actions(alarm_names)
        
        assert result is True
        alarms_manager.cloudwatch.enable_alarm_actions.assert_called_once_with(
            AlarmNames=alarm_names
        )

    def test_disable_alarm_actions(self, alarms_manager):
        """Test disabling alarm actions."""
        alarm_names = ["Alarm1", "Alarm2"]
        
        result = alarms_manager.disable_alarm_actions(alarm_names)
        
        assert result is True
        alarms_manager.cloudwatch.disable_alarm_actions.assert_called_once_with(
            AlarmNames=alarm_names
        )

    def test_set_alarm_state(self, alarms_manager):
        """Test setting alarm state."""
        result = alarms_manager.set_alarm_state(
            alarm_name="TestAlarm",
            state=AlarmState.ALARM,
            state_reason="Testing alarm state"
        )
        
        assert result is True
        alarms_manager.cloudwatch.set_alarm_state.assert_called_once_with(
            AlarmName="TestAlarm",
            StateValue="ALARM",
            StateReason="Testing alarm state"
        )

    def test_get_alarm_history(self, alarms_manager):
        """Test getting alarm history."""
        alarms_manager.cloudwatch.describe_alarm_history.return_value = {
            'AlarmHistoryItems': [
                {
                    'Timestamp': datetime.utcnow(),
                    'HistoryItemType': 'StateUpdate',
                    'HistorySummary': 'Alarm triggered',
                    'HistoryData': '{"newState":"ALARM"}'
                },
                {
                    'Timestamp': datetime.utcnow(),
                    'HistoryItemType': 'StateUpdate',
                    'HistorySummary': 'Alarm recovered',
                    'HistoryData': '{"newState":"OK"}'
                }
            ]
        }
        
        history = alarms_manager.get_alarm_history("TestAlarm")
        
        assert len(history) == 2
        assert history[0]['HistoryItemType'] == 'StateUpdate'
        assert history[1]['HistoryItemType'] == 'StateUpdate'

    def test_get_alarm_history_with_max_records(self, alarms_manager):
        """Test getting alarm history with max records."""
        alarms_manager.cloudwatch.describe_alarm_history.return_value = {
            'AlarmHistoryItems': []
        }
        
        history = alarms_manager.get_alarm_history("TestAlarm", max_records=50)
        
        # Verify max_records was passed
        call_args = alarms_manager.cloudwatch.describe_alarm_history.call_args
        assert call_args[1]['MaxRecords'] == 50


class TestAlarmState:
    """Test AlarmState enum."""

    def test_alarm_state_values(self):
        """Test AlarmState enum values."""
        assert AlarmState.OK.value == "OK"
        assert AlarmState.ALARM.value == "ALARM"
        assert AlarmState.INSUFFICIENT_DATA.value == "INSUFFICIENT_DATA"


class TestComparisonOperator:
    """Test ComparisonOperator enum."""

    def test_comparison_operator_values(self):
        """Test ComparisonOperator enum values."""
        assert ComparisonOperator.GREATER_THAN_THRESHOLD.value == "GreaterThanThreshold"
        assert ComparisonOperator.LESS_THAN_THRESHOLD.value == "LessThanThreshold"


class TestStatistic:
    """Test Statistic enum."""

    def test_statistic_values(self):
        """Test Statistic enum values."""
        assert Statistic.AVERAGE.value == "Average"
        assert Statistic.SUM.value == "Sum"
        assert Statistic.MINIMUM.value == "Minimum"
        assert Statistic.MAXIMUM.value == "Maximum"


class TestCreateAlarmsManager:
    """Test create_alarms_manager factory function."""

    def test_create_alarms_manager_default_region(self):
        """Test creating alarms manager with default region."""
        with patch('boto3.client'):
            manager = create_alarms_manager()
            assert manager.region == "us-east-1"

    def test_create_alarms_manager_custom_region(self):
        """Test creating alarms manager with custom region."""
        with patch('boto3.client'):
            manager = create_alarms_manager(region="us-west-2")
            assert manager.region == "us-west-2"
