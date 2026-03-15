"""
Property-based tests for agent action audit logging.

Tests validate that all agent actions and data access are logged to CloudWatch.
"""

import pytest
from hypothesis import given, settings, strategies as st
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime

from src.security.audit_logging import (
    log_agent_action,
    log_data_access,
    AuditLogger,
    AuditLogEntry
)


class TestAgentActionAuditLogging:
    """
    Property 57: Agent Action Audit Logging
    
    For any agent action or data access, a log entry should be created in 
    CloudWatch with timestamp, agent type, action type, and user ID.
    
    Validates: Requirements 13.4
    """

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        agent_type=st.sampled_from([
            'portfolio_analyzer',
            'tax_optimizer',
            'rebalancing_agent',
            'supervisor'
        ]),
        action_type=st.sampled_from([
            'read',
            'write',
            'analyze',
            'optimize',
            'execute'
        ]),
        resource_type=st.sampled_from(['portfolio', 'transaction', 'agent_state']),
        resource_id=st.text(min_size=1, max_size=100)
    )
    def test_agent_action_logging(
        self,
        user_id,
        agent_type,
        action_type,
        resource_type,
        resource_id
    ):
        """
        Test that agent actions are logged.
        
        For any agent action, a log entry should be created with required fields.
        """
        with patch('src.security.audit_logging.logger') as mock_logger:
            trace_id = log_agent_action(
                user_id=user_id,
                agent_type=agent_type,
                action_type=action_type,
                resource_type=resource_type,
                resource_id=resource_id,
                status='success'
            )
            
            assert trace_id is not None
            assert len(trace_id) > 0
            mock_logger.info.assert_called()

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        agent_type=st.sampled_from([
            'portfolio_analyzer',
            'tax_optimizer',
            'rebalancing_agent'
        ]),
        access_type=st.sampled_from(['read', 'write', 'delete']),
        resource_type=st.sampled_from(['portfolio', 'transaction', 'agent_state']),
        resource_id=st.text(min_size=1, max_size=100)
    )
    def test_data_access_logging(
        self,
        user_id,
        agent_type,
        access_type,
        resource_type,
        resource_id
    ):
        """
        Test that data access is logged.
        
        For any data access by an agent, a log entry should be created.
        """
        with patch('src.security.audit_logging.logger') as mock_logger:
            trace_id = log_data_access(
                user_id=user_id,
                agent_type=agent_type,
                access_type=access_type,
                resource_type=resource_type,
                resource_id=resource_id
            )
            
            assert trace_id is not None
            assert len(trace_id) > 0
            mock_logger.info.assert_called()

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        agent_type=st.sampled_from([
            'portfolio_analyzer',
            'tax_optimizer',
            'rebalancing_agent'
        ]),
        action_type=st.text(min_size=1, max_size=50),
        resource_type=st.text(min_size=1, max_size=50),
        resource_id=st.text(min_size=1, max_size=100)
    )
    def test_audit_log_entry_fields(
        self,
        user_id,
        agent_type,
        action_type,
        resource_type,
        resource_id
    ):
        """
        Test that audit log entries contain required fields.
        
        For any audit log entry, it should include timestamp, user_id, agent_type, 
        action_type, and resource information.
        """
        entry = AuditLogEntry(
            timestamp=datetime.utcnow().isoformat() + 'Z',
            trace_id='trace-123',
            user_id=user_id,
            agent_type=agent_type,
            action_type=action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            status='success'
        )
        
        assert entry.timestamp is not None
        assert entry.trace_id == 'trace-123'
        assert entry.user_id == user_id
        assert entry.agent_type == agent_type
        assert entry.action_type == action_type
        assert entry.resource_type == resource_type
        assert entry.resource_id == resource_id
        assert entry.status == 'success'

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        agent_type=st.sampled_from([
            'portfolio_analyzer',
            'tax_optimizer',
            'rebalancing_agent'
        ]),
        action_type=st.text(min_size=1, max_size=50),
        resource_type=st.text(min_size=1, max_size=50),
        resource_id=st.text(min_size=1, max_size=100),
        status=st.sampled_from(['success', 'failure', 'error'])
    )
    def test_audit_log_status_tracking(
        self,
        user_id,
        agent_type,
        action_type,
        resource_type,
        resource_id,
        status
    ):
        """
        Test that audit logs track action status.
        
        For any agent action, the log should record whether it succeeded or failed.
        """
        with patch('src.security.audit_logging.logger') as mock_logger:
            trace_id = log_agent_action(
                user_id=user_id,
                agent_type=agent_type,
                action_type=action_type,
                resource_type=resource_type,
                resource_id=resource_id,
                status=status
            )
            
            assert trace_id is not None
            mock_logger.info.assert_called()

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        agent_type=st.sampled_from([
            'portfolio_analyzer',
            'tax_optimizer',
            'rebalancing_agent'
        ]),
        action_type=st.text(min_size=1, max_size=50),
        resource_type=st.text(min_size=1, max_size=50),
        resource_id=st.text(min_size=1, max_size=100)
    )
    def test_trace_id_generation(
        self,
        user_id,
        agent_type,
        action_type,
        resource_type,
        resource_id
    ):
        """
        Test that trace IDs are generated for audit logs.
        
        For any audit log entry, a unique trace ID should be generated.
        """
        with patch('src.security.audit_logging.logger') as mock_logger:
            trace_id1 = log_agent_action(
                user_id=user_id,
                agent_type=agent_type,
                action_type=action_type,
                resource_type=resource_type,
                resource_id=resource_id
            )
            
            trace_id2 = log_agent_action(
                user_id=user_id,
                agent_type=agent_type,
                action_type=action_type,
                resource_type=resource_type,
                resource_id=resource_id
            )
            
            assert trace_id1 != trace_id2, "Trace IDs should be unique"

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        agent_type=st.sampled_from([
            'portfolio_analyzer',
            'tax_optimizer',
            'rebalancing_agent'
        ]),
        action_type=st.text(min_size=1, max_size=50),
        resource_type=st.text(min_size=1, max_size=50),
        resource_id=st.text(min_size=1, max_size=100),
        trace_id=st.text(min_size=10, max_size=100)
    )
    def test_trace_id_propagation(
        self,
        user_id,
        agent_type,
        action_type,
        resource_type,
        resource_id,
        trace_id
    ):
        """
        Test that trace IDs are propagated through logs.
        
        For any audit log with a provided trace ID, it should be used.
        """
        with patch('src.security.audit_logging.logger') as mock_logger:
            returned_trace_id = log_agent_action(
                user_id=user_id,
                agent_type=agent_type,
                action_type=action_type,
                resource_type=resource_type,
                resource_id=resource_id,
                trace_id=trace_id
            )
            
            assert returned_trace_id == trace_id

    @settings(max_examples=50)
    @given(
        user_id=st.text(min_size=1, max_size=100),
        agent_type=st.sampled_from([
            'portfolio_analyzer',
            'tax_optimizer',
            'rebalancing_agent'
        ]),
        action_type=st.text(min_size=1, max_size=50),
        resource_type=st.text(min_size=1, max_size=50),
        resource_id=st.text(min_size=1, max_size=100),
        details=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.text(min_size=1, max_size=100),
            min_size=0,
            max_size=3
        )
    )
    def test_audit_log_with_details(
        self,
        user_id,
        agent_type,
        action_type,
        resource_type,
        resource_id,
        details
    ):
        """
        Test that audit logs can include additional details.
        
        For any agent action, additional context details should be logged.
        """
        with patch('src.security.audit_logging.logger') as mock_logger:
            trace_id = log_agent_action(
                user_id=user_id,
                agent_type=agent_type,
                action_type=action_type,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details
            )
            
            assert trace_id is not None
            mock_logger.info.assert_called()
