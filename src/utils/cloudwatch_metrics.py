"""CloudWatch custom metrics utility for performance monitoring."""

import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum
import boto3
from botocore.exceptions import ClientError

from src.utils.logging import create_logger

logger = create_logger("cloudwatch-metrics")


class MetricUnit(Enum):
    """CloudWatch metric units."""
    MILLISECONDS = "Milliseconds"
    SECONDS = "Seconds"
    COUNT = "Count"
    PERCENT = "Percent"


class CloudWatchMetrics:
    """
    Utility for emitting custom metrics to CloudWatch.
    
    Provides methods to emit performance metrics for:
    - Agent response times
    - Workflow durations
    - Trade execution outcomes
    - Database query latencies
    """
    
    def __init__(self, namespace: str = "MultiAgentAdvisorySystem"):
        """
        Initialize CloudWatch metrics client.
        
        Args:
            namespace: CloudWatch namespace for metrics (default: MultiAgentAdvisorySystem)
        """
        self.namespace = namespace
        self.cloudwatch = boto3.client("cloudwatch")
    
    def emit_metric(
        self,
        metric_name: str,
        value: float,
        unit: MetricUnit,
        dimensions: Optional[Dict[str, str]] = None,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Emit a single metric to CloudWatch.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: Unit of measurement (MetricUnit enum)
            dimensions: Optional dictionary of dimension name-value pairs
            timestamp: Optional timestamp (defaults to now)
            
        Returns:
            True if metric was successfully emitted, False otherwise
        """
        try:
            # Validate inputs
            if not metric_name or not isinstance(metric_name, str):
                logger.error("Invalid metric_name: must be non-empty string")
                return False
            
            if not isinstance(value, (int, float)):
                logger.error(f"Invalid metric value: {value} is not numeric")
                return False
            
            if value < 0:
                logger.warn(f"Negative metric value: {value}")
            
            # Build metric data
            metric_data = {
                "MetricName": metric_name,
                "Value": float(value),
                "Unit": unit.value,
                "Timestamp": timestamp or datetime.utcnow()
            }
            
            # Add dimensions if provided
            if dimensions:
                metric_data["Dimensions"] = [
                    {"Name": k, "Value": str(v)}
                    for k, v in dimensions.items()
                ]
            
            # Emit metric
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=[metric_data]
            )
            
            logger.debug(
                f"Emitted metric: {metric_name}",
                metric_name=metric_name,
                value=value,
                unit=unit.value,
                dimensions=dimensions
            )
            
            return True
            
        except ClientError as e:
            logger.error(
                f"CloudWatch API error: {str(e)}",
                error_code=e.response.get("Error", {}).get("Code"),
                metric_name=metric_name
            )
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error emitting metric: {str(e)}",
                metric_name=metric_name
            )
            return False
    
    def emit_batch_metrics(
        self,
        metrics: List[Dict[str, Any]]
    ) -> int:
        """
        Emit multiple metrics to CloudWatch in a batch.
        
        Args:
            metrics: List of metric dictionaries with keys:
                - metric_name (str): Name of the metric
                - value (float): Metric value
                - unit (MetricUnit): Unit of measurement
                - dimensions (dict, optional): Dimension name-value pairs
                - timestamp (datetime, optional): Metric timestamp
                
        Returns:
            Number of metrics successfully emitted
        """
        if not metrics:
            logger.warn("No metrics provided for batch emission")
            return 0
        
        # CloudWatch API allows max 20 metrics per request
        batch_size = 20
        successful_count = 0
        
        for i in range(0, len(metrics), batch_size):
            batch = metrics[i:i + batch_size]
            
            try:
                metric_data = []
                
                for metric in batch:
                    # Validate required fields
                    if not all(k in metric for k in ["metric_name", "value", "unit"]):
                        logger.warn(f"Skipping invalid metric: missing required fields")
                        continue
                    
                    metric_entry = {
                        "MetricName": metric["metric_name"],
                        "Value": float(metric["value"]),
                        "Unit": metric["unit"].value if isinstance(metric["unit"], MetricUnit) else metric["unit"],
                        "Timestamp": metric.get("timestamp", datetime.utcnow())
                    }
                    
                    # Add dimensions if provided
                    if "dimensions" in metric and metric["dimensions"]:
                        metric_entry["Dimensions"] = [
                            {"Name": k, "Value": str(v)}
                            for k, v in metric["dimensions"].items()
                        ]
                    
                    metric_data.append(metric_entry)
                
                if metric_data:
                    self.cloudwatch.put_metric_data(
                        Namespace=self.namespace,
                        MetricData=metric_data
                    )
                    successful_count += len(metric_data)
                    
                    logger.debug(
                        f"Emitted batch of {len(metric_data)} metrics"
                    )
                    
            except ClientError as e:
                logger.error(
                    f"CloudWatch API error in batch: {str(e)}",
                    error_code=e.response.get("Error", {}).get("Code"),
                    batch_size=len(batch)
                )
            except Exception as e:
                logger.error(
                    f"Unexpected error in batch emission: {str(e)}",
                    batch_size=len(batch)
                )
        
        return successful_count
    
    def emit_agent_response_time(
        self,
        agent_type: str,
        response_time_ms: float,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Emit AgentResponseTime metric for agent invocation.
        
        Args:
            agent_type: Type of agent (e.g., "portfolio_analyzer", "tax_optimizer")
            response_time_ms: Response time in milliseconds
            user_id: Optional user ID for tracking
            
        Returns:
            True if metric was successfully emitted
        """
        if response_time_ms < 0:
            logger.warn(f"Invalid response time: {response_time_ms}ms")
            return False
        
        dimensions = {"AgentType": agent_type}
        
        success = self.emit_metric(
            metric_name="AgentResponseTime",
            value=response_time_ms,
            unit=MetricUnit.MILLISECONDS,
            dimensions=dimensions
        )
        
        if success and response_time_ms > 5000:
            logger.warn(
                f"Slow agent response detected: {agent_type} took {response_time_ms}ms",
                agent_type=agent_type,
                response_time_ms=response_time_ms,
                user_id=user_id
            )
        
        return success
    
    def emit_workflow_duration(
        self,
        workflow_type: str,
        duration_seconds: float,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Emit WorkflowDuration metric for Step Functions execution.
        
        Args:
            workflow_type: Type of workflow (e.g., "rebalancing", "tax_optimization")
            duration_seconds: Workflow duration in seconds
            user_id: Optional user ID for tracking
            
        Returns:
            True if metric was successfully emitted
        """
        if duration_seconds < 0:
            logger.warn(f"Invalid workflow duration: {duration_seconds}s")
            return False
        
        dimensions = {"WorkflowType": workflow_type}
        
        success = self.emit_metric(
            metric_name="WorkflowDuration",
            value=duration_seconds,
            unit=MetricUnit.SECONDS,
            dimensions=dimensions
        )
        
        if success and duration_seconds > 900:  # 15 minutes
            logger.warn(
                f"Long-running workflow detected: {workflow_type} took {duration_seconds}s",
                workflow_type=workflow_type,
                duration_seconds=duration_seconds,
                user_id=user_id
            )
        
        return success
    
    def emit_trade_execution_success(
        self,
        order_type: str,
        success: bool,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Emit TradeExecutionSuccess metric for trade outcomes.
        
        Args:
            order_type: Type of order (e.g., "market", "limit")
            success: Whether the trade was successful
            user_id: Optional user ID for tracking
            
        Returns:
            True if metric was successfully emitted
        """
        dimensions = {
            "OrderType": order_type,
            "Status": "success" if success else "failure"
        }
        
        return self.emit_metric(
            metric_name="TradeExecutionSuccess",
            value=1.0 if success else 0.0,
            unit=MetricUnit.COUNT,
            dimensions=dimensions
        )
    
    def emit_dynamodb_query_latency(
        self,
        table_name: str,
        latency_ms: float,
        operation: str = "query",
        user_id: Optional[str] = None
    ) -> bool:
        """
        Emit DynamoDBQueryLatency metric for database operations.
        
        Args:
            table_name: Name of DynamoDB table
            latency_ms: Query latency in milliseconds
            operation: Type of operation (e.g., "query", "scan", "get_item")
            user_id: Optional user ID for tracking
            
        Returns:
            True if metric was successfully emitted
        """
        if latency_ms < 0:
            logger.warn(f"Invalid query latency: {latency_ms}ms")
            return False
        
        dimensions = {
            "TableName": table_name,
            "Operation": operation
        }
        
        success = self.emit_metric(
            metric_name="DynamoDBQueryLatency",
            value=latency_ms,
            unit=MetricUnit.MILLISECONDS,
            dimensions=dimensions
        )
        
        if success and latency_ms > 200:
            logger.warn(
                f"High DynamoDB latency detected: {table_name}.{operation} took {latency_ms}ms",
                table_name=table_name,
                operation=operation,
                latency_ms=latency_ms,
                user_id=user_id
            )
        
        return success
    
    def emit_request_count(
        self,
        agent_type: str,
        count: int = 1,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Emit request count metric for tracking request volume.
        
        Args:
            agent_type: Type of agent
            count: Number of requests (default: 1)
            user_id: Optional user ID for tracking
            
        Returns:
            True if metric was successfully emitted
        """
        if count < 0:
            logger.warn(f"Invalid request count: {count}")
            return False
        
        dimensions = {"AgentType": agent_type}
        
        return self.emit_metric(
            metric_name="RequestCount",
            value=float(count),
            unit=MetricUnit.COUNT,
            dimensions=dimensions
        )


class MetricsTimer:
    """Context manager for timing operations and emitting metrics."""
    
    def __init__(
        self,
        metrics_client: CloudWatchMetrics,
        metric_name: str,
        dimensions: Optional[Dict[str, str]] = None,
        unit: MetricUnit = MetricUnit.MILLISECONDS
    ):
        """
        Initialize metrics timer.
        
        Args:
            metrics_client: CloudWatchMetrics instance
            metric_name: Name of the metric to emit
            dimensions: Optional dimensions for the metric
            unit: Unit of measurement (default: Milliseconds)
        """
        self.metrics_client = metrics_client
        self.metric_name = metric_name
        self.dimensions = dimensions or {}
        self.unit = unit
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        """Start timing."""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timing and emit metric."""
        self.end_time = time.time()
        
        # Calculate duration
        if self.unit == MetricUnit.MILLISECONDS:
            duration = (self.end_time - self.start_time) * 1000
        elif self.unit == MetricUnit.SECONDS:
            duration = self.end_time - self.start_time
        else:
            duration = self.end_time - self.start_time
        
        # Emit metric
        self.metrics_client.emit_metric(
            metric_name=self.metric_name,
            value=duration,
            unit=self.unit,
            dimensions=self.dimensions
        )
    
    def get_duration(self) -> Optional[float]:
        """
        Get duration in the specified unit.
        
        Returns:
            Duration value or None if timer hasn't completed
        """
        if self.start_time is None or self.end_time is None:
            return None
        
        if self.unit == MetricUnit.MILLISECONDS:
            return (self.end_time - self.start_time) * 1000
        elif self.unit == MetricUnit.SECONDS:
            return self.end_time - self.start_time
        else:
            return self.end_time - self.start_time


def create_metrics_client(namespace: str = "MultiAgentAdvisorySystem") -> CloudWatchMetrics:
    """
    Create a CloudWatch metrics client.
    
    Args:
        namespace: CloudWatch namespace for metrics
        
    Returns:
        CloudWatchMetrics instance
    """
    return CloudWatchMetrics(namespace)
