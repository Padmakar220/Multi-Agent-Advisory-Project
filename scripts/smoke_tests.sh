#!/bin/bash
# Post-deployment smoke tests for Multi-Agent Advisory AI System
# Usage: ./scripts/smoke_tests.sh --env dev --api-endpoint https://xxx.execute-api.us-east-1.amazonaws.com/dev

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ENVIRONMENT=""
API_ENDPOINT=""
REGION="${AWS_REGION:-us-east-1}"
FAILURES=0

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --env)          ENVIRONMENT="$2"; shift ;;
        --api-endpoint) API_ENDPOINT="$2"; shift ;;
        --region)       REGION="$2"; shift ;;
        *) echo -e "${RED}Unknown parameter: $1${NC}"; exit 1 ;;
    esac
    shift
done

if [ -z "${ENVIRONMENT}" ] || [ -z "${API_ENDPOINT}" ]; then
    echo -e "${RED}Usage: $0 --env dev --api-endpoint https://...${NC}"
    exit 1
fi

ENV_PREFIX="advisory-${ENVIRONMENT}"

pass() { echo -e "${GREEN}✓ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; FAILURES=$((FAILURES + 1)); }
info() { echo -e "${YELLOW}  $1${NC}"; }

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}Smoke Tests - ${ENVIRONMENT}${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# ─── 1. API Gateway ──────────────────────────────────────────────────────────
echo "1. API Gateway endpoints"

# Health check (unauthenticated OPTIONS for CORS)
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X OPTIONS "${API_ENDPOINT}/health" \
    --max-time 10 2>/dev/null || echo "000")

if [[ "${HTTP_STATUS}" =~ ^(200|204|403|405)$ ]]; then
    pass "API Gateway reachable (HTTP ${HTTP_STATUS})"
else
    fail "API Gateway unreachable (HTTP ${HTTP_STATUS})"
fi

# Unauthenticated request should return 401/403, not 5xx
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${API_ENDPOINT}/analyze" \
    -H "Content-Type: application/json" \
    -d '{"user_id":"smoke-test"}' \
    --max-time 10 2>/dev/null || echo "000")

if [[ "${HTTP_STATUS}" =~ ^(401|403)$ ]]; then
    pass "Unauthenticated request correctly rejected (HTTP ${HTTP_STATUS})"
elif [[ "${HTTP_STATUS}" =~ ^5 ]]; then
    fail "API returned server error on unauthenticated request (HTTP ${HTTP_STATUS})"
else
    info "Unexpected status ${HTTP_STATUS} for unauthenticated request"
fi

echo ""

# ─── 2. Lambda Functions ─────────────────────────────────────────────────────
echo "2. Lambda function invocations"

LAMBDA_FUNCTIONS=(
    "supervisor-agent"
    "portfolio-analyzer"
    "tax-optimizer"
    "rebalancing-agent"
    "approval-handler"
    "trade-executor"
    "portfolio-updater"
)

for fn in "${LAMBDA_FUNCTIONS[@]}"; do
    RESULT=$(aws lambda invoke \
        --function-name "${fn}" \
        --payload '{"smoke_test": true}' \
        --region "${REGION}" \
        --cli-binary-format raw-in-base64-out \
        /tmp/smoke_response.json \
        --query 'StatusCode' \
        --output text 2>/dev/null || echo "ERROR")

    if [ "${RESULT}" = "200" ]; then
        pass "Lambda ${fn} invocable"
    else
        fail "Lambda ${fn} invocation failed (status: ${RESULT})"
    fi
done

echo ""

# ─── 3. DynamoDB Tables ──────────────────────────────────────────────────────
echo "3. DynamoDB table access"

TABLES=(
    "${ENV_PREFIX}-portfolios"
    "${ENV_PREFIX}-transactions"
    "${ENV_PREFIX}-agent-sessions"
    "${ENV_PREFIX}-market-data-cache"
)

for table in "${TABLES[@]}"; do
    STATUS=$(aws dynamodb describe-table \
        --table-name "${table}" \
        --region "${REGION}" \
        --query 'Table.TableStatus' \
        --output text 2>/dev/null || echo "NOT_FOUND")

    if [ "${STATUS}" = "ACTIVE" ]; then
        pass "DynamoDB table ${table} is ACTIVE"
    else
        fail "DynamoDB table ${table} status: ${STATUS}"
    fi
done

echo ""

# ─── 4. Step Functions ───────────────────────────────────────────────────────
echo "4. Step Functions workflow"

SM_ARN=$(aws cloudformation describe-stacks \
    --stack-name "${ENV_PREFIX}-compute" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
    --output text 2>/dev/null || echo "")

if [ -z "${SM_ARN}" ]; then
    fail "Could not retrieve State Machine ARN from compute stack"
else
    pass "State Machine ARN retrieved: ${SM_ARN}"

    # Start a test execution and immediately stop it
    EXEC_ARN=$(aws stepfunctions start-execution \
        --state-machine-arn "${SM_ARN}" \
        --name "smoke-test-$(date +%s)" \
        --input '{"smoke_test": true, "user_id": "smoke-user", "request_type": "analyze"}' \
        --region "${REGION}" \
        --query 'executionArn' \
        --output text 2>/dev/null || echo "")

    if [ -n "${EXEC_ARN}" ]; then
        pass "Step Functions execution started"
        # Stop the test execution immediately
        aws stepfunctions stop-execution \
            --execution-arn "${EXEC_ARN}" \
            --cause "smoke-test-cleanup" \
            --region "${REGION}" > /dev/null 2>&1 || true
        info "Test execution stopped (cleanup)"
    else
        fail "Could not start Step Functions execution"
    fi
fi

echo ""

# ─── 5. CloudWatch Alarms ────────────────────────────────────────────────────
echo "5. CloudWatch alarms"

ALARM_COUNT=$(aws cloudwatch describe-alarms \
    --alarm-name-prefix "${ENV_PREFIX}" \
    --region "${REGION}" \
    --query 'length(MetricAlarms)' \
    --output text 2>/dev/null || echo "0")

if [ "${ALARM_COUNT}" -gt 0 ]; then
    pass "CloudWatch alarms configured (${ALARM_COUNT} alarms)"

    # Check for any alarms in ALARM state
    ALARMING=$(aws cloudwatch describe-alarms \
        --alarm-name-prefix "${ENV_PREFIX}" \
        --state-value ALARM \
        --region "${REGION}" \
        --query 'length(MetricAlarms)' \
        --output text 2>/dev/null || echo "0")

    if [ "${ALARMING}" -gt 0 ]; then
        fail "${ALARMING} alarm(s) currently in ALARM state - investigate before proceeding"
    else
        pass "No alarms currently firing"
    fi
else
    fail "No CloudWatch alarms found for ${ENV_PREFIX}"
fi

echo ""

# ─── Summary ─────────────────────────────────────────────────────────────────
echo "============================================"
if [ "${FAILURES}" -eq 0 ]; then
    echo -e "${GREEN}✓ All smoke tests passed${NC}"
    exit 0
else
    echo -e "${RED}✗ ${FAILURES} smoke test(s) failed${NC}"
    echo "Review failures above before proceeding."
    exit 1
fi
