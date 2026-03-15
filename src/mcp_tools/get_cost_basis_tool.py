"""GetCostBasisTool for retrieving cost basis information from DynamoDB."""

import boto3
from typing import Optional
from botocore.exceptions import ClientError

from src.models.responses import CostBasisInfo
from src.error_handling import ErrorClassifier, ErrorCategory


class GetCostBasisTool:
    """
    MCP Tool for retrieving cost basis information for securities.
    
    This tool queries the Portfolios table for specific ticker holdings
    with purchase dates and returns cost basis data.
    """
    
    name: str = "get_cost_basis"
    description: str = "Retrieve cost basis information for securities from DynamoDB"
    
    def __init__(self, table_name: str = "Portfolios", region_name: str = "us-east-1"):
        """
        Initialize the GetCostBasisTool.
        
        Args:
            table_name: Name of the DynamoDB Portfolios table
            region_name: AWS region name
        """
        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb', region_name=region_name)
        self.table = self.dynamodb.Table(table_name)
    
    def execute(self, user_id: str, portfolio_id: str, ticker: str) -> CostBasisInfo:
        """
        Retrieve cost basis information for a specific security.
        
        Args:
            user_id: User identifier (partition key)
            portfolio_id: Portfolio identifier (sort key)
            ticker: Ticker symbol to retrieve cost basis for
            
        Returns:
            CostBasisInfo object with cost per share and purchase date
            
        Raises:
            ValueError: If portfolio or ticker not found, or invalid input
            ClientError: If DynamoDB operation fails
        """
        if not user_id:
            raise ValueError("user_id cannot be empty")
        if not portfolio_id:
            raise ValueError("portfolio_id cannot be empty")
        if not ticker:
            raise ValueError("ticker cannot be empty")
        
        try:
            # Query DynamoDB for portfolio
            response = self.table.get_item(
                Key={
                    'user_id': user_id,
                    'portfolio_id': portfolio_id
                }
            )
            
            # Check if portfolio exists
            if 'Item' not in response:
                raise ValueError(
                    f"Portfolio not found: user_id={user_id}, portfolio_id={portfolio_id}"
                )
            
            # Find the ticker in holdings
            item = response['Item']
            holdings = item.get('holdings', [])
            
            ticker_holding = None
            for holding in holdings:
                if holding.get('ticker') == ticker:
                    ticker_holding = holding
                    break
            
            if ticker_holding is None:
                raise ValueError(
                    f"Ticker {ticker} not found in portfolio {portfolio_id}"
                )
            
            # Extract cost basis information
            cost_basis_info = CostBasisInfo(
                ticker=ticker,
                quantity=int(ticker_holding['quantity']),
                cost_per_share=float(ticker_holding['cost_basis']),
                purchase_date=ticker_holding['purchase_date']
            )
            
            return cost_basis_info
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            # Classify error for appropriate handling
            category = ErrorClassifier.categorize(e)
            
            if category == ErrorCategory.TRANSIENT:
                # Transient errors should be retried by caller
                raise ClientError(
                    {
                        'Error': {
                            'Code': error_code,
                            'Message': f"Transient DynamoDB error: {error_message}"
                        }
                    },
                    'GetItem'
                )
            elif category == ErrorCategory.PERMANENT:
                # Permanent errors should not be retried
                raise ValueError(f"Invalid request: {error_message}")
            else:
                # Critical errors
                raise ClientError(
                    {
                        'Error': {
                            'Code': 'CriticalError',
                            'Message': f"Critical DynamoDB error: {error_message}"
                        }
                    },
                    'GetItem'
                )
        
        except ValueError:
            # Re-raise ValueError (portfolio/ticker not found, validation errors)
            raise
        
        except Exception as e:
            # Unexpected errors
            raise RuntimeError(f"Unexpected error retrieving cost basis: {str(e)}")
