#!/bin/bash
# Deploy all stacks for Multi-Agent Advisory AI System
# Usage: ./scripts/deploy.sh --env dev --bucket my-bucket [--region us-east-1] [--skip-package]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ─── Defaults ────────────────────────────────────────────────────────────────
ENVIRONMENT=""
BUCKET_NAME=""
REGION="${AWS_REGION:-us-east-1}"
SKIP_PACKAGE=false
DRY_RUN=false

# ─── Parse Arguments ─────────────────────────────────────────────────────────
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --env)          ENVIRONMENT="$2"; shift ;;
        --bucket)       BUCKET_NAME="$2"; shift ;;
        --region)       REGION="$2"; shift ;;
        --skip-package) SKIP_PACKAGE=true ;;
        --dry-run)      DRY_RUN=true ;;
        *) echo -e "${RED}Unknown parameter: $1${NC}"; exit 1 ;;
    esac
    shift
done

# ─── Validation ──────────────────────────────────────────────────────────────
if [ -z "${ENVIRONMENT}" ]; then
    echo -e "${RED}Error: --env is required (dev|staging|prod)${NC}"
    exit 1
fi

if [[ ! "${ENVIRONMENT}" =~ ^(dev|staging|prod)$ ]]; then
    echo -e "${RED}Error: --env must be dev, staging, or prod${NC}"
    exit 1
fi

if [ -z "${BUCKET_NAME}" ]; then
    echo -e "${RED}Error: --bucket is required${NC}"
    exit 1
fi

# ─── Pre-deployment Checks ───────────────────────────────────────────────────
preflight_checks() {
    echo -e "${YELLOW}Running pre-deployment checks...${NC}"

    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}✗ AWS CLI not found${NC}"; exit 1
    fi
    echo -e "${GREEN}✓ AWS CLI available${NC}"

    # Check AWS credentials
    if ! aws sts get-caller-identity --region "${REGION}" > /dev/null 2>&1; then
        echo -e "${RED}✗ AWS credentials not configured or invalid${NC}"; exit 1
    fi
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    echo -e "${GREEN}✓ AWS credentials valid (account: ${ACCOUNT_ID})${NC}"

    # Check S3 bucket exists
    if ! aws s3 ls "s3://${BUCKET_NAME}" --region "${REGION}" > /dev/null 2>&1; then
        echo -e "${RED}✗ S3 bucket '${BUCKET_NAME}' not accessible${NC}"; exit 1
    fi
    echo -e "${GREEN}✓ S3 bucket accessible${NC}"

    # Validate all CloudFormation templates
    echo -e "${YELLOW}Validating CloudFormation templates...${NC}"
    for template in infrastructure/*.yaml; do
        aws cloudformation validate-template \
            --template-body "file://${template}" \
            --region "${REGION}" > /dev/null
        echo -e "${GREEN}✓ $(basename "${template}")${NC}"
    done

    echo -e "${GREEN}✓ All pre-deployment checks passed${NC}"
    echo ""
}

# ─── Deploy a Single Stack ───────────────────────────────────────────────────
deploy_stack() {
    local stack_name="$1"
    local template_url="$2"
    shift 2
    local params=("$@")

    echo -e "${BLUE}Deploying stack: ${stack_name}${NC}"

    if [ "${DRY_RUN}" = true ]; then
        echo -e "${YELLOW}[DRY RUN] Would deploy ${stack_name}${NC}"
        return 0
    fi

    local param_string=""
    for param in "${params[@]}"; do
        param_string="${param_string} ParameterKey=${param%%=*},ParameterValue=${param#*=}"
    done

    aws cloudformation deploy \
        --stack-name "${stack_name}" \
        --template-url "${template_url}" \
        --parameter-overrides ${param_string} \
        --capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
        --region "${REGION}" \
        --tags Project=MultiAgentAdvisory Environment="${ENVIRONMENT}" \
        --no-fail-on-empty-changeset

    echo -e "${GREEN}✓ ${stack_name} deployed${NC}"
    echo ""
}

get_stack_output() {
    local stack_name="$1"
    local output_key="$2"
    aws cloudformation describe-stacks \
        --stack-name "${stack_name}" \
        --region "${REGION}" \
        --query "Stacks[0].Outputs[?OutputKey=='${output_key}'].OutputValue" \
        --output text 2>/dev/null || echo ""
}

# ─── Main Deployment Sequence ────────────────────────────────────────────────
TEMPLATE_BASE="https://${BUCKET_NAME}.s3.${REGION}.amazonaws.com/infrastructure"
ENV_PREFIX="advisory-${ENVIRONMENT}"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}Multi-Agent Advisory AI System Deployment${NC}"
echo -e "${GREEN}============================================${NC}"
echo "Environment : ${ENVIRONMENT}"
echo "Region      : ${REGION}"
echo "Account     : $(aws sts get-caller-identity --query Account --output text 2>/dev/null)"
echo "Bucket      : ${BUCKET_NAME}"
echo ""

preflight_checks

# Step 1: Package and upload artifacts
if [ "${SKIP_PACKAGE}" = false ]; then
    echo -e "${YELLOW}Step 1/7: Packaging Lambda functions and uploading artifacts...${NC}"
    bash scripts/package_lambdas.sh --env "${ENVIRONMENT}" --bucket "${BUCKET_NAME}"
    echo ""
else
    echo -e "${YELLOW}Step 1/7: Skipping packaging (--skip-package)${NC}"
    echo ""
fi

# Step 2: Network stack
echo -e "${YELLOW}Step 2/7: Deploying network stack...${NC}"
deploy_stack "${ENV_PREFIX}-network" \
    "${TEMPLATE_BASE}/network-stack.yaml" \
    "EnvironmentName=${ENV_PREFIX}"

# Step 3: IAM stack
echo -e "${YELLOW}Step 3/7: Deploying IAM stack...${NC}"
deploy_stack "${ENV_PREFIX}-iam" \
    "${TEMPLATE_BASE}/iam-stack.yaml" \
    "EnvironmentName=${ENV_PREFIX}"

KMS_KEY_ID=$(get_stack_output "${ENV_PREFIX}-iam" "KMSKeyId")
AGENT_ROLE_ARN=$(get_stack_output "${ENV_PREFIX}-iam" "AgentExecutionRoleArn")
SF_ROLE_ARN=$(get_stack_output "${ENV_PREFIX}-iam" "StepFunctionsExecutionRoleArn")

# Step 4: Data stack
echo -e "${YELLOW}Step 4/7: Deploying data stack...${NC}"
deploy_stack "${ENV_PREFIX}-data" \
    "${TEMPLATE_BASE}/data-stack.yaml" \
    "EnvironmentName=${ENV_PREFIX}" \
    "KMSKeyId=${KMS_KEY_ID}"

# Step 5: Lambda layers
echo -e "${YELLOW}Step 5/7: Deploying Lambda layers...${NC}"
deploy_stack "${ENV_PREFIX}-layers" \
    "${TEMPLATE_BASE}/lambda-layers.yaml" \
    "Environment=${ENVIRONMENT}" \
    "LayersBucketName=${BUCKET_NAME}"

# Step 6: Compute stack
echo -e "${YELLOW}Step 6/7: Deploying compute stack...${NC}"
deploy_stack "${ENV_PREFIX}-compute" \
    "${TEMPLATE_BASE}/compute-stack.yaml" \
    "Environment=${ENVIRONMENT}" \
    "AgentExecutionRoleArn=${AGENT_ROLE_ARN}" \
    "StepFunctionsExecutionRoleArn=${SF_ROLE_ARN}"

# Step 7: API + Monitoring stacks (parallel-safe, both depend only on compute)
echo -e "${YELLOW}Step 7/7: Deploying API and monitoring stacks...${NC}"
deploy_stack "${ENV_PREFIX}-api" \
    "${TEMPLATE_BASE}/api-stack.yaml" \
    "Environment=${ENVIRONMENT}"

deploy_stack "${ENV_PREFIX}-monitoring" \
    "${TEMPLATE_BASE}/monitoring-stack.yaml" \
    "Environment=${ENVIRONMENT}"

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}✓ Deployment complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Stack outputs:"
API_ENDPOINT=$(get_stack_output "${ENV_PREFIX}-api" "ApiEndpoint")
SM_ARN=$(get_stack_output "${ENV_PREFIX}-compute" "StateMachineArn")
echo "  API Endpoint    : ${API_ENDPOINT}"
echo "  State Machine   : ${SM_ARN}"
echo ""
echo "Run smoke tests:"
echo "  bash scripts/smoke_tests.sh --env ${ENVIRONMENT} --api-endpoint ${API_ENDPOINT}"
