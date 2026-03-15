"""ManageAgentStateTool for agent session state persistence."""

import boto3
from typing import Dict, Optional
from datetime import datetime
from botocore.exceptions import ClientError

from src.models.portfolio import AgentState
from src.error_handling import ErrorClassifier, ErrorCategory


class ManageAgentStateTool:
    """
    MCP Tool for managing agent session state persistence.
    
    This tool provides save_state and load_state methods to persist
    and retrieve agent state from the AgentSessions DynamoDB table
    with 24-hour TTL.
    """
    
    name: str = "manage_agent_state"
    description: str = "Save or retrieve agent session state with TTL management"
    
    def __init__(self, table_name: str = "AgentSessions", region_name: str = "us-east-1"):
        """
        Initialize the ManageAgentStateTool.
        
        Args:
            table_name: Name of the DynamoDB AgentSessions table
            region_name: AWS region name
        """
        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb', region_name=region_name)
        self.table = self.dynamodb.Table(table_name)
    
    def save_state(self, session_id: str, user_id: str, agent_type: str, state: Dict) -> bool:
        """
        Persist agent state to DynamoDB with 24-hour TTL.
        
        Args:
            session_id: Unique session identifier
            user_id: User identifier
            agent_type: Type of agent (e.g., 'supervisor', 'portfolio_analyzer')
            state: State dictionary to persist
            
        Returns:
            True if save successful
            
        Raises:
            ValueError: If required parameters are missing or invalid
            ClientError: If DynamoDB operation fails
        """
        if not session_id:
            raise ValueError("session_id cannot be empty")
        if not user_id:
            raise ValueError("user_id cannot be empty")
        if not agent_type:
            raise ValueError("agent_type cannot be empty")
        if state is None:
            raise ValueError("state cannot be None")
        
        try:
            # Create AgentState object (handles TTL calculation)
            agent_state = AgentState(
                session_id=session_id,
                user_id=user_id,
                agent_type=agent_type,
                state=state,
                last_updated=datetime.utcnow().isoformat()
            )
            
            # Convert to DynamoDB format
            item = agent_state.to_dynamodb()
            
            # Save to DynamoDB
            self.table.put_item(Item=item)
            
            return True
            
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
                    'PutItem'
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
                    'PutItem'
                )
        
        except ValueError:
            # Re-raise ValueError (validation errors)
            raise
        
        except Exception as e:
            # Unexpected errors
            raise RuntimeError(f"Unexpected error saving agent state: {str(e)}")
    
    def load_state(self, session_id: str) -> Dict:
        """
        Retrieve agent session state from DynamoDB.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            State dictionary
            
        Raises:
            ValueError: If session not found or session_id is invalid
            ClientError: If DynamoDB operation fails
        """
        if not session_id:
            raise ValueError("session_id cannot be empty")
        
        try:
            # Query DynamoDB for session
            response = self.table.get_item(
                Key={'session_id': session_id}
            )
            
            # Check if session exists
            if 'Item' not in response:
                raise ValueError(f"Session not found: session_id={session_id}")
            
            # Convert DynamoDB item to AgentState object
            item = response['Item']
            agent_state = AgentState.from_dynamodb(item)
            
            # Check if session has expired
            current_time = int(datetime.utcnow().timestamp())
            if agent_state.ttl < current_time:
                raise ValueError(f"Session expired: session_id={session_id}")
            
            return agent_state.state
            
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
            # Re-raise ValueError (session not found, expired, validation errors)
            raise
        
        except Exception as e:
            # Unexpected errors
            raise RuntimeError(f"Unexpected error loading agent state: {str(e)}")
