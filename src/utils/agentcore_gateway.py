"""AgentCore Gateway — MCP tool invocation via managed endpoint.

Registers MCP tools as AgentCore Gateway managed endpoints and provides
a unified invoke() interface.  Agents call tools through this gateway
instead of invoking Lambda functions directly.

Tool interface contracts (input/output schemas) are unchanged.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

from src.utils.agentcore_identity import AgentCoreIdentityClient, ScopeViolationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool registry — maps tool name → required scope + Lambda function name
# ---------------------------------------------------------------------------

TOOL_REGISTRY: Dict[str, Dict[str, str]] = {
    "get_portfolio": {
        "scope": "read:portfolio-data",
        "lambda_function": os.environ.get("GET_PORTFOLIO_LAMBDA", "get-portfolio-tool"),
    },
    "get_cost_basis": {
        "scope": "read:cost-basis",
        "lambda_function": os.environ.get("GET_COST_BASIS_LAMBDA", "get-cost-basis-tool"),
    },
    "query_market_data": {
        "scope": "read:market-data",
        "lambda_function": os.environ.get("QUERY_MARKET_DATA_LAMBDA", "query-market-data-tool"),
    },
    "execute_trade": {
        "scope": "invoke:trade-executor",
        "lambda_function": os.environ.get("EXECUTE_TRADE_LAMBDA", "execute-trade-tool"),
    },
}


class AgentCoreGateway:
    """
    Unified gateway for MCP tool invocations.

    Usage:
        gateway = AgentCoreGateway(agent_type="supervisor")
        result = gateway.invoke("get_portfolio", {"user_id": "u1", "portfolio_id": "p1"})
    """

    def __init__(
        self,
        agent_type: str,
        identity_client: Optional[AgentCoreIdentityClient] = None,
        region_name: str = "us-east-1",
    ):
        self.agent_type = agent_type
        self.identity_client = identity_client or AgentCoreIdentityClient(
            region_name=region_name
        )
        self.lambda_client = boto3.client("lambda", region_name=region_name)
        self._token: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _get_token(self) -> Dict[str, Any]:
        """Return a valid token, refreshing if expired."""
        import time

        if self._token is None or self._token.get("expires_at", 0) <= int(time.time()):
            self._token = self.identity_client.exchange_token(self.agent_type)
        return self._token

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def invoke(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invoke a registered MCP tool via the AgentCore Gateway.

        Validates that the agent's token grants the required scope before
        dispatching to the underlying Lambda function.

        Args:
            tool_name: Registered tool name (e.g. "get_portfolio")
            payload:   Tool input dict (unchanged from direct invocation)

        Returns:
            Tool output dict (unchanged from direct invocation)

        Raises:
            ScopeViolationError: If the agent lacks the required scope
            ValueError:          If tool_name is not registered
            RuntimeError:        If the Lambda invocation fails
        """
        if tool_name not in TOOL_REGISTRY:
            raise ValueError(
                f"Tool '{tool_name}' is not registered in AgentCore Gateway. "
                f"Available tools: {list(TOOL_REGISTRY)}"
            )

        registration = TOOL_REGISTRY[tool_name]
        required_scope = registration["scope"]
        lambda_function = registration["lambda_function"]

        # Scope check
        token = self._get_token()
        AgentCoreIdentityClient.validate_scope(token, required_scope)

        # Invoke Lambda
        try:
            response = self.lambda_client.invoke(
                FunctionName=lambda_function,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload),
            )
            result = json.loads(response["Payload"].read())
            if "errorMessage" in result:
                raise RuntimeError(
                    f"Tool '{tool_name}' returned error: {result['errorMessage']}"
                )
            return result
        except ClientError as exc:
            raise RuntimeError(
                f"Failed to invoke tool '{tool_name}': {exc.response['Error']['Message']}"
            ) from exc

    def list_tools(self) -> Dict[str, Dict[str, str]]:
        """Return the registered tool definitions."""
        return dict(TOOL_REGISTRY)
