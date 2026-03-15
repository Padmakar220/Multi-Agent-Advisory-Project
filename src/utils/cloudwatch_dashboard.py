"""CloudWatch Dashboard management for monitoring system performance."""

import json
from typing import Any, Dict, List, Optional
import boto3
from botocore.exceptions import ClientError


class CloudWatchDashboard:
    """Manages CloudWatch dashboards for system monitoring."""

    def __init__(self, region: str = "us-east-1"):
        """Initialize CloudWatch Dashboard client.
        
        Args:
            region: AWS region for CloudWatch
        """
        self.region = region
        self.client = boto3.client("cloudwatch", region_name=region)
        self.namespace = "MultiAgentAdvisorySystem"

    def create_dashboard(self, dashboard_name: str, dashboard_body: Dict[str, Any]) -> bool:
        """Create or update a CloudWatch dashboard.
        
        Args:
            dashboard_name: Name of the dashboard
            dashboard_body: Dashboard body with widgets
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.put_dashboard(
                DashboardName=dashboard_name,
                DashboardBody=json.dumps(dashboard_body)
            )
            return True
        except ClientError as e:
            print(f"Error creating dashboard: {e}")
            return False

    def delete_dashboard(self, dashboard_name: str) -> bool:
        """Delete a CloudWatch dashboard.
        
        Args:
            dashboard_name: Name of the dashboard to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.delete_dashboards(DashboardNames=[dashboard_name])
            return True
        except ClientError as e:
            print(f"Error deleting dashboard: {e}")
            return False

    def get_dashboard(self, dashboard_name: str) -> Optional[Dict[str, Any]]:
        """Get dashboard details.
        
        Args:
            dashboard_name: Name of the dashboard
            
        Returns:
            Dashboard body or None if not found
        """
        try:
            response = self.client.get_dashboard(DashboardName=dashboard_name)
            return json.loads(response.get("DashboardBody", "{}"))
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidParameterInput":
                return None
            print(f"Error getting dashboard: {e}")
            return None

    def list_dashboards(self) -> List[str]:
        """List all CloudWatch dashboards.
        
        Returns:
            List of dashboard names
        """
        try:
            response = self.client.list_dashboards()
            return [d["DashboardName"] for d in response.get("DashboardEntries", [])]
        except ClientError as e:
            print(f"Error listing dashboards: {e}")
            return []

    def create_monitoring_dashboard(self) -> bool:
        """Create the main monitoring dashboard with all key metrics.
        
        Returns:
            True if successful, False otherwise
        """
        dashboard_body = {
            "widgets": [
                self._create_lambda_performance_widget(),
                self._create_agent_performance_widget(),
                self._create_error_logs_widget(),
                self._create_dynamodb_metrics_widget(),
            ]
        }
        return self.create_dashboard("MultiAgentAdvisoryMonitoring", dashboard_body)

    def _create_lambda_performance_widget(self) -> Dict[str, Any]:
        """Create Lambda performance metrics widget.
        
        Returns:
            Widget configuration
        """
        return {
            "type": "metric",
            "properties": {
                "metrics": [
                    ["AWS/Lambda", "Duration", {"stat": "Average"}],
                    [".", ".", {"stat": "Maximum"}],
                    [".", "Errors", {"stat": "Sum"}],
                    [".", "Invocations", {"stat": "Sum"}],
                    [".", "Throttles", {"stat": "Sum"}],
                    [".", "ConcurrentExecutions", {"stat": "Maximum"}],
                ],
                "period": 60,
                "stat": "Average",
                "region": self.region,
                "title": "Lambda Performance Metrics",
                "yAxis": {
                    "left": {
                        "min": 0
                    }
                }
            }
        }

    def _create_agent_performance_widget(self) -> Dict[str, Any]:
        """Create agent performance metrics widget.
        
        Returns:
            Widget configuration
        """
        return {
            "type": "metric",
            "properties": {
                "metrics": [
                    [self.namespace, "AgentResponseTime", {"stat": "p99"}],
                    ["...", {"stat": "p95"}],
                    ["...", {"stat": "Average"}],
                    [self.namespace, "WorkflowDuration", {"stat": "Average"}],
                    ["...", {"stat": "Maximum"}],
                    [self.namespace, "TradeExecutionSuccess", {"stat": "Sum"}],
                ],
                "period": 60,
                "stat": "Average",
                "region": self.region,
                "title": "Agent Performance Metrics",
                "yAxis": {
                    "left": {
                        "min": 0
                    }
                }
            }
        }

    def _create_error_logs_widget(self) -> Dict[str, Any]:
        """Create error logs insights widget.
        
        Returns:
            Widget configuration
        """
        return {
            "type": "log",
            "properties": {
                "query": """fields @timestamp, @message, @logStream, error_type, service
| filter @message like /ERROR|CRITICAL/
| stats count() as error_count by service, error_type
| sort error_count desc
| limit 20""",
                "region": self.region,
                "title": "Recent Errors by Service and Type",
                "queryId": "error-analysis"
            }
        }

    def _create_dynamodb_metrics_widget(self) -> Dict[str, Any]:
        """Create DynamoDB metrics widget.
        
        Returns:
            Widget configuration
        """
        return {
            "type": "metric",
            "properties": {
                "metrics": [
                    ["AWS/DynamoDB", "ConsumedReadCapacityUnits", {"stat": "Sum"}],
                    [".", "ConsumedWriteCapacityUnits", {"stat": "Sum"}],
                    [".", "UserErrors", {"stat": "Sum"}],
                    [".", "SystemErrors", {"stat": "Sum"}],
                    [".", "SuccessfulRequestLatency", {"stat": "Average"}],
                    [".", "SuccessfulRequestLatency", {"stat": "p99"}],
                ],
                "period": 60,
                "stat": "Average",
                "region": self.region,
                "title": "DynamoDB Metrics",
                "yAxis": {
                    "left": {
                        "min": 0
                    }
                }
            }
        }

    def add_widget(self, dashboard_name: str, widget: Dict[str, Any]) -> bool:
        """Add a widget to an existing dashboard.
        
        Args:
            dashboard_name: Name of the dashboard
            widget: Widget configuration
            
        Returns:
            True if successful, False otherwise
        """
        dashboard = self.get_dashboard(dashboard_name)
        if dashboard is None:
            return False
        
        if "widgets" not in dashboard:
            dashboard["widgets"] = []
        
        dashboard["widgets"].append(widget)
        return self.create_dashboard(dashboard_name, dashboard)

    def remove_widget(self, dashboard_name: str, widget_index: int) -> bool:
        """Remove a widget from a dashboard.
        
        Args:
            dashboard_name: Name of the dashboard
            widget_index: Index of the widget to remove
            
        Returns:
            True if successful, False otherwise
        """
        dashboard = self.get_dashboard(dashboard_name)
        if dashboard is None or "widgets" not in dashboard:
            return False
        
        if 0 <= widget_index < len(dashboard["widgets"]):
            dashboard["widgets"].pop(widget_index)
            return self.create_dashboard(dashboard_name, dashboard)
        
        return False


def create_dashboard_manager(region: str = "us-east-1") -> CloudWatchDashboard:
    """Factory function to create a CloudWatch Dashboard manager.
    
    Args:
        region: AWS region
        
    Returns:
        CloudWatchDashboard instance
    """
    return CloudWatchDashboard(region=region)
