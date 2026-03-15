"""Audit logging for agent actions and data access."""

import logging
import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

import boto3

logger = logging.getLogger(__name__)


@dataclass
class AuditLogEntry:
    """Audit log entry for agent actions."""
    timestamp: str
    trace_id: str
    user_id: str
    agent_type: str
    action_type: str
    resource_type: str
    resource_id: str
    status: str
    details: Optional[Dict[str, Any]] = None


class AuditLogger:
    """Logs agent actions and data access to CloudWatch."""
    
    def __init__(self, log_group: str = '/aws/lambda/portfolio-advisor'):
        """Initialize audit logger."""
        self.cloudwatch = boto3.client('logs')
        self.log_group = log_group
        self.log_stream = f'audit-{datetime.utcnow().strftime("%Y-%m-%d")}'
    
    def log_agent_action(
        self,
        user_id: str,
        agent_type: str,
        action_type: str,
        resource_type: str,
        resource_id: str,
        status: str = 'success',
        details: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ) -> str:
        """
        Log an agent action.
        
        Args:
            user_id: ID of the user
            agent_type: Type of agent (portfolio_analyzer, tax_optimizer, etc.)
            action_type: Type of action (read, write, analyze, etc.)
            resource_type: Type of resource (portfolio, transaction, etc.)
            resource_id: ID of the resource
            status: Status of the action (success, failure, etc.)
            details: Additional details about the action
            trace_id: Trace ID for correlation
            
        Returns:
            Trace ID for the log entry
        """
        if not trace_id:
            trace_id = str(uuid.uuid4())
        
        entry = AuditLogEntry(
            timestamp=datetime.utcnow().isoformat() + 'Z',
            trace_id=trace_id,
            user_id=user_id,
            agent_type=agent_type,
            action_type=action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            details=details
        )
        
        self._write_log(entry)
        return trace_id
    
    def log_data_access(
        self,
        user_id: str,
        agent_type: str,
        access_type: str,
        resource_type: str,
        resource_id: str,
        trace_id: Optional[str] = None
    ) -> str:
        """
        Log data access by an agent.
        
        Args:
            user_id: ID of the user
            agent_type: Type of agent
            access_type: Type of access (read, write, delete)
            resource_type: Type of resource
            resource_id: ID of the resource
            trace_id: Trace ID for correlation
            
        Returns:
            Trace ID for the log entry
        """
        return self.log_agent_action(
            user_id=user_id,
            agent_type=agent_type,
            action_type=f'data_access_{access_type}',
            resource_type=resource_type,
            resource_id=resource_id,
            status='success',
            trace_id=trace_id
        )
    
    def _write_log(self, entry: AuditLogEntry) -> None:
        """Write log entry to CloudWatch."""
        try:
            log_message = json.dumps(asdict(entry))
            logger.info(log_message)
        except Exception as e:
            logger.error(f"Error writing audit log: {e}")


def log_agent_action(
    user_id: str,
    agent_type: str,
    action_type: str,
    resource_type: str,
    resource_id: str,
    status: str = 'success',
    details: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None
) -> str:
    """Log an agent action."""
    logger_instance = AuditLogger()
    return logger_instance.log_agent_action(
        user_id=user_id,
        agent_type=agent_type,
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        details=details,
        trace_id=trace_id
    )


def log_data_access(
    user_id: str,
    agent_type: str,
    access_type: str,
    resource_type: str,
    resource_id: str,
    trace_id: Optional[str] = None
) -> str:
    """Log data access by an agent."""
    logger_instance = AuditLogger()
    return logger_instance.log_data_access(
        user_id=user_id,
        agent_type=agent_type,
        access_type=access_type,
        resource_type=resource_type,
        resource_id=resource_id,
        trace_id=trace_id
    )
