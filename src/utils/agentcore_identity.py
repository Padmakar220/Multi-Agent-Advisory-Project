"""AgentCore Identity — per-agent OAuth 2.0 scope definitions and token exchange.

Each agent type has a fixed scope set.  At Lambda invocation start the handler
calls `exchange_token()` to obtain a short-lived token that is used for all
downstream tool and brokerage API calls within that invocation.
"""

import logging
import os
import time
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-agent scope definitions (Requirement 22.6)
# ---------------------------------------------------------------------------

AGENT_SCOPES: Dict[str, List[str]] = {
    "supervisor": [
        "invoke:portfolio-analyzer",
        "invoke:tax-optimizer",
        "invoke:rebalancing-agent",
    ],
    "portfolio_analyzer": [
        "read:portfolio-data",
        "read:market-data",
        "invoke:bedrock",
    ],
    "tax_optimizer": [
        "read:portfolio-data",
        "read:cost-basis",
        "invoke:bedrock",
    ],
    "rebalancing_agent": [
        "read:portfolio-data",
        "invoke:bedrock",
        "invoke:trade-executor",
    ],
}


class ScopeViolationError(Exception):
    """Raised when an agent attempts to use a scope it is not authorised for."""


class AgentCoreIdentityClient:
    """
    Thin wrapper around the AgentCore Identity token exchange endpoint.

    In production this calls the AgentCore Identity service.  In tests the
    client is replaced with a mock.
    """

    def __init__(
        self,
        identity_endpoint: Optional[str] = None,
        region_name: str = "us-east-1",
    ):
        self.identity_endpoint = identity_endpoint or os.environ.get(
            "AGENTCORE_IDENTITY_ENDPOINT", "https://agentcore.identity.amazonaws.com"
        )
        self.region_name = region_name
        # boto3 session used for SigV4 signing of identity requests
        self._session = boto3.Session(region_name=region_name)

    def exchange_token(self, agent_type: str) -> Dict[str, object]:
        """
        Exchange the Lambda execution role credentials for a short-lived
        AgentCore Identity token scoped to *agent_type*.

        Returns a dict with keys:
            access_token  — bearer token for downstream calls
            scopes        — list of granted scopes
            expires_at    — Unix timestamp when the token expires
        """
        if agent_type not in AGENT_SCOPES:
            raise ValueError(f"Unknown agent_type: {agent_type!r}")

        scopes = AGENT_SCOPES[agent_type]

        # In a real deployment this would call the AgentCore Identity REST API
        # with SigV4 signing.  Here we return a structured mock token so that
        # the rest of the system can be tested end-to-end without a live endpoint.
        token = {
            "access_token": f"agentcore-token-{agent_type}-{int(time.time())}",
            "scopes": scopes,
            "expires_at": int(time.time()) + 900,  # 15-minute TTL
            "agent_type": agent_type,
        }
        logger.info(
            "AgentCore Identity token issued",
            extra={"agent_type": agent_type, "scopes": scopes},
        )
        return token

    @staticmethod
    def validate_scope(token: Dict[str, object], required_scope: str) -> None:
        """
        Assert that *token* grants *required_scope*.

        Raises ScopeViolationError if the scope is not present.
        """
        granted: List[str] = token.get("scopes", [])
        if required_scope not in granted:
            agent_type = token.get("agent_type", "unknown")
            raise ScopeViolationError(
                f"Agent '{agent_type}' does not have scope '{required_scope}'. "
                f"Granted scopes: {granted}"
            )
