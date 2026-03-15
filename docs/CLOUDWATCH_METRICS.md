# CloudWatch Custom Metrics Implementation

## Overview

The CloudWatch metrics utility provides a comprehensive solution for emitting custom performance metrics to AWS CloudWatch. It supports tracking:

- **AgentResponseTime**: Response time for each agent invocation (milliseconds)
- **WorkflowDuration**: Duration of Step Functions workflow executions (seconds)
- **TradeExecutionSuccess**: Success/failure outcomes for trade executions (count)
- **DynamoDBQueryLatency**: Latency of database operations (milliseconds)
- **RequestCount**: Volume of requests processed per agent type (count)

## Architecture

### Components

1. **CloudWatchMetrics**: Main utility class for emitting metrics
2. **MetricUnit**: Enum for metric units (Milliseconds, Seconds, Count, Percent)
3. **MetricsTimer**: Context manager for automatic timing and metric emission
4. **create_metrics_client()**: Factory function for creating metrics clients

### Metric Dimensions

Each metric includes relevant dimensions for filtering and aggregation:

- **AgentResponseTime**: AgentType (portfolio_analyzer, tax_optimizer, rebalancing_agent)
- **WorkflowDuration**: WorkflowType (rebalancing, tax_optimization, analysis)
- **TradeExecutionSuccess**: OrderType (market, limit), Status (success, failure)
- **DynamoDBQueryLatency**: TableName (Portfolios, Transactions, AgentSessions), Operation (query, scan, get_item)
- **RequestCount**: AgentType

## Usage Examples

### Basic Metric Emission

```python
from src.utils.cloudwatch_metrics import create_metrics_client, MetricUnit

# Create metrics client
metrics = create_metrics_client()

# Emit agent response time
metrics.emit_agent_response_time(
    agent_type="portfolio_analyzer",
    response_time_ms=250.5,
    user_id="user_123"
)

# Emit workflow duration
metrics.emit_workflow_duration(
    workflow_type="rebalancing",
    duration_seconds=45.5,
    user_id="user_123"
)

# Emit trade execution result
metrics.emit_trade_execution_success(
    order_type="market",
    success=True,
    user_id="user_123"
)

# Emit DynamoDB query latency
metrics.emit_dynamodb_query_latency(
    table_name="Portfolios",
    latency_ms=85.5,
    operation="query",
    user_id="user_123"
)
```

### Using MetricsTimer Context Manager

```python
from src.utils.cloudwatch_metrics import create_metrics_client, MetricsTimer, MetricUnit
import time

metrics = create_metrics_client()

# Automatically time and emit metric
with MetricsTimer(
    metrics,
    "AgentResponseTime",
    dimensions={"AgentType": "portfolio_analyzer"},
    unit=MetricUnit.MILLISECONDS
):
    # Your agent code here
    time.sleep(0.25)
    # Metric is automatically emitted on exit
```

### Batch Metric Emission

```python
from src.utils.cloudwatch_metrics import create_metrics_client, MetricUnit

metrics = create_metrics_client()

# Emit multiple metrics in a batch
batch_metrics = [
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

count = metrics.emit_batch_metrics(batch_metrics)
print(f"Emitted {count} metrics")
```

## Integration with Lambda Functions

### Portfolio Analyzer Integration

```python
import json
import time
from src.utils.cloudwatch_metrics import create_metrics_client, MetricsTimer, MetricUnit
from src.utils.logging import create_logger

logger = create_logger("portfolio-analyzer")
metrics = create_metrics_client()

def lambda_handler(event, context):
    """Lambda handler for Portfolio Analyzer Agent."""
    user_id = event.get("user_id")
    
    # Use timer to automatically emit response time metric
    with MetricsTimer(
        metrics,
        "AgentResponseTime",
        dimensions={"AgentType": "portfolio_analyzer"},
        unit=MetricUnit.MILLISECONDS
    ):
        try:
            # Your analysis logic here
            portfolio_id = event.get("portfolio_id")
            
            # Emit request count
            metrics.emit_request_count("portfolio_analyzer", user_id=user_id)
            
            # Perform analysis
            report = analyze_portfolio(user_id, portfolio_id)
            
            return {
                "statusCode": 200,
                "body": json.dumps({"status": "success", "report": report})
            }
        except Exception as e:
            logger.error(f"Error: {str(e)}", user_id=user_id)
            return {
                "statusCode": 500,
                "body": json.dumps({"status": "error", "message": str(e)})
            }
```

### Trade Executor Integration

```python
import json
from src.utils.cloudwatch_metrics import create_metrics_client
from src.utils.logging import create_logger

logger = create_logger("trade-executor")
metrics = create_metrics_client()

def lambda_handler(event, context):
    """Lambda handler for Trade Executor."""
    user_id = event.get("user_id")
    trade_order = event.get("trade_order")
    
    try:
        # Execute trade
        result = execute_trade(trade_order)
        
        # Emit trade execution metric
        metrics.emit_trade_execution_success(
            order_type=trade_order.get("order_type", "market"),
            success=result.get("success", False),
            user_id=user_id
        )
        
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "success", "result": result})
        }
    except Exception as e:
        # Emit failure metric
        metrics.emit_trade_execution_success(
            order_type=trade_order.get("order_type", "market"),
            success=False,
            user_id=user_id
        )
        
        logger.error(f"Trade execution failed: {str(e)}", user_id=user_id)
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "error", "message": str(e)})
        }
```

### DynamoDB Query Integration

```python
import time
import boto3
from src.utils.cloudwatch_metrics import create_metrics_client
from src.utils.logging import create_logger

logger = create_logger("portfolio-service")
metrics = create_metrics_client()
dynamodb = boto3.resource("dynamodb")

def get_portfolio(user_id, portfolio_id):
    """Get portfolio from DynamoDB with latency tracking."""
    table = dynamodb.Table("Portfolios")
    
    start_time = time.time()
    
    try:
        response = table.get_item(
            Key={"user_id": user_id, "portfolio_id": portfolio_id}
        )
        
        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000
        
        # Emit latency metric
        metrics.emit_dynamodb_query_latency(
            table_name="Portfolios",
            latency_ms=latency_ms,
            operation="get_item",
            user_id=user_id
        )
        
        return response.get("Item")
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        metrics.emit_dynamodb_query_latency(
            table_name="Portfolios",
            latency_ms=latency_ms,
            operation="get_item",
            user_id=user_id
        )
        logger.error(f"DynamoDB error: {str(e)}", user_id=user_id)
        raise
```

## CloudWatch Alarms

The metrics support the following CloudWatch alarms:

### HighAgentResponseTime
- **Metric**: AgentResponseTime
- **Threshold**: 5000 milliseconds (5 seconds)
- **Evaluation Periods**: 2
- **Action**: Alert administrators

### HighDynamoDBLatency
- **Metric**: DynamoDBQueryLatency
- **Threshold**: 200 milliseconds
- **Evaluation Periods**: 3
- **Action**: Alert administrators

### TradeExecutionFailures
- **Metric**: TradeExecutionSuccess
- **Threshold**: < 5 successful trades
- **Evaluation Periods**: 1
- **Action**: Alert administrators

## CloudWatch Dashboard

The metrics are displayed in a CloudWatch dashboard with:

- **Agent Performance Widget**: AgentResponseTime (p99), RequestCount
- **Workflow Performance Widget**: WorkflowDuration (average, p95, p99)
- **Trade Execution Widget**: TradeExecutionSuccess (success rate)
- **Database Performance Widget**: DynamoDBQueryLatency (average, p95, p99)

## Performance Warnings

The utility automatically logs performance warnings when:

- Agent response time exceeds 5 seconds
- Workflow duration exceeds 15 minutes (900 seconds)
- DynamoDB query latency exceeds 200 milliseconds

These warnings are logged to CloudWatch Logs with structured format for easy analysis.

## Error Handling

The metrics utility includes comprehensive error handling:

- **Validation**: Validates metric names, values, and dimensions
- **API Errors**: Catches and logs CloudWatch API errors
- **Batch Processing**: Handles errors in batch metric emission
- **Graceful Degradation**: Returns False on error but doesn't raise exceptions

## Testing

### Unit Tests

Run unit tests for the metrics utility:

```bash
pytest tests/unit/test_cloudwatch_metrics.py -v
```

### Integration Tests

Run integration tests:

```bash
pytest tests/integration/test_cloudwatch_metrics_integration.py -v
```

## Best Practices

1. **Use MetricsTimer for automatic timing**: Reduces boilerplate code
2. **Include user_id for tracking**: Helps with user-specific analysis
3. **Batch metrics when possible**: More efficient than individual emissions
4. **Monitor performance warnings**: Set up alerts for slow operations
5. **Use consistent dimension values**: Enables better aggregation in CloudWatch

## Troubleshooting

### Metrics not appearing in CloudWatch

1. Verify IAM permissions for `cloudwatch:PutMetricData`
2. Check CloudWatch Logs for error messages
3. Verify metric names and dimensions are correct
4. Ensure Lambda function has network access to CloudWatch

### High latency metrics

1. Check DynamoDB provisioned capacity
2. Review Lambda memory allocation
3. Analyze CloudWatch Logs for errors
4. Consider enabling DynamoDB auto-scaling

### Missing dimensions

1. Verify dimension names match expected values
2. Check that dimensions are passed correctly to emit functions
3. Review CloudWatch dashboard configuration
