"""ExecuteTradeTool for brokerage API integration via Lambda."""

import boto3
import json
from typing import Dict
from botocore.exceptions import ClientError

from src.models.responses import TradeOrder, TradeConfirmation
from src.error_handling import CircuitBreaker, CircuitBreakerOpenException


class ExecuteTradeTool:
    """
    MCP Tool for executing trades through brokerage API integration.
    
    This tool invokes the trade-executor Lambda function with circuit breaker
    protection for brokerage API failures.
    """
    
    name: str = "execute_trade"
    description: str = "Execute a trade order through brokerage API with circuit breaker"
    
    def __init__(
        self,
        lambda_function_name: str = "trade-executor",
        region_name: str = "us-east-1",
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: int = 60
    ):
        """
        Initialize the ExecuteTradeTool.
        
        Args:
            lambda_function_name: Name of the trade executor Lambda function
            region_name: AWS region name
            circuit_breaker_threshold: Number of failures before opening circuit
            circuit_breaker_timeout: Seconds to wait before attempting recovery
        """
        self.lambda_function_name = lambda_function_name
        self.region_name = region_name
        self.lambda_client = boto3.client('lambda', region_name=region_name)
        
        # Initialize circuit breaker for brokerage API failures
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_threshold,
            timeout=circuit_breaker_timeout
        )
    
    def _invoke_lambda(self, trade_order: TradeOrder) -> Dict:
        """
        Invoke the trade executor Lambda function.
        
        Args:
            trade_order: TradeOrder object to execute
            
        Returns:
            Lambda response payload
            
        Raises:
            RuntimeError: If Lambda invocation fails
        """
        # Prepare payload
        payload = {
            'order_id': trade_order.order_id,
            'action': trade_order.action,
            'ticker': trade_order.ticker,
            'quantity': trade_order.quantity,
            'order_type': trade_order.order_type,
            'estimated_price': trade_order.estimated_price
        }
        
        try:
            # Invoke Lambda function
            response = self.lambda_client.invoke(
                FunctionName=self.lambda_function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            # Parse response
            response_payload = json.loads(response['Payload'].read())
            
            # Check for Lambda function errors
            if 'errorMessage' in response_payload:
                raise RuntimeError(f"Lambda execution error: {response_payload['errorMessage']}")
            
            return response_payload
            
        except ClientError as e:
            error_message = e.response['Error']['Message']
            raise RuntimeError(f"Failed to invoke Lambda: {error_message}")
    
    def execute(self, trade_order: TradeOrder) -> TradeConfirmation:
        """
        Execute a trade order through brokerage API with circuit breaker protection.
        
        Args:
            trade_order: TradeOrder object with all required fields
            
        Returns:
            TradeConfirmation with execution details
            
        Raises:
            ValueError: If trade_order is invalid
            CircuitBreakerOpenException: If circuit breaker is open
            RuntimeError: If trade execution fails
        """
        # Validate trade order
        if not isinstance(trade_order, TradeOrder):
            raise ValueError("trade_order must be a TradeOrder object")
        
        # Validate required fields
        if not trade_order.order_id:
            raise ValueError("order_id is required")
        if not trade_order.ticker:
            raise ValueError("ticker is required")
        if trade_order.quantity <= 0:
            raise ValueError(f"quantity must be positive, got {trade_order.quantity}")
        if trade_order.action not in ["buy", "sell"]:
            raise ValueError(f"action must be 'buy' or 'sell', got {trade_order.action}")
        
        try:
            # Execute with circuit breaker protection
            response_payload = self.circuit_breaker.call(
                self._invoke_lambda,
                trade_order
            )
            
            # Parse trade confirmation from response
            trade_confirmation = TradeConfirmation(
                order_id=response_payload['order_id'],
                transaction_id=response_payload['transaction_id'],
                ticker=response_payload['ticker'],
                action=response_payload['action'],
                quantity=response_payload['quantity'],
                execution_price=response_payload['execution_price'],
                execution_time=response_payload['execution_time'],
                status=response_payload['status'],
                commission=response_payload.get('commission', 0.0),
                error_message=response_payload.get('error_message')
            )
            
            return trade_confirmation
            
        except CircuitBreakerOpenException as e:
            # Circuit breaker is open - brokerage API is failing
            raise CircuitBreakerOpenException(
                f"Trade execution unavailable due to brokerage API failures: {str(e)}"
            )
        
        except ValueError:
            # Re-raise validation errors
            raise
        
        except Exception as e:
            # All other errors
            raise RuntimeError(f"Failed to execute trade: {str(e)}")
    
    def get_circuit_breaker_state(self) -> str:
        """
        Get the current state of the circuit breaker.
        
        Returns:
            Circuit breaker state as string ('CLOSED', 'OPEN', 'HALF_OPEN')
        """
        return self.circuit_breaker.get_state().value
    
    def reset_circuit_breaker(self):
        """Manually reset the circuit breaker to closed state."""
        self.circuit_breaker.reset()
