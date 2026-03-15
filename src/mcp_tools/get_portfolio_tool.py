"""GetPortfolioTool for retrieving portfolio data from DynamoDB."""

import boto3
from typing import Optional
from botocore.exceptions import ClientError

from src.models.portfolio import Portfolio
from src.error_handling import ErrorClassifier, ErrorCategory


class GetPortfolioTool:
    """
    MCP Tool for retrieving portfolio holdings and metadata from DynamoDB.
    
    This tool queries the Portfolios table by user_id and portfolio_id,
    returning a complete Portfolio object with all holdings and metadata.
    """
    
    name: str = "get_portfolio"
    description: str = "Retrieve portfolio holdings and metadata from DynamoDB"
    
    def __init__(self, table_name: str = "Portfolios", region_name: str = "us-east-1"):
        """
        Initialize the GetPortfolioTool.
        
        Args:
            table_name: Name of the DynamoDB Portfolios table
            region_name: AWS region name
        """
        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb', region_name=region_name)
        self.table = self.dynamodb.Table(table_name)
    
    def execute(self, user_id: str, portfolio_id: str) -> Portfolio:
        """
        Retrieve portfolio data from DynamoDB.
        
        Args:
            user_id: User identifier (partition key)
            portfolio_id: Portfolio identifier (sort key)
            
        Returns:
            Portfolio object with all holdings and metadata
            
        Raises:
            ValueError: If portfolio not found
            ClientError: If DynamoDB operation fails
        """
        if not user_id:
            raise ValueError("user_id cannot be empty")
        if not portfolio_id:
            raise ValueError("portfolio_id cannot be empty")
        
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
            
            # Convert DynamoDB item to Portfolio object
            item = response['Item']
            portfolio = Portfolio.from_dynamodb(item)
            
            return portfolio
            
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
            # Re-raise ValueError (portfolio not found, validation errors)
            raise
        
        except Exception as e:
            # Unexpected errors
            raise RuntimeError(f"Unexpected error retrieving portfolio: {str(e)}")
