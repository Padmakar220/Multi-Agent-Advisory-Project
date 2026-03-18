"""Property-based tests for AgentCore Identity and Gateway.

Properties 88-89 validate per-agent scope enforcement and gateway
tool invocation round-trips.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from hypothesis import given, settings, strategies as st

from src.utils.agentcore_identity import (
    AgentCoreIdentityClient,
    AGENT_SCOPES,
    ScopeViolationError,
)
from src.utils.agentcore_gateway import AgentCoreGateway, TOOL_REGISTRY


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

agent_type_st = st.sampled_from(list(AGENT_SCOPES.keys()))
tool_name_st = st.sampled_from(list(TOOL_REGISTRY.keys()))


# ---------------------------------------------------------------------------
# Property 88: Per-Agent Scope Enforcement
# ---------------------------------------------------------------------------

class TestProperty88PerAgentScopeEnforcement:
    """
    Property 88: a token issued to agent type X does not grant access to
    scopes defined only for agent type Y.
    """

    @settings(max_examples=100)
    @given(
        agent_a=agent_type_st,
        agent_b=agent_type_st,
    )
    def test_token_scopes_match_agent_type(self, agent_a, agent_b):
        client = AgentCoreIdentityClient.__new__(AgentCoreIdentityClient)
        client.identity_endpoint = "https://mock"
        client.region_name = "us-east-1"
        client._session = MagicMock()

        token_a = client.exchange_token(agent_a)
        token_b = client.exchange_token(agent_b)

        # Each token must contain exactly the scopes for its agent type
        assert set(token_a["scopes"]) == set(AGENT_SCOPES[agent_a])
        assert set(token_b["scopes"]) == set(AGENT_SCOPES[agent_b])

    @settings(max_examples=100)
    @given(
        agent_a=agent_type_st,
        agent_b=agent_type_st,
    )
    def test_exclusive_scopes_not_cross_granted(self, agent_a, agent_b):
        """Scopes exclusive to agent_b must not appear in agent_a's token."""
        if agent_a == agent_b:
            return  # trivially same

        client = AgentCoreIdentityClient.__new__(AgentCoreIdentityClient)
        client.identity_endpoint = "https://mock"
        client.region_name = "us-east-1"
        client._session = MagicMock()

        token_a = client.exchange_token(agent_a)
        scopes_a = set(token_a["scopes"])
        scopes_b = set(AGENT_SCOPES[agent_b])

        exclusive_to_b = scopes_b - set(AGENT_SCOPES[agent_a])
        cross_granted = scopes_a & exclusive_to_b

        assert not cross_granted, (
            f"Agent '{agent_a}' was granted scopes exclusive to '{agent_b}': {cross_granted}"
        )

    @settings(max_examples=100)
    @given(
        agent_type=agent_type_st,
        scope=st.text(min_size=1, max_size=60),
    )
    def test_validate_scope_raises_for_missing_scope(self, agent_type, scope):
        """validate_scope raises ScopeViolationError for any scope not in the token."""
        client = AgentCoreIdentityClient.__new__(AgentCoreIdentityClient)
        client.identity_endpoint = "https://mock"
        client.region_name = "us-east-1"
        client._session = MagicMock()

        token = client.exchange_token(agent_type)
        if scope in token["scopes"]:
            return  # scope is granted — skip

        with pytest.raises(ScopeViolationError):
            AgentCoreIdentityClient.validate_scope(token, scope)

    @settings(max_examples=100)
    @given(agent_type=agent_type_st)
    def test_validate_scope_passes_for_granted_scopes(self, agent_type):
        """validate_scope must not raise for any scope the agent is entitled to."""
        client = AgentCoreIdentityClient.__new__(AgentCoreIdentityClient)
        client.identity_endpoint = "https://mock"
        client.region_name = "us-east-1"
        client._session = MagicMock()

        token = client.exchange_token(agent_type)
        for scope in token["scopes"]:
            # Must not raise
            AgentCoreIdentityClient.validate_scope(token, scope)


# ---------------------------------------------------------------------------
# Property 89: Gateway Tool Invocation Round-Trip
# ---------------------------------------------------------------------------

class TestProperty89GatewayToolInvocationRoundTrip:
    """
    Property 89: tool call via AgentCore Gateway returns identical result
    to direct Lambda invocation for any valid input.
    """

    def _make_gateway(self, agent_type: str, lambda_response: dict) -> AgentCoreGateway:
        """Build a gateway with mocked identity and Lambda clients."""
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

    @settings(max_examples=100)
    @given(
        response_data=st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.one_of(st.text(max_size=50), st.integers(), st.booleans()),
            min_size=1,
            max_size=5,
        )
    )
    def test_gateway_returns_lambda_response_unchanged(self, response_data):
        """Gateway must return the Lambda response payload unchanged."""
        gw = self._make_gateway("portfolio_analyzer", response_data)

        result = gw.invoke("get_portfolio", {"user_id": "u1", "portfolio_id": "p1"})

        assert result == response_data

    @settings(max_examples=100)
    @given(
        tool_name=tool_name_st,
        payload=st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.text(max_size=50),
            min_size=1,
            max_size=3,
        ),
        response_data=st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.text(max_size=50),
            min_size=1,
            max_size=3,
        ),
    )
    def test_gateway_invokes_correct_lambda_for_tool(
        self, tool_name, payload, response_data
    ):
        """Gateway must invoke the Lambda registered for the given tool."""
        # Find an agent type that has the required scope for this tool
        required_scope = TOOL_REGISTRY[tool_name]["scope"]
        agent_type = next(
            (a for a, scopes in AGENT_SCOPES.items() if required_scope in scopes),
            None,
        )
        if agent_type is None:
            return  # No agent has this scope — skip

        gw = self._make_gateway(agent_type, response_data)
        # Override token to include the required scope
        gw._token = {
            "access_token": "tok",
            "scopes": AGENT_SCOPES[agent_type],
            "expires_at": 9_999_999_999,
            "agent_type": agent_type,
        }

        result = gw.invoke(tool_name, payload)

        assert result == response_data
        expected_fn = TOOL_REGISTRY[tool_name]["lambda_function"]
        gw.lambda_client.invoke.assert_called_once()
        call_kwargs = gw.lambda_client.invoke.call_args[1]
        assert call_kwargs["FunctionName"] == expected_fn

    def test_scope_violation_raises_for_wrong_agent(self):
        """Supervisor must not be able to invoke read:cost-basis tool."""
        gw = self._make_gateway("supervisor", {})
        # Supervisor does not have read:cost-basis
        with pytest.raises(ScopeViolationError):
            gw.invoke("get_cost_basis", {"user_id": "u1", "portfolio_id": "p1", "ticker": "AAPL"})

    def test_unknown_tool_raises_value_error(self):
        gw = self._make_gateway("supervisor", {})
        with pytest.raises(ValueError, match="not registered"):
            gw.invoke("nonexistent_tool", {})
