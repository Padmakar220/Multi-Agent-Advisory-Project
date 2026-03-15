"""CloudWatch Logs Insights query management for system monitoring."""

from typing import Any, Dict, List, Optional
import boto3
from botocore.exceptions import ClientError


class CloudWatchLogsInsights:
    """Manages CloudWatch Logs Insights queries for system monitoring."""

    def __init__(self, region: str = "us-east-1"):
        """Initialize CloudWatch Logs Insights client.
        
        Args:
            region: AWS region for CloudWatch Logs
        """
        self.region = region
        self.client = boto3.client("logs", region_name=region)

    def start_query(
        self,
        log_group_name: str,
        query: str,
        start_time: int,
        end_time: int,
        limit: int = 1000
    ) -> Optional[str]:
        """Start a CloudWatch Logs Insights query.
        
        Args:
            log_group_name: Name of the log group
            query: CloudWatch Logs Insights query string
            start_time: Start time in seconds since epoch
            end_time: End time in seconds since epoch
            limit: Maximum number of results
            
        Returns:
            Query ID or None if failed
        """
        try:
            response = self.client.start_query(
                logGroupName=log_group_name,
                startTime=start_time,
                endTime=end_time,
                queryString=query,
                limit=limit
            )
            return response.get("queryId")
        except ClientError as e:
            print(f"Error starting query: {e}")
            return None

    def get_query_results(self, query_id: str) -> Optional[Dict[str, Any]]:
        """Get results of a CloudWatch Logs Insights query.
        
        Args:
            query_id: Query ID from start_query
            
        Returns:
            Query results or None if failed
        """
        try:
            response = self.client.get_query_results(queryId=query_id)
            return {
                "status": response.get("status"),
                "results": response.get("results", []),
                "statistics": response.get("statistics", {})
            }
        except ClientError as e:
            print(f"Error getting query results: {e}")
            return None

    def stop_query(self, query_id: str) -> bool:
        """Stop a running CloudWatch Logs Insights query.
        
        Args:
            query_id: Query ID to stop
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.stop_query(queryId=query_id)
            return True
        except ClientError as e:
            print(f"Error stopping query: {e}")
            return False

    def get_error_analysis_query(self) -> str:
        """Get query for error analysis by service and error type.
        
        Returns:
            CloudWatch Logs Insights query string
        """
        return """fields @timestamp, @message, @logStream, service, error_type, error_code
| filter @message like /ERROR|CRITICAL|FATAL/
| stats count() as error_count by service, error_type
| sort error_count desc
| limit 100"""

    def get_user_activity_query(self) -> str:
        """Get query for user activity tracking.
        
        Returns:
            CloudWatch Logs Insights query string
        """
        return """fields @timestamp, user_id, action, resource, status, duration
| filter ispresent(user_id)
| stats count() as action_count, avg(duration) as avg_duration by user_id, action
| sort action_count desc
| limit 100"""

    def get_trade_execution_audit_query(self) -> str:
        """Get query for trade execution audit trail.
        
        Returns:
            CloudWatch Logs Insights query string
        """
        return """fields @timestamp, user_id, portfolio_id, trade_id, action, ticker, quantity, price, status, execution_time
| filter action like /trade|execution/
| stats count() as trade_count, avg(execution_time) as avg_execution_time by status
| sort @timestamp desc
| limit 100"""

    def run_error_analysis(
        self,
        log_group_name: str,
        start_time: int,
        end_time: int
    ) -> Optional[Dict[str, Any]]:
        """Run error analysis query.
        
        Args:
            log_group_name: Name of the log group
            start_time: Start time in seconds since epoch
            end_time: End time in seconds since epoch
            
        Returns:
            Query results or None if failed
        """
        query = self.get_error_analysis_query()
        query_id = self.start_query(log_group_name, query, start_time, end_time)
        if query_id is None:
            return None
        return self.get_query_results(query_id)

    def run_user_activity_query(
        self,
        log_group_name: str,
        start_time: int,
        end_time: int
    ) -> Optional[Dict[str, Any]]:
        """Run user activity tracking query.
        
        Args:
            log_group_name: Name of the log group
            start_time: Start time in seconds since epoch
            end_time: End time in seconds since epoch
            
        Returns:
            Query results or None if failed
        """
        query = self.get_user_activity_query()
        query_id = self.start_query(log_group_name, query, start_time, end_time)
        if query_id is None:
            return None
        return self.get_query_results(query_id)

    def run_trade_execution_audit(
        self,
        log_group_name: str,
        start_time: int,
        end_time: int
    ) -> Optional[Dict[str, Any]]:
        """Run trade execution audit trail query.
        
        Args:
            log_group_name: Name of the log group
            start_time: Start time in seconds since epoch
            end_time: End time in seconds since epoch
            
        Returns:
            Query results or None if failed
        """
        query = self.get_trade_execution_audit_query()
        query_id = self.start_query(log_group_name, query, start_time, end_time)
        if query_id is None:
            return None
        return self.get_query_results(query_id)


def create_logs_insights_client(region: str = "us-east-1") -> CloudWatchLogsInsights:
    """Factory function to create a CloudWatch Logs Insights client.
    
    Args:
        region: AWS region
        
    Returns:
        CloudWatchLogsInsights instance
    """
    return CloudWatchLogsInsights(region=region)
