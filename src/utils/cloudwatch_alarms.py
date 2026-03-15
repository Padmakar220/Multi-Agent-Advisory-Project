"""
CloudWatch Alarms Management Module

Provides utilities for creating, updating, and managing CloudWatch alarms
for the Multi-Agent Advisory System.
"""

import boto3
import logging
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class AlarmState(Enum):
    """CloudWatch alarm states."""
    OK = "OK"
    ALARM = "ALARM"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ComparisonOperator(Enum):
    """CloudWatch alarm comparison operators."""
    GREATER_THAN_THRESHOLD = "GreaterThanThreshold"
    GREATER_THAN_OR_EQUAL_TO_THRESHOLD = "GreaterThanOrEqualToThreshold"
    LESS_THAN_THRESHOLD = "LessThanThreshold"
    LESS_THAN_OR_EQUAL_TO_THRESHOLD = "LessThanOrEqualToThreshold"


class Statistic(Enum):
    """CloudWatch statistics."""
    AVERAGE = "Average"
    SUM = "Sum"
    MINIMUM = "Minimum"
    MAXIMUM = "Maximum"
    SAMPLE_COUNT = "SampleCount"
    P99 = "p99"
    P95 = "p95"


class CloudWatchAlarms:
    """Manages CloudWatch alarms for monitoring system performance."""

    def __init__(self, region: str = "us-east-1"):
        """
        Initialize CloudWatch Alarms manager.
        
        Args:
            region: AWS region for CloudWatch
        """
        self.region = region
        self.cloudwatch = boto3.client('cloudwatch', region_name=region)
        self.sns = boto3.client('sns', region_name=region)

    def create_alarm(
        self,
        alarm_name: str,
        metric_name: str,
        namespace: str,
        statistic: Statistic,
        period: int,
        evaluation_periods: int,
        threshold: float,
        comparison_operator: ComparisonOperator,
        alarm_description: Optional[str] = None,
        dimensions: Optional[Dict[str, str]] = None,
        alarm_actions: Optional[List[str]] = None,
        ok_actions: Optional[List[str]] = None,
        insufficient_data_actions: Optional[List[str]] = None,
        treat_missing_data: str = "notBreaching"
    ) -> bool:
        """
        Create a CloudWatch alarm.
        
        Args:
            alarm_name: Name of the alarm
            metric_name: Name of the metric to monitor
            namespace: Namespace of the metric
            statistic: Statistic to use (Average, Sum, etc.)
            period: Period in seconds
            evaluation_periods: Number of periods to evaluate
            threshold: Threshold value
            comparison_operator: Comparison operator
            alarm_description: Description of the alarm
            dimensions: Optional metric dimensions
            alarm_actions: SNS topics to notify when alarm triggers
            ok_actions: SNS topics to notify when alarm recovers
            insufficient_data_actions: SNS topics to notify on insufficient data
            treat_missing_data: How to treat missing data
            
        Returns:
            True if alarm was created successfully
        """
        try:
            params = {
                'AlarmName': alarm_name,
                'MetricName': metric_name,
                'Namespace': namespace,
                'Statistic': statistic.value,
                'Period': period,
                'EvaluationPeriods': evaluation_periods,
                'Threshold': threshold,
                'ComparisonOperator': comparison_operator.value,
                'TreatMissingData': treat_missing_data
            }
            
            if alarm_description:
                params['AlarmDescription'] = alarm_description
            
            if dimensions:
                params['Dimensions'] = [
                    {'Name': k, 'Value': str(v)}
                    for k, v in dimensions.items()
                ]
            
            if alarm_actions:
                params['AlarmActions'] = alarm_actions
            
            if ok_actions:
                params['OKActions'] = ok_actions
            
            if insufficient_data_actions:
                params['InsufficientDataActions'] = insufficient_data_actions
            
            self.cloudwatch.put_metric_alarm(**params)
            
            logger.info(
                f"Created alarm: {alarm_name}",
                alarm_name=alarm_name,
                metric_name=metric_name,
                threshold=threshold
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to create alarm: {str(e)}",
                alarm_name=alarm_name,
                error=str(e)
            )
            return False

    def delete_alarm(self, alarm_name: str) -> bool:
        """
        Delete a CloudWatch alarm.
        
        Args:
            alarm_name: Name of the alarm to delete
            
        Returns:
            True if alarm was deleted successfully
        """
        try:
            self.cloudwatch.delete_alarms(AlarmNames=[alarm_name])
            
            logger.info(
                f"Deleted alarm: {alarm_name}",
                alarm_name=alarm_name
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to delete alarm: {str(e)}",
                alarm_name=alarm_name,
                error=str(e)
            )
            return False

    def get_alarm_state(self, alarm_name: str) -> Optional[AlarmState]:
        """
        Get the current state of an alarm.
        
        Args:
            alarm_name: Name of the alarm
            
        Returns:
            Current alarm state or None if alarm not found
        """
        try:
            response = self.cloudwatch.describe_alarms(AlarmNames=[alarm_name])
            
            if response['MetricAlarms']:
                state = response['MetricAlarms'][0]['StateValue']
                return AlarmState(state)
            
            return None
            
        except Exception as e:
            logger.error(
                f"Failed to get alarm state: {str(e)}",
                alarm_name=alarm_name,
                error=str(e)
            )
            return None

    def list_alarms(self, state_filter: Optional[AlarmState] = None) -> List[Dict[str, Any]]:
        """
        List CloudWatch alarms.
        
        Args:
            state_filter: Optional filter by alarm state
            
        Returns:
            List of alarm details
        """
        try:
            params = {}
            if state_filter:
                params['StateValue'] = state_filter.value
            
            response = self.cloudwatch.describe_alarms(**params)
            
            alarms = []
            for alarm in response['MetricAlarms']:
                alarms.append({
                    'AlarmName': alarm['AlarmName'],
                    'MetricName': alarm['MetricName'],
                    'Namespace': alarm['Namespace'],
                    'State': alarm['StateValue'],
                    'Threshold': alarm['Threshold'],
                    'ComparisonOperator': alarm['ComparisonOperator'],
                    'EvaluationPeriods': alarm['EvaluationPeriods'],
                    'Period': alarm['Period']
                })
            
            return alarms
            
        except Exception as e:
            logger.error(
                f"Failed to list alarms: {str(e)}",
                error=str(e)
            )
            return []

    def enable_alarm_actions(self, alarm_names: List[str]) -> bool:
        """
        Enable actions for alarms.
        
        Args:
            alarm_names: List of alarm names
            
        Returns:
            True if actions were enabled successfully
        """
        try:
            self.cloudwatch.enable_alarm_actions(AlarmNames=alarm_names)
            
            logger.info(
                f"Enabled alarm actions for {len(alarm_names)} alarms",
                alarm_count=len(alarm_names)
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to enable alarm actions: {str(e)}",
                error=str(e)
            )
            return False

    def disable_alarm_actions(self, alarm_names: List[str]) -> bool:
        """
        Disable actions for alarms.
        
        Args:
            alarm_names: List of alarm names
            
        Returns:
            True if actions were disabled successfully
        """
        try:
            self.cloudwatch.disable_alarm_actions(AlarmNames=alarm_names)
            
            logger.info(
                f"Disabled alarm actions for {len(alarm_names)} alarms",
                alarm_count=len(alarm_names)
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to disable alarm actions: {str(e)}",
                error=str(e)
            )
            return False

    def set_alarm_state(
        self,
        alarm_name: str,
        state: AlarmState,
        state_reason: str
    ) -> bool:
        """
        Set the state of an alarm (for testing purposes).
        
        Args:
            alarm_name: Name of the alarm
            state: New alarm state
            state_reason: Reason for state change
            
        Returns:
            True if state was set successfully
        """
        try:
            self.cloudwatch.set_alarm_state(
                AlarmName=alarm_name,
                StateValue=state.value,
                StateReason=state_reason
            )
            
            logger.info(
                f"Set alarm state: {alarm_name} -> {state.value}",
                alarm_name=alarm_name,
                state=state.value
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to set alarm state: {str(e)}",
                alarm_name=alarm_name,
                error=str(e)
            )
            return False

    def get_alarm_history(
        self,
        alarm_name: str,
        max_records: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get the history of an alarm.
        
        Args:
            alarm_name: Name of the alarm
            max_records: Maximum number of records to return
            
        Returns:
            List of alarm history items
        """
        try:
            response = self.cloudwatch.describe_alarm_history(
                AlarmName=alarm_name,
                MaxRecords=max_records
            )
            
            history = []
            for item in response.get('AlarmHistoryItems', []):
                history.append({
                    'Timestamp': item['Timestamp'],
                    'HistoryItemType': item['HistoryItemType'],
                    'HistorySummary': item['HistorySummary'],
                    'HistoryData': item.get('HistoryData')
                })
            
            return history
            
        except Exception as e:
            logger.error(
                f"Failed to get alarm history: {str(e)}",
                alarm_name=alarm_name,
                error=str(e)
            )
            return []


def create_alarms_manager(region: str = "us-east-1") -> CloudWatchAlarms:
    """
    Factory function to create a CloudWatch Alarms manager.
    
    Args:
        region: AWS region
        
    Returns:
        CloudWatchAlarms instance
    """
    return CloudWatchAlarms(region=region)
