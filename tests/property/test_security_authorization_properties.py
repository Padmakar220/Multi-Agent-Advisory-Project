"""
Property-based tests for authorization and user data isolation.

Tests validate that agent access is properly authorized and user data is isolated.
"""

import pytest
from hypothesis import given, settings, strategies as st
from unittest.mock import Mock, patch, MagicMock

from src.security.authorization import (
    check_user_access,
    enforce_user_isolation,
    AuthorizationChecker
)


class TestUserDataIsolation:
    """
    Property 30: User Data Isolation
    
    For any two different users, one user should not be able to access or 
    modify the other user's agent state, portfolio data, or transaction history.
    
    Validates: Requirements 13.5
    """

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        resource_owner=st.text(min_size=1, max_size=100),
        resource_type=st.sampled_from(['portfolio', 'transaction', 'agent_state']),
        resource_id=st.text(min_size=1, max_size=100)
    )
    def test_user_isolation_enforcement(
        self,
        user_id,
        resource_owner,
        resource_type,
        resource_id
    ):
        """
        Test that users cannot access other users' resources.
        
        For any resource owned by a user, only that user should be able to access it.
        """
        result = enforce_user_isolation(
            user_id=user_id,
            resource_owner=resource_owner,
            resource_type=resource_type,
            resource_id=resource_id
        )
        
        if user_id == resource_owner:
            assert result is True, "User should be able to access own resource"
        else:
            assert result is False, "User should not be able to access other's resource"

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        resource_owner=st.text(min_size=1, max_size=100),
        resource_type=st.sampled_from(['portfolio', 'transaction', 'agent_state']),
        resource_id=st.text(min_size=1, max_size=100)
    )
    def test_user_isolation_different_users(
        self,
        user_id,
        resource_owner,
        resource_type,
        resource_id
    ):
        """
        Test isolation between different users.
        
        For any two different users, they should not be able to access each other's data.
        """
        if user_id != resource_owner:
            result = enforce_user_isolation(
                user_id=user_id,
                resource_owner=resource_owner,
                resource_type=resource_type,
                resource_id=resource_id
            )
            
            assert result is False, "Different users should be isolated"

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        resource_type=st.sampled_from(['portfolio', 'transaction', 'agent_state']),
        resource_id=st.text(min_size=1, max_size=100)
    )
    def test_user_isolation_same_user(
        self,
        user_id,
        resource_type,
        resource_id
    ):
        """
        Test that users can access their own resources.
        
        For any resource owned by a user, that user should be able to access it.
        """
        result = enforce_user_isolation(
            user_id=user_id,
            resource_owner=user_id,
            resource_type=resource_type,
            resource_id=resource_id
        )
        
        assert result is True, "User should be able to access own resource"


class TestAgentAccessAuthorization:
    """
    Property 55: Agent Access Authorization
    
    For any agent attempt to access user data, authorization should be checked 
    against IAM policies before granting access.
    
    Validates: Requirements 13.2
    """

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        resource_type=st.sampled_from(['portfolio', 'transaction', 'agent_state']),
        resource_id=st.text(min_size=1, max_size=100),
        action=st.sampled_from(['read', 'write', 'delete'])
    )
    def test_authorization_check_with_owner(
        self,
        user_id,
        resource_type,
        resource_id,
        action
    ):
        """
        Test authorization check when user owns the resource.
        
        For any resource owned by a user, authorization should pass.
        """
        result = check_user_access(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            resource_owner=user_id
        )
        
        # Should pass ownership check
        assert result.user_id == user_id
        assert result.resource_id == resource_id

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        resource_owner=st.text(min_size=1, max_size=100),
        resource_type=st.sampled_from(['portfolio', 'transaction', 'agent_state']),
        resource_id=st.text(min_size=1, max_size=100),
        action=st.sampled_from(['read', 'write', 'delete'])
    )
    def test_authorization_check_different_owner(
        self,
        user_id,
        resource_owner,
        resource_type,
        resource_id,
        action
    ):
        """
        Test authorization check when user doesn't own the resource.
        
        For any resource not owned by a user, authorization should fail.
        """
        if user_id != resource_owner:
            result = check_user_access(
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                resource_owner=resource_owner
            )
            
            assert result.authorized is False, "User should not be authorized"
            assert result.reason is not None

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        resource_type=st.sampled_from(['portfolio', 'transaction', 'agent_state']),
        resource_id=st.text(min_size=1, max_size=100),
        action=st.sampled_from(['read', 'write', 'delete'])
    )
    def test_authorization_result_fields(
        self,
        user_id,
        resource_type,
        resource_id,
        action
    ):
        """
        Test that authorization result contains required fields.
        
        For any authorization check, the result should include user_id and resource_id.
        """
        result = check_user_access(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            resource_owner=user_id
        )
        
        assert result.user_id == user_id
        assert result.resource_id == resource_id
        assert result.reason is not None or result.authorized

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        resource_type=st.text(min_size=1, max_size=50),
        resource_id=st.text(min_size=1, max_size=100),
        action=st.text(min_size=1, max_size=50)
    )
    def test_authorization_with_various_actions(
        self,
        user_id,
        resource_type,
        resource_id,
        action
    ):
        """
        Test authorization with various action types.
        
        For any action type, authorization should be checked consistently.
        """
        result = check_user_access(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            resource_owner=user_id
        )
        
        assert result.user_id == user_id
        assert result.resource_id == resource_id

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        resource_type=st.sampled_from(['portfolio', 'transaction', 'agent_state']),
        resource_id=st.text(min_size=1, max_size=100)
    )
    def test_authorization_without_owner(
        self,
        user_id,
        resource_type,
        resource_id
    ):
        """
        Test authorization check without specifying resource owner.
        
        For any authorization check without owner, it should still validate.
        """
        result = check_user_access(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action='read',
            resource_owner=None
        )
        
        assert result.user_id == user_id
        assert result.resource_id == resource_id
