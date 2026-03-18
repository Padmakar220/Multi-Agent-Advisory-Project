"""Unit tests for AgentCore Identity and Gateway integration."""

import json
import time
import pytest
from unittest.mock import MagicMock, patch

from src.utils.agentcore_identity import (
    AgentCoreIdentityClient,
    AGENT_SCOPES,
    ScopeViolationError,
)
from src.utils.agentcore_gateway import AgentCoreGateway, TOOL_REGISTRY


# ---------------------------------------------------------------------------
# AgentCoreIdentityClient
# ---------------------------------------------------------------------------

class TestAgentCoreIdentityClient:
    def _client(self):
        c = AgentCoreIdentityClient.__new__(AgentCoreIdentityClient)
        c.identity_endpoint = "https://mock"
        c.region_name = "us-east-1"
        c._session = MagicMock()
        return c

    def test_exchange_token_returns_correct_scopes_for_supervisor(self):
        token = self._client().exchange_token("supervisor")
        assert set(token["scopes"]) == set(AGENT_SCOPES["supervisor"])

    def test_exchange_token_returns_correct_scopes_for_portfolio_analyzer(self):
        token = self._client().exchange_token("portfolio_analyzer")
        assert set(token["scopes"]) == set(AGENT_SCOPES["portfolio_analyzer"])

    def test_exchange_token_returns_correct_scopes_for_tax_optimizer(self):
        token = self._client().exchange_token("tax_optimizer")
        assert set(token["scopes"]) == set(AGENT_SCOPES["tax_optimizer"])

    def test_exchange_token_returns_correct_scopes_for_rebalancing_agent(self):
        token = self._client().exchange_token("rebalancing_agent")
        assert set(token["scopes"]) == set(AGENT_SCOPES["rebalancing_agent"])

    def test_exchange_token_unknown_agent_raises(self):
        with pytest.raises(ValueError, match="Unknown agent_type"):
            self._client().exchange_token("unknown_agent")

    def test_token_has_expiry(self):
        token = self._client().exchange_token("supervisor")
        assert token["expires_at"] > int(time.time())

    def test_validate_scope_passes_for_granted_scope(self):
        token = {"scopes": ["read:portfolio-data", "invoke:bedrock"], "agent_type": "portfolio_analyzer"}
        AgentCoreIdentityClient.validate_scope(token, "read:portfolio-data")  # no exception

    def test_validate_scope_raises_for_missing_scope(self):
        token = {"scopes": ["read:portfolio-data"], "agent_type": "portfolio_analyzer"}
        with pytest.raises(ScopeViolationError, match="invoke:trade-executor"):
            AgentCoreIdentityClient.validate_scope(token, "invoke:trade-executor")

    def test_validate_scope_error_message_includes_agent_type(self):
        token = {"scopes": [], "agent_type": "supervisor"}
        with pytest.raises(ScopeViolationError) as exc_info:
            AgentCoreIdentityClient.validate_scope(token, "read:cost-basis")
        assert "supervisor" in str(exc_info.value)


# ---------------------------------------------------------------------------
# AgentCoreGateway
# ---------------------------------------------------------------------------

def _make_gateway(agent_type: str, lambda_response: dict) -> AgentCoreGateway:
    mock_identity = MagicMock(spec=AgentCoreIdentityClient)
    mock_identity.exchange_token.return_value = {
        "access_token": "tok",
        "scopes": AGENT_SCOPES[agent_type],
        "expires_at": 9_999_999_999,
        "agent_type": agent_type,
    }

    gw = AgentCoreGateway.__new__(AgentCoreGateway)
    gw.agent_type = agent_type
    gw.identity_client = mock_identity
    gw._token = None

    mock_lambda = MagicMock()
    payload_bytes = json.dumps(lambda_response).encode()
    mock_lambda.invoke.return_value = {
        "Payload": MagicMock(read=MagicMock(return_value=payload_bytes))
    }
    gw.lambda_client = mock_lambda
    return gw


class TestAgentCoreGateway:
    def test_invoke_get_portfolio_returns_response(self):
        expected = {"portfolio_id": "p1", "holdings": []}
        gw = _make_gateway("portfolio_analyzer", expected)
        result = gw.invoke("get_portfolio", {"user_id": "u1", "portfolio_id": "p1"})
        assert result == expected

    def test_invoke_calls_correct_lambda_function(self):
        gw = _make_gateway("portfolio_analyzer", {"ok": True})
        gw.invoke("get_portfolio", {"user_id": "u1", "portfolio_id": "p1"})
        call_kwargs = gw.lambda_client.invoke.call_args[1]
        assert call_kwargs["FunctionName"] == TOOL_REGISTRY["get_portfolio"]["lambda_function"]

    def test_scope_rejection_for_out_of_scope_tool(self):
        """Supervisor cannot call get_cost_basis (read:cost-basis not in supervisor scopes)."""
        gw = _make_gateway("supervisor", {})
        with pytest.raises(ScopeViolationError):
            gw.invoke("get_cost_basis", {"user_id": "u1", "portfolio_id": "p1", "ticker": "AAPL"})

    def test_unknown_tool_raises_value_error(self):
        gw = _make_gateway("supervisor", {})
        with pytest.raises(ValueError, match="not registered"):
            gw.invoke("nonexistent_tool", {})

    def test_lambda_error_message_raises_runtime_error(self):
        gw = _make_gateway("portfolio_analyzer", {"errorMessage": "function crashed"})
        with pytest.raises(RuntimeError, match="function crashed"):
            gw.invoke("get_portfolio", {"user_id": "u1", "portfolio_id": "p1"})

    def test_token_refreshed_when_expired(self):
        gw = _make_gateway("portfolio_analyzer", {"ok": True})
        # Set an expired token
        gw._token = {
            "access_token": "old",
            "scopes": AGENT_SCOPES["portfolio_analyzer"],
            "expires_at": 1,  # epoch — definitely expired
            "agent_type": "portfolio_analyzer",
        }
        gw.invoke("get_portfolio", {"user_id": "u1", "portfolio_id": "p1"})
        # exchange_token should have been called to refresh
        gw.identity_client.exchange_token.assert_called_once_with("portfolio_analyzer")

    def test_list_tools_returns_registry(self):
        gw = _make_gateway("supervisor", {})
        tools = gw.list_tools()
        assert set(tools.keys()) == set(TOOL_REGISTRY.keys())

    def test_gateway_unavailable_raises_runtime_error(self):
        """When AgentCore Identity is unavailable, exchange_token raises."""
        gw = _make_gateway("portfolio_analyzer", {})
        gw.identity_client.exchange_token.side_effect = RuntimeError("identity service down")
        gw._token = None  # force refresh

        with pytest.raises(RuntimeError, match="identity service down"):
            gw.invoke("get_portfolio", {"user_id": "u1", "portfolio_id": "p1"})
