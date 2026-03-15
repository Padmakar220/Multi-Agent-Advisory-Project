"""
Deployment smoke tests for Multi-Agent Advisory AI System.

These tests verify that all deployed AWS resources are reachable and
functioning after a deployment. They require real AWS credentials and
are intended to run post-deployment, not in unit test suites.

Run with:
    pytest tests/smoke/ -v \
        --env dev \
        --api-endpoint https://xxx.execute-api.us-east-1.amazonaws.com/dev
"""

import json
import os
import time

import boto3
import pytest
import requests


# ─── Fixtures ────────────────────────────────────────────────────────────────

def pytest_addoption(parser):
    parser.addoption("--env", default="dev", help="Deployment environment")
    parser.addoption("--api-endpoint", default="", help="API Gateway base URL")


@pytest.fixture(scope="session")
def environment(request):
    return request.config.getoption("--env")


@pytest.fixture(scope="session")
def api_endpoint(request):
    ep = request.config.getoption("--api-endpoint")
    if not ep:
        ep = os.environ.get("API_ENDPOINT", "")
    return ep.rstrip("/")


@pytest.fixture(scope="session")
def env_prefix(environment):
    return f"advisory-{environment}"


@pytest.fixture(scope="session")
def region():
    return os.environ.get("AWS_REGION", "us-east-1")


@pytest.fixture(scope="session")
def dynamodb_client(region):
    return boto3.client("dynamodb", region_name=region)


@pytest.fixture(scope="session")
def lambda_client(region):
    return boto3.client("lambda", region_name=region)


@pytest.fixture(scope="session")
def sfn_client(region):
    return boto3.client("stepfunctions", region_name=region)


@pytest.fixture(scope="session")
def cloudwatch_client(region):
    return boto3.client("cloudwatch", region_name=region)


@pytest.fixture(scope="session")
def cfn_client(region):
    return boto3.client("cloudformation", region_name=region)


def get_stack_output(cfn_client, stack_name, output_key):
    """Retrieve a CloudFormation stack output value."""
    resp = cfn_client.describe_stacks(StackName=stack_name)
    outputs = resp["Stacks"][0].get("Outputs", [])
    for o in outputs:
        if o["OutputKey"] == output_key:
            return o["OutputValue"]
    return None


# ─── 1. API Gateway Tests ─────────────────────────────────────────────────────

class TestAPIGateway:
    def test_api_endpoint_reachable(self, api_endpoint):
        """API Gateway should respond (even with 401/403 for unauth requests)."""
        if not api_endpoint:
            pytest.skip("No --api-endpoint provided")

        resp = requests.options(f"{api_endpoint}/health", timeout=10)
        assert resp.status_code < 500, (
            f"API Gateway returned server error: {resp.status_code}"
        )

    def test_unauthenticated_request_rejected(self, api_endpoint):
        """Unauthenticated POST should return 401 or 403, not 5xx."""
        if not api_endpoint:
            pytest.skip("No --api-endpoint provided")

        resp = requests.post(
            f"{api_endpoint}/analyze",
            json={"user_id": "smoke-test"},
            timeout=10,
        )
        assert resp.status_code in (401, 403), (
            f"Expected 401/403 for unauthenticated request, got {resp.status_code}"
        )

    def test_rebalance_endpoint_exists(self, api_endpoint):
        """POST /rebalance endpoint should exist."""
        if not api_endpoint:
            pytest.skip("No --api-endpoint provided")

        resp = requests.post(
            f"{api_endpoint}/rebalance",
            json={"user_id": "smoke-test"},
            timeout=10,
        )
        # 401/403 means the endpoint exists but auth is required
        assert resp.status_code not in (404,), (
            f"/rebalance endpoint not found (404)"
        )

    def test_optimize_tax_endpoint_exists(self, api_endpoint):
        """POST /optimize-tax endpoint should exist."""
        if not api_endpoint:
            pytest.skip("No --api-endpoint provided")

        resp = requests.post(
            f"{api_endpoint}/optimize-tax",
            json={"user_id": "smoke-test"},
            timeout=10,
        )
        assert resp.status_code not in (404,), (
            f"/optimize-tax endpoint not found (404)"
        )


# ─── 2. Lambda Function Tests ─────────────────────────────────────────────────

LAMBDA_FUNCTIONS = [
    "supervisor-agent",
    "portfolio-analyzer",
    "tax-optimizer",
    "rebalancing-agent",
    "approval-handler",
    "trade-executor",
    "portfolio-updater",
]


class TestLambdaFunctions:
    @pytest.mark.parametrize("function_name", LAMBDA_FUNCTIONS)
    def test_lambda_invocable(self, lambda_client, function_name):
        """Each Lambda function should be invocable and return HTTP 200."""
        payload = json.dumps({"smoke_test": True}).encode()
        resp = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=payload,
        )
        assert resp["StatusCode"] == 200, (
            f"Lambda {function_name} returned status {resp['StatusCode']}"
        )
        # Function errors (unhandled exceptions) show up in FunctionError
        assert "FunctionError" not in resp or resp.get("FunctionError") is None, (
            f"Lambda {function_name} raised an unhandled error"
        )

    @pytest.mark.parametrize("function_name", LAMBDA_FUNCTIONS)
    def test_lambda_configuration(self, lambda_client, function_name):
        """Lambda functions should have correct runtime and timeout."""
        resp = lambda_client.get_function_configuration(FunctionName=function_name)
        assert resp["Runtime"] == "python3.11", (
            f"{function_name} runtime is {resp['Runtime']}, expected python3.11"
        )
        assert resp["Timeout"] >= 60, (
            f"{function_name} timeout {resp['Timeout']}s is too low"
        )


# ─── 3. DynamoDB Table Tests ──────────────────────────────────────────────────

class TestDynamoDB:
    @pytest.fixture(autouse=True)
    def table_names(self, env_prefix):
        self.tables = [
            f"{env_prefix}-portfolios",
            f"{env_prefix}-transactions",
            f"{env_prefix}-agent-sessions",
            f"{env_prefix}-market-data-cache",
        ]

    @pytest.mark.parametrize("table_suffix", [
        "portfolios", "transactions", "agent-sessions", "market-data-cache"
    ])
    def test_table_active(self, dynamodb_client, env_prefix, table_suffix):
        """DynamoDB tables should be in ACTIVE state."""
        table_name = f"{env_prefix}-{table_suffix}"
        resp = dynamodb_client.describe_table(TableName=table_name)
        status = resp["Table"]["TableStatus"]
        assert status == "ACTIVE", (
            f"Table {table_name} is in {status} state, expected ACTIVE"
        )

    def test_portfolios_table_schema(self, dynamodb_client, env_prefix):
        """Portfolios table should have correct key schema."""
        resp = dynamodb_client.describe_table(TableName=f"{env_prefix}-portfolios")
        key_schema = {k["AttributeName"]: k["KeyType"] for k in resp["Table"]["KeySchema"]}
        assert key_schema.get("user_id") == "HASH"
        assert key_schema.get("portfolio_id") == "RANGE"

    def test_transactions_table_has_gsi(self, dynamodb_client, env_prefix):
        """Transactions table should have PortfolioIndex GSI."""
        resp = dynamodb_client.describe_table(TableName=f"{env_prefix}-transactions")
        gsi_names = [g["IndexName"] for g in resp["Table"].get("GlobalSecondaryIndexes", [])]
        assert "PortfolioIndex" in gsi_names, (
            f"PortfolioIndex GSI not found. Found: {gsi_names}"
        )

    def test_agent_sessions_table_has_ttl(self, dynamodb_client, env_prefix):
        """AgentSessions table should have TTL enabled."""
        resp = dynamodb_client.describe_time_to_live(
            TableName=f"{env_prefix}-agent-sessions"
        )
        ttl_status = resp["TimeToLiveDescription"]["TimeToLiveStatus"]
        assert ttl_status in ("ENABLED", "ENABLING"), (
            f"TTL not enabled on agent-sessions table (status: {ttl_status})"
        )


# ─── 4. Step Functions Tests ──────────────────────────────────────────────────

class TestStepFunctions:
    @pytest.fixture(scope="class")
    def state_machine_arn(self, cfn_client, env_prefix):
        arn = get_stack_output(cfn_client, f"{env_prefix}-compute", "StateMachineArn")
        if not arn:
            pytest.skip("StateMachineArn not found in compute stack outputs")
        return arn

    def test_state_machine_exists(self, sfn_client, state_machine_arn):
        """State machine should exist and be in ACTIVE status."""
        resp = sfn_client.describe_state_machine(stateMachineArn=state_machine_arn)
        assert resp["status"] == "ACTIVE", (
            f"State machine status is {resp['status']}, expected ACTIVE"
        )

    def test_state_machine_startable(self, sfn_client, state_machine_arn):
        """Should be able to start and immediately stop a test execution."""
        exec_name = f"smoke-test-{int(time.time())}"
        resp = sfn_client.start_execution(
            stateMachineArn=state_machine_arn,
            name=exec_name,
            input=json.dumps({
                "smoke_test": True,
                "user_id": "smoke-user",
                "request_type": "analyze",
            }),
        )
        exec_arn = resp["executionArn"]
        assert exec_arn, "No execution ARN returned"

        # Clean up: stop the test execution
        try:
            sfn_client.stop_execution(
                executionArn=exec_arn,
                cause="smoke-test-cleanup",
            )
        except Exception:
            pass  # Best-effort cleanup


# ─── 5. CloudWatch Alarms Tests ───────────────────────────────────────────────

class TestCloudWatchAlarms:
    def test_alarms_configured(self, cloudwatch_client, env_prefix):
        """At least one CloudWatch alarm should be configured."""
        resp = cloudwatch_client.describe_alarms(AlarmNamePrefix=env_prefix)
        alarm_count = len(resp["MetricAlarms"])
        assert alarm_count > 0, (
            f"No CloudWatch alarms found with prefix '{env_prefix}'"
        )

    def test_no_alarms_firing(self, cloudwatch_client, env_prefix):
        """No alarms should be in ALARM state immediately after deployment."""
        resp = cloudwatch_client.describe_alarms(
            AlarmNamePrefix=env_prefix,
            StateValue="ALARM",
        )
        firing = [a["AlarmName"] for a in resp["MetricAlarms"]]
        assert len(firing) == 0, (
            f"Alarms currently firing: {firing}"
        )
