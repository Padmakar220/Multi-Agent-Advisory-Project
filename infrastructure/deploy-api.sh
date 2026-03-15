#!/bin/bash

# Deploy API layer infrastructure for Multi-Agent Advisory AI System
# This script deploys API Gateway, Cognito, and authentication

set -e

# Configuration
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-advisory}"
STACK_NAME="${ENVIRONMENT_NAME}-api-stack"
TEMPLATE_FILE="infrastructure/api-stack.yaml"
REGION="${AWS_REGION:-us-east-1}"

echo "========================================="
echo "API Stack Deployment"
echo "========================================="
echo "Environment: $ENVIRONMENT_NAME"
echo "Stack Name: $STACK_NAME"
echo "Region: $REGION"
echo "========================================="

# Get IAM role ARNs from IAM stack
echo "Retrieving IAM role ARNs from IAM stack..."
IAM_STACK_NAME="${ENVIRONMENT_NAME}-iam-stack"

API_EXECUTION_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name "$IAM_STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiExecutionRoleArn'].OutputValue" \
  --output text)

if [ -z "$API_EXECUTION_ROLE_ARN" ]; then
  echo "ERROR: Could not retrieve API Execution Role ARN from IAM stack"
  echo "Please ensure the IAM stack is deployed first"
  exit 1
fi

echo "Using ApiExecutionRole: $API_EXECUTION_ROLE_ARN"

# Get Step Functions State Machine ARN from compute stack
echo "Retrieving Step Functions State Machine ARN from compute stack..."
COMPUTE_STACK_NAME="${ENVIRONMENT_NAME}-compute-stack"

STEPFUNCTIONS_STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name "$COMPUTE_STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='PortfolioRebalancingStateMachineArn'].OutputValue" \
  --output text)

if [ -z "$STEPFUNCTIONS_STATE_MACHINE_ARN" ]; then
  echo "ERROR: Could not retrieve Step Functions State Machine ARN from compute stack"
  echo "Please ensure the compute stack is deployed first"
  exit 1
fi

echo "Using Step Functions State Machine: $STEPFUNCTIONS_STATE_MACHINE_ARN"

# Deploy the stack
echo ""
echo "Deploying API stack..."
aws cloudformation deploy \
  --template-file "$TEMPLATE_FILE" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --parameter-overrides \
    Environment="$ENVIRONMENT_NAME" \
    StepFunctionsStateMachineArn="$STEPFUNCTIONS_STATE_MACHINE_ARN" \
    ApiExecutionRoleArn="$API_EXECUTION_ROLE_ARN" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

if [ $? -eq 0 ]; then
  echo ""
  echo "========================================="
  echo "API Stack Deployment Successful"
  echo "========================================="
  
  # Get outputs
  echo ""
  echo "Stack Outputs:"
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[*].[OutputKey,OutputValue]" \
    --output table
  
  echo ""
  echo "Next steps:"
  echo "1. Test API endpoints with valid Cognito tokens"
  echo "2. Create test users in Cognito User Pool"
  echo "3. Test workflow initiation via API"
  echo "4. Monitor CloudWatch logs for errors"
else
  echo ""
  echo "ERROR: API stack deployment failed"
  exit 1
fi
