"""Utility functions and helpers for the Multi-Agent Advisory AI System."""

from src.utils.logging import (
    StructuredLogger,
    TraceContext,
    set_trace_id,
    get_trace_id,
    create_logger
)
from src.utils.agentcore_memory import AgentCoreMemoryClient, session_namespace, user_namespace
from src.utils.agentcore_identity import AgentCoreIdentityClient, AGENT_SCOPES, ScopeViolationError
from src.utils.agentcore_gateway import AgentCoreGateway, TOOL_REGISTRY

__all__ = [
    "StructuredLogger",
    "TraceContext",
    "set_trace_id",
    "get_trace_id",
    "create_logger",
    "AgentCoreMemoryClient",
    "session_namespace",
    "user_namespace",
    "AgentCoreIdentityClient",
    "AGENT_SCOPES",
    "ScopeViolationError",
    "AgentCoreGateway",
    "TOOL_REGISTRY",
]
