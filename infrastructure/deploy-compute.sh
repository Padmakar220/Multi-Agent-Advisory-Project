#!/bin/bash

# Deploy compute layer infrastructure for Multi-Agent Advisory AI System
# This script deploys Lambda functions and Step Functions state machine

set -e

# Configuration
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-advisory}"
STACK_NAME="${ENVIRONMENT_NAME}-compute-stack"
TEMPLATE_FILE="infrastructure/compute-stack.yaml"
REGION="${AWS_REGION:-us-east-1}"

echo "========================================="
echo "Compute Stack Deployment"
echo "========================================="
echo "Environment: $ENVIRONMENT_NAME"
echo "Stack Name: $STACK_NAME"
echo "Region: $REGION"
echo "========================================="

# Get IAM role ARNs from IAM stack
echo "Retrieving IAM role ARNs from IAM stack..."
IAM_STACK_NAME="${ENVIRONMENT_NAME}-iam-stack"

AGENT_EXECUTION_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name "$IAM_STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='AgentExecutionRoleArn'].OutputValue" \
  --output text)

STEPFUNCTIONS_EXECUTION_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name "$IAM_STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='StepFunctionsExecutionRoleArn'].OutputValue" \
  --output text)

if [ -z "$AGENT_EXECUTION_ROLE_ARN" ] || [ -z "$STEPFUNCTIONS_EXECUTION_ROLE_ARN" ]; then
  echo "ERROR: Could not retrieve IAM role ARNs from IAM stack"
  echo "Please ensure the IAM stack is deployed first"
  exit 1
fi

echo "Using AgentExecutionRole: $AGENT_EXECUTION_ROLE_ARN"
echo "Using StepFunctionsExecutionRole: $STEPFUNCTIONS_EXECUTION_ROLE_ARN"

# Deploy the stack
echo ""
echo "Deploying compute stack..."
aws cloudformation deploy \
  --template-file "$TEMPLATE_FILE" \
  --stack-name "$STACK_NAME" \
  --parameter-overrides \
    Environment="$ENVIRONMENT_NAME" \
    AgentExecutionRoleArn="$AGENT_EXECUTION_ROLE_ARN" \
    StepFunctionsExecutionRoleArn="$STEPFUNCTIONS_EXECUTION_ROLE_ARN" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION" \
  --no-fail-on-empty-changeset

# Check deployment status
if [ $? -eq 0 ]; then
  echo ""
  echo "========================================="
  echo "Compute stack deployed successfully!"
  echo "========================================="
  
  # Display outputs
  echo ""
  echo "Stack Outputs:"
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[*].[OutputKey,OutputValue]" \
    --output table
  
  # Get state machine ARN
  STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
    --output text)
  
  echo ""
  echo "State Machine ARN: $STATE_MACHINE_ARN"
  
  echo ""
  echo "Next steps:"
  echo "1. Verify Step Functions state machine in AWS Console"
  echo "2. Deploy API Gateway stack"
  echo "3. Test workflow execution"
else
  echo ""
  echo "ERROR: Compute stack deployment failed"
  exit 1
fi
