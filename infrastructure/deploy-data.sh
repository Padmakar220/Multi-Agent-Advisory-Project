#!/bin/bash

# Deploy data layer infrastructure for Multi-Agent Advisory AI System
# This script deploys DynamoDB tables, OpenSearch Serverless collection, and S3 buckets

set -e

# Configuration
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-advisory}"
STACK_NAME="${ENVIRONMENT_NAME}-data-stack"
TEMPLATE_FILE="infrastructure/data-stack.yaml"
REGION="${AWS_REGION:-us-east-1}"

echo "========================================="
echo "Data Stack Deployment"
echo "========================================="
echo "Environment: $ENVIRONMENT_NAME"
echo "Stack Name: $STACK_NAME"
echo "Region: $REGION"
echo "========================================="

# Get KMS Key ID from IAM stack
echo "Retrieving KMS Key ID from IAM stack..."
KMS_KEY_ID=$(aws cloudformation describe-stacks \
  --stack-name "${ENVIRONMENT_NAME}-iam-stack" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='DynamoDBEncryptionKeyId'].OutputValue" \
  --output text)

if [ -z "$KMS_KEY_ID" ]; then
  echo "ERROR: Could not retrieve KMS Key ID from IAM stack"
  echo "Please ensure the IAM stack is deployed first"
  exit 1
fi

echo "Using KMS Key ID: $KMS_KEY_ID"

# Deploy the stack
echo ""
echo "Deploying data stack..."
aws cloudformation deploy \
  --template-file "$TEMPLATE_FILE" \
  --stack-name "$STACK_NAME" \
  --parameter-overrides \
    EnvironmentName="$ENVIRONMENT_NAME" \
    KMSKeyId="$KMS_KEY_ID" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION" \
  --no-fail-on-empty-changeset

# Check deployment status
if [ $? -eq 0 ]; then
  echo ""
  echo "========================================="
  echo "Data stack deployed successfully!"
  echo "========================================="
  
  # Display outputs
  echo ""
  echo "Stack Outputs:"
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[*].[OutputKey,OutputValue]" \
    --output table
  
  echo ""
  echo "Next steps:"
  echo "1. Verify DynamoDB tables in AWS Console"
  echo "2. Configure OpenSearch index mappings (see infrastructure/opensearch-index-setup.sh)"
  echo "3. Deploy compute stack (Lambda functions)"
else
  echo ""
  echo "ERROR: Data stack deployment failed"
  exit 1
fi
