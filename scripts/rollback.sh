#!/bin/bash
# Rollback deployment for Multi-Agent Advisory AI System
# Usage: ./scripts/rollback.sh --env dev [--region us-east-1] [--stack STACK_NAME]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ENVIRONMENT=""
REGION="${AWS_REGION:-us-east-1}"
TARGET_STACK=""  # If set, only roll back this specific stack

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --env)    ENVIRONMENT="$2"; shift ;;
        --region) REGION="$2"; shift ;;
        --stack)  TARGET_STACK="$2"; shift ;;
        *) echo -e "${RED}Unknown parameter: $1${NC}"; exit 1 ;;
    esac
    shift
done

if [ -z "${ENVIRONMENT}" ]; then
    echo -e "${RED}Error: --env is required${NC}"; exit 1
fi

ENV_PREFIX="advisory-${ENVIRONMENT}"

# Stacks in reverse dependency order for teardown
ALL_STACKS=(
    "${ENV_PREFIX}-monitoring"
    "${ENV_PREFIX}-api"
    "${ENV_PREFIX}-compute"
    "${ENV_PREFIX}-layers"
    "${ENV_PREFIX}-data"
    "${ENV_PREFIX}-iam"
    "${ENV_PREFIX}-network"
)

rollback_stack() {
    local stack_name="$1"

    local status
    status=$(aws cloudformation describe-stacks \
        --stack-name "${stack_name}" \
        --region "${REGION}" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "DOES_NOT_EXIST")

    if [ "${status}" = "DOES_NOT_EXIST" ]; then
        echo -e "${YELLOW}⚠ ${stack_name} does not exist, skipping${NC}"
        return
    fi

    # If stack is in a ROLLBACK_COMPLETE state it must be deleted before re-deploy
    if [[ "${status}" == *"ROLLBACK_COMPLETE"* ]] || [[ "${status}" == *"FAILED"* ]]; then
        echo -e "${YELLOW}Stack ${stack_name} is in ${status} - deleting...${NC}"
        aws cloudformation delete-stack \
            --stack-name "${stack_name}" \
            --region "${REGION}"
        aws cloudformation wait stack-delete-complete \
            --stack-name "${stack_name}" \
            --region "${REGION}"
        echo -e "${GREEN}✓ ${stack_name} deleted${NC}"
        return
    fi

    # For stacks in UPDATE_IN_PROGRESS, cancel the update first
    if [[ "${status}" == "UPDATE_IN_PROGRESS" ]]; then
        echo -e "${YELLOW}Cancelling in-progress update for ${stack_name}...${NC}"
        aws cloudformation cancel-update-stack \
            --stack-name "${stack_name}" \
            --region "${REGION}" || true
        aws cloudformation wait stack-rollback-complete \
            --stack-name "${stack_name}" \
            --region "${REGION}" || true
        echo -e "${GREEN}✓ ${stack_name} update cancelled${NC}"
        return
    fi

    # For stable stacks, trigger a rollback to the previous version
    echo -e "${YELLOW}Rolling back ${stack_name} (current status: ${status})...${NC}"
    aws cloudformation rollback-stack \
        --stack-name "${stack_name}" \
        --region "${REGION}" 2>/dev/null || {
        echo -e "${YELLOW}⚠ rollback-stack not supported for ${status}, no action taken${NC}"
        return
    }
    aws cloudformation wait stack-rollback-complete \
        --stack-name "${stack_name}" \
        --region "${REGION}"
    echo -e "${GREEN}✓ ${stack_name} rolled back${NC}"
}

echo -e "${RED}============================================${NC}"
echo -e "${RED}Rolling Back Deployment${NC}"
echo -e "${RED}============================================${NC}"
echo "Environment : ${ENVIRONMENT}"
echo "Region      : ${REGION}"
echo ""

if [ -n "${TARGET_STACK}" ]; then
    echo -e "${YELLOW}Rolling back single stack: ${TARGET_STACK}${NC}"
    rollback_stack "${TARGET_STACK}"
else
    echo -e "${YELLOW}Rolling back all stacks in reverse order...${NC}"
    for stack in "${ALL_STACKS[@]}"; do
        rollback_stack "${stack}"
    done
fi

echo ""
echo -e "${GREEN}✓ Rollback complete${NC}"
