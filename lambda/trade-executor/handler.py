"""Trade executor Lambda function for executing approved trades."""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import boto3

from src.models.responses import TradeConfirmation, TradeOrder
from src.models.portfolio import Transaction
from src.error_handling.error_classifier import ErrorClassifier
from src.error_handling.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from src.utils.logging import create_logger, set_trace_id

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
cloudwatch = boto3.client("cloudwatch")
sns = boto3.client("sns")

# Initialize logger
logger = create_logger("trade-executor", os.getenv("LOG_LEVEL", "INFO"))

# Environment variables
TRANSACTIONS_TABLE = os.getenv("DYNAMODB_TABLE_TRANSACTIONS", "Transactions")
PORTFOLIOS_TABLE = os.getenv("DYNAMODB_TABLE_PORTFOLIOS", "Portfolios")
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN", "")

# Circuit breaker for brokerage API calls
brokerage_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)


class BrokerageAPI:
    """Mock brokerage API for trade execution."""
    
    def __init__(self):
        """Initialize brokerage API client."""
        self.api_endpoint = os.getenv("BROKERAGE_API_ENDPOINT", "https://api.brokerage.example.com")
        self.api_key = os.getenv("BROKERAGE_API_KEY", "mock-key")
    
    def execute_trade(self, trade_order: TradeOrder) -> Dict[str, Any]:
        """
        Execute a trade order through the brokerage API.
        
        Args:
            trade_order: TradeOrder object with trade details
            
        Returns:
            Dictionary with execution details (order_id, execution_price, timestamp)
            
        Raises:
            Exception: If trade execution fails
        """
        # Mock implementation - in production, this would call actual brokerage API
        logger.info(
            f"Executing trade: {trade_order.action} {trade_order.quantity} {trade_order.ticker}",
            user_id=trade_order.user_id if hasattr(trade_order, 'user_id') else None,
            ticker=trade_order.ticker,
            quantity=trade_order.quantity,
            action=trade_order.action
        )
        
        # Simulate API call with circuit breaker
        def _execute():
            # Mock execution - return confirmation
            return {
                "order_id": str(uuid.uuid4()),
                "execution_price": trade_order.estimated_price,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "status": "executed"
            }
        
        return brokerage_circuit_breaker.call(_execute)


class TradeExecutor:
    """Executes trades and records transactions."""
    
    def __init__(self):
        """Initialize trade executor."""
        self.brokerage = BrokerageAPI()
        self.transactions_table = dynamodb.Table(TRANSACTIONS_TABLE)
        self.portfolios_table = dynamodb.Table(PORTFOLIOS_TABLE)
    
    def execute_trade(self, trade_order: TradeOrder, user_id: str, portfolio_id: str) -> TradeConfirmation:
        """
        Execute a single trade order.
        
        Args:
            trade_order: TradeOrder object with trade details
            user_id: User ID for the trade
            portfolio_id: Portfolio ID for the trade
            
        Returns:
            TradeConfirmation with execution details
            
        Raises:
            Exception: If trade execution fails
        """
        try:
            # Execute trade through brokerage API
            execution_result = self.brokerage.execute_trade(trade_order)
            
            # Record transaction in DynamoDB
            transaction = self._record_transaction(
                user_id=user_id,
                portfolio_id=portfolio_id,
                trade_order=trade_order,
                execution_result=execution_result,
                status="completed"
            )
            
            # Create and return confirmation
            confirmation = TradeConfirmation(
                order_id=execution_result["order_id"],
                trade_order=trade_order,
                execution_price=execution_result["execution_price"],
                execution_timestamp=execution_result["timestamp"],
                transaction_id=transaction.transaction_id,
                status="executed"
            )
            
            logger.info(
                f"Trade executed successfully: {trade_order.ticker}",
                user_id=user_id,
                order_id=confirmation.order_id,
                transaction_id=confirmation.transaction_id
            )
            
            return confirmation
            
        except CircuitBreakerOpenException as e:
            logger.error(
                f"Circuit breaker open for trade execution: {str(e)}",
                user_id=user_id,
                ticker=trade_order.ticker
            )
            self._handle_trade_failure(
                user_id=user_id,
                portfolio_id=portfolio_id,
                trade_order=trade_order,
                error=e,
                error_type="circuit_breaker_open"
            )
            raise
            
        except Exception as e:
            logger.error(
                f"Trade execution failed: {str(e)}",
                user_id=user_id,
                ticker=trade_order.ticker,
                error_type=e.__class__.__name__
            )
            self._handle_trade_failure(
                user_id=user_id,
                portfolio_id=portfolio_id,
                trade_order=trade_order,
                error=e,
                error_type=e.__class__.__name__
            )
            raise
    
    def _record_transaction(
        self,
        user_id: str,
        portfolio_id: str,
        trade_order: TradeOrder,
        execution_result: Dict[str, Any],
        status: str
    ) -> Transaction:
        """
        Record a transaction in DynamoDB.
        
        Args:
            user_id: User ID
            portfolio_id: Portfolio ID
            trade_order: TradeOrder object
            execution_result: Result from brokerage API
            status: Transaction status (completed, failed)
            
        Returns:
            Transaction object
        """
        timestamp = datetime.utcnow().isoformat() + "Z"
        transaction_id = str(uuid.uuid4())
        
        transaction = Transaction(
            user_id=user_id,
            timestamp=timestamp,
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            action=trade_order.action,
            ticker=trade_order.ticker,
            quantity=trade_order.quantity,
            price=execution_result["execution_price"],
            commission=0.0,  # Mock - would be from brokerage
            total_cost=(trade_order.quantity * execution_result["execution_price"]),
            execution_status=status,
            order_type=trade_order.order_type,
            initiated_by="rebalancing_agent"
        )
        
        # Write to DynamoDB
        self.transactions_table.put_item(Item=transaction.to_dynamodb())
        
        logger.info(
            f"Transaction recorded: {transaction_id}",
            user_id=user_id,
            transaction_id=transaction_id,
            ticker=trade_order.ticker
        )
        
        return transaction
    
    def _handle_trade_failure(
        self,
        user_id: str,
        portfolio_id: str,
        trade_order: TradeOrder,
        error: Exception,
        error_type: str
    ):
        """
        Handle trade failure by logging and notifying user.
        
        Args:
            user_id: User ID
            portfolio_id: Portfolio ID
            trade_order: TradeOrder object
            error: Exception that occurred
            error_type: Type of error
        """
        # Record failed transaction
        timestamp = datetime.utcnow().isoformat() + "Z"
        transaction_id = str(uuid.uuid4())
        
        failed_transaction = Transaction(
            user_id=user_id,
            timestamp=timestamp,
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            action=trade_order.action,
            ticker=trade_order.ticker,
            quantity=trade_order.quantity,
            price=trade_order.estimated_price,
            commission=0.0,
            total_cost=0.0,
            execution_status="failed",
            order_type=trade_order.order_type,
            initiated_by="rebalancing_agent"
        )
        
        self.transactions_table.put_item(Item=failed_transaction.to_dynamodb())
        
        # Log to CloudWatch
        logger.error(
            f"Trade failed: {trade_order.ticker}",
            user_id=user_id,
            transaction_id=transaction_id,
            error_type=error_type,
            error_message=str(error),
            ticker=trade_order.ticker,
            quantity=trade_order.quantity,
            action=trade_order.action
        )
        
        # Send SNS notification
        self._notify_user_of_failure(
            user_id=user_id,
            trade_order=trade_order,
            error=error,
            transaction_id=transaction_id
        )
    
    def _notify_user_of_failure(
        self,
        user_id: str,
        trade_order: TradeOrder,
        error: Exception,
        transaction_id: str
    ):
        """
        Send SNS notification to user about trade failure.
        
        Args:
            user_id: User ID
            trade_order: TradeOrder object
            error: Exception that occurred
            transaction_id: Transaction ID
        """
        if not SNS_TOPIC_ARN:
            logger.warn("SNS_TOPIC_ARN not configured, skipping notification")
            return
        
        message = {
            "user_id": user_id,
            "transaction_id": transaction_id,
            "ticker": trade_order.ticker,
            "action": trade_order.action,
            "quantity": trade_order.quantity,
            "error_reason": str(error),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject=f"Trade Execution Failed: {trade_order.ticker}",
                Message=json.dumps(message, indent=2)
            )
            logger.info(
                f"User notified of trade failure",
                user_id=user_id,
                transaction_id=transaction_id
            )
        except Exception as e:
            logger.error(
                f"Failed to send SNS notification: {str(e)}",
                user_id=user_id,
                transaction_id=transaction_id
            )


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for trade execution.
    
    Args:
        event: Lambda event containing trade order details
        context: Lambda context
        
    Returns:
        Dictionary with execution result
    """
    try:
        # Set trace ID for logging
        trace_id = context.request_id if hasattr(context, 'request_id') else str(uuid.uuid4())
        set_trace_id(trace_id)
        
        logger.info("Trade execution started", trace_id=trace_id)
        
        # Parse input
        user_id = event.get("user_id")
        portfolio_id = event.get("portfolio_id")
        trade_order_data = event.get("trade_order")
        
        if not all([user_id, portfolio_id, trade_order_data]):
            raise ValueError("Missing required fields: user_id, portfolio_id, trade_order")
        
        # Create TradeOrder object
        trade_order = TradeOrder(
            order_id=trade_order_data.get("order_id", str(uuid.uuid4())),
            action=trade_order_data["action"],
            ticker=trade_order_data["ticker"],
            quantity=trade_order_data["quantity"],
            order_type=trade_order_data.get("order_type", "market"),
            estimated_price=trade_order_data.get("estimated_price", 0.0),
            estimated_cost=trade_order_data.get("estimated_cost", 0.0)
        )
        
        # Execute trade
        executor = TradeExecutor()
        confirmation = executor.execute_trade(trade_order, user_id, portfolio_id)
        
        return {
            "statusCode": 200,
            "body": {
                "order_id": confirmation.order_id,
                "transaction_id": confirmation.transaction_id,
                "status": confirmation.status,
                "execution_price": confirmation.execution_price,
                "execution_timestamp": confirmation.execution_timestamp
            }
        }
        
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        return {
            "statusCode": 400,
            "body": {
                "error": "Validation error",
                "message": str(e)
            }
        }
    except CircuitBreakerOpenException as e:
        logger.error(f"Circuit breaker open: {str(e)}")
        return {
            "statusCode": 503,
            "body": {
                "error": "Service unavailable",
                "message": "Brokerage API temporarily unavailable"
            }
        }
    except Exception as e:
        logger.error(f"Trade execution error: {str(e)}", error_type=e.__class__.__name__)
        return {
            "statusCode": 500,
            "body": {
                "error": "Trade execution failed",
                "message": str(e)
            }
        }
