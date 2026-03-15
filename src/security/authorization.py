"""Authorization and access control for agent operations."""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


@dataclass
class AuthorizationContext:
    """Context for authorization checks."""
    user_id: str
    agent_type: str
    action: str
    resource_type: str
    resource_id: str
    resource_owner: Optional[str] = None


@dataclass
class AuthorizationResult:
    """Result of authorization check."""
    authorized: bool
    user_id: str
    resource_id: str
    reason: Optional[str] = None
    policy_matched: Optional[str] = None


class AuthorizationChecker:
    """Checks authorization for agent operations."""
    
    def __init__(self):
        """Initialize authorization checker."""
        self.iam_client = boto3.client('iam')
        self.sts_client = boto3.client('sts')
    
    def check_user_access(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        resource_owner: Optional[str] = None
    ) -> AuthorizationResult:
        """
        Check if user is authorized to access a resource.
        
        Args:
            user_id: ID of the user making the request
            resource_type: Type of resource (portfolio, transaction, etc.)
            resource_id: ID of the resource
            action: Action being performed (read, write, delete)
            resource_owner: Owner of the resource (for isolation checks)
            
        Returns:
            AuthorizationResult indicating if access is allowed
        """
        # First check: user data isolation
        if resource_owner and user_id != resource_owner:
            return AuthorizationResult(
                authorized=False,
                user_id=user_id,
                resource_id=resource_id,
                reason='User does not own this resource',
                policy_matched=None
            )
        
        # Second check: IAM policy validation
        try:
            # Get user's IAM policies
            policies = self._get_user_policies(user_id)
            
            # Check if any policy allows the action
            for policy in policies:
                if self._policy_allows_action(policy, action, resource_type):
                    return AuthorizationResult(
                        authorized=True,
                        user_id=user_id,
                        resource_id=resource_id,
                        reason='User has required IAM policy',
                        policy_matched=policy.get('PolicyName')
                    )
            
            return AuthorizationResult(
                authorized=False,
                user_id=user_id,
                resource_id=resource_id,
                reason='No IAM policy allows this action',
                policy_matched=None
            )
        
        except Exception as e:
            logger.error(f"Error checking authorization: {e}")
            return AuthorizationResult(
                authorized=False,
                user_id=user_id,
                resource_id=resource_id,
                reason=f'Authorization check failed: {str(e)}',
                policy_matched=None
            )
    
    def enforce_user_isolation(
        self,
        user_id: str,
        resource_owner: str,
        resource_type: str,
        resource_id: str
    ) -> bool:
        """
        Enforce user data isolation.
        
        Args:
            user_id: ID of the user making the request
            resource_owner: Owner of the resource
            resource_type: Type of resource
            resource_id: ID of the resource
            
        Returns:
            True if isolation is enforced (user owns resource), False otherwise
        """
        if user_id != resource_owner:
            logger.warning(
                f"User {user_id} attempted to access {resource_type} {resource_id} "
                f"owned by {resource_owner}"
            )
            return False
        
        return True
    
    def _get_user_policies(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get IAM policies for a user.
        
        Args:
            user_id: User ID (typically from Cognito)
            
        Returns:
            List of IAM policies
        """
        # In a real implementation, this would query IAM
        # For now, return empty list (policies are checked via IAM service)
        return []
    
    def _policy_allows_action(
        self,
        policy: Dict[str, Any],
        action: str,
        resource_type: str
    ) -> bool:
        """
        Check if a policy allows an action.
        
        Args:
            policy: IAM policy document
            action: Action to check (read, write, delete)
            resource_type: Type of resource
            
        Returns:
            True if policy allows action, False otherwise
        """
        # This would parse the policy document and check permissions
        # For now, return False (actual check done by IAM service)
        return False


def check_user_access(
    user_id: str,
    resource_type: str,
    resource_id: str,
    action: str,
    resource_owner: Optional[str] = None
) -> AuthorizationResult:
    """
    Check if user is authorized to access a resource.
    
    Args:
        user_id: ID of the user making the request
        resource_type: Type of resource (portfolio, transaction, etc.)
        resource_id: ID of the resource
        action: Action being performed (read, write, delete)
        resource_owner: Owner of the resource (for isolation checks)
        
    Returns:
        AuthorizationResult indicating if access is allowed
    """
    checker = AuthorizationChecker()
    return checker.check_user_access(
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        resource_owner=resource_owner
    )


def enforce_user_isolation(
    user_id: str,
    resource_owner: str,
    resource_type: str,
    resource_id: str
) -> bool:
    """
    Enforce user data isolation.
    
    Args:
        user_id: ID of the user making the request
        resource_owner: Owner of the resource
        resource_type: Type of resource
        resource_id: ID of the resource
        
    Returns:
        True if isolation is enforced (user owns resource), False otherwise
    """
    checker = AuthorizationChecker()
    return checker.enforce_user_isolation(
        user_id=user_id,
        resource_owner=resource_owner,
        resource_type=resource_type,
        resource_id=resource_id
    )
