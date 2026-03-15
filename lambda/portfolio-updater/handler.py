"""Portfolio updater Lambda function for updating portfolio holdings after trades."""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List
import boto3

from src.models.portfolio import Portfolio, Holding
from src.utils.logging import create_logger, set_trace_id

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")

# Initialize logger
logger = create_logger("portfolio-updater", os.getenv("LOG_LEVEL", "INFO"))

# Environment variables
PORTFOLIOS_TABLE = os.getenv("DYNAMODB_TABLE_PORTFOLIOS", "Portfolios")
TRANSACTIONS_TABLE = os.getenv("DYNAMODB_TABLE_TRANSACTIONS", "Transactions")


class PortfolioUpdater:
    """Updates portfolio holdings after successful trades."""
    
    def __init__(self):
        """Initialize portfolio updater."""
        self.portfolios_table = dynamodb.Table(PORTFOLIOS_TABLE)
        self.transactions_table = dynamodb.Table(TRANSACTIONS_TABLE)
    
    def update_portfolio(
        self,
        user_id: str,
        portfolio_id: str,
        transactions: List[Dict[str, Any]]
    ) -> Portfolio:
        """
        Update portfolio holdings based on completed transactions.
        
        Args:
            user_id: User ID
            portfolio_id: Portfolio ID
            transactions: List of completed transaction details
            
        Returns:
            Updated Portfolio object
            
        Raises:
            Exception: If portfolio update fails
        """
        try:
            # Retrieve current portfolio
            portfolio = self._get_portfolio(user_id, portfolio_id)
            
            logger.info(
                f"Updating portfolio with {len(transactions)} transactions",
                user_id=user_id,
                portfolio_id=portfolio_id,
                transaction_count=len(transactions)
            )
            
            # Apply each transaction to portfolio
            for transaction in transactions:
                portfolio = self._apply_transaction(portfolio, transaction)
            
            # Recalculate portfolio value
            portfolio.total_value = sum(h.market_value for h in portfolio.holdings)
            portfolio.updated_at = datetime.utcnow().isoformat() + "Z"
            
            # Save updated portfolio
            self.portfolios_table.put_item(Item=portfolio.to_dynamodb())
            
            logger.info(
                f"Portfolio updated successfully",
                user_id=user_id,
                portfolio_id=portfolio_id,
                new_total_value=portfolio.total_value,
                holding_count=len(portfolio.holdings)
            )
            
            return portfolio
            
        except Exception as e:
            logger.error(
                f"Portfolio update failed: {str(e)}",
                user_id=user_id,
                portfolio_id=portfolio_id,
                error_type=e.__class__.__name__
            )
            raise
    
    def _get_portfolio(self, user_id: str, portfolio_id: str) -> Portfolio:
        """
        Retrieve portfolio from DynamoDB.
        
        Args:
            user_id: User ID
            portfolio_id: Portfolio ID
            
        Returns:
            Portfolio object
            
        Raises:
            Exception: If portfolio not found
        """
        response = self.portfolios_table.get_item(
            Key={
                "user_id": user_id,
                "portfolio_id": portfolio_id
            }
        )
        
        if "Item" not in response:
            raise ValueError(f"Portfolio not found: {portfolio_id}")
        
        return Portfolio.from_dynamodb(response["Item"])
    
    def _apply_transaction(self, portfolio: Portfolio, transaction: Dict[str, Any]) -> Portfolio:
        """
        Apply a transaction to portfolio holdings.
        
        Args:
            portfolio: Portfolio object
            transaction: Transaction details
            
        Returns:
            Updated Portfolio object
        """
        ticker = transaction["ticker"]
        quantity = transaction["quantity"]
        action = transaction["action"]
        price = transaction.get("price", 0.0)
        
        # Find or create holding
        holding = None
        for h in portfolio.holdings:
            if h.ticker == ticker:
                holding = h
                break
        
        if holding is None:
            # Create new holding for buy
            if action == "buy":
                holding = Holding(
                    ticker=ticker,
                    quantity=quantity,
                    cost_basis=price,
                    current_price=price,
                    purchase_date=datetime.utcnow().isoformat()
                )
                portfolio.holdings.append(holding)
                logger.info(
                    f"Created new holding: {ticker}",
                    ticker=ticker,
                    quantity=quantity,
                    price=price
                )
            else:
                # Sell without holding - error
                logger.warn(
                    f"Attempted to sell non-existent holding: {ticker}",
                    ticker=ticker,
                    quantity=quantity
                )
                raise ValueError(f"Cannot sell non-existent holding: {ticker}")
        else:
            # Update existing holding
            if action == "buy":
                # Update cost basis for buy
                total_cost = (holding.quantity * holding.cost_basis) + (quantity * price)
                total_quantity = holding.quantity + quantity
                holding.cost_basis = total_cost / total_quantity if total_quantity > 0 else 0
                holding.quantity = total_quantity
                holding.current_price = price
                
                logger.info(
                    f"Updated holding (buy): {ticker}",
                    ticker=ticker,
                    new_quantity=holding.quantity,
                    new_cost_basis=holding.cost_basis
                )
                
            elif action == "sell":
                # Decrease quantity for sell
                if holding.quantity < quantity:
                    raise ValueError(
                        f"Insufficient quantity to sell: have {holding.quantity}, "
                        f"trying to sell {quantity}"
                    )
                
                holding.quantity -= quantity
                holding.current_price = price
                
                # Remove holding if quantity reaches zero
                if holding.quantity == 0:
                    portfolio.holdings.remove(holding)
                    logger.info(
                        f"Removed holding (quantity zero): {ticker}",
                        ticker=ticker
                    )
                else:
                    logger.info(
                        f"Updated holding (sell): {ticker}",
                        ticker=ticker,
                        new_quantity=holding.quantity
                    )
        
        return portfolio


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for portfolio updates.
    
    Args:
        event: Lambda event containing portfolio and transaction details
        context: Lambda context
        
    Returns:
        Dictionary with update result
    """
    try:
        # Set trace ID for logging
        trace_id = context.request_id if hasattr(context, 'request_id') else str(uuid.uuid4())
        set_trace_id(trace_id)
        
        logger.info("Portfolio update started", trace_id=trace_id)
        
        # Parse input
        user_id = event.get("user_id")
        portfolio_id = event.get("portfolio_id")
        transactions = event.get("transactions", [])
        
        if not all([user_id, portfolio_id]):
            raise ValueError("Missing required fields: user_id, portfolio_id")
        
        if not transactions:
            logger.warn("No transactions to apply")
            return {
                "statusCode": 200,
                "body": {
                    "message": "No transactions to apply",
                    "portfolio_id": portfolio_id
                }
            }
        
        # Update portfolio
        updater = PortfolioUpdater()
        updated_portfolio = updater.update_portfolio(user_id, portfolio_id, transactions)
        
        return {
            "statusCode": 200,
            "body": {
                "portfolio_id": portfolio_id,
                "total_value": updated_portfolio.total_value,
                "holding_count": len(updated_portfolio.holdings),
                "updated_at": updated_portfolio.updated_at,
                "holdings": [
                    {
                        "ticker": h.ticker,
                        "quantity": h.quantity,
                        "current_price": h.current_price,
                        "market_value": h.market_value
                    }
                    for h in updated_portfolio.holdings
                ]
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
    except Exception as e:
        logger.error(f"Portfolio update error: {str(e)}", error_type=e.__class__.__name__)
        return {
            "statusCode": 500,
            "body": {
                "error": "Portfolio update failed",
                "message": str(e)
            }
        }
