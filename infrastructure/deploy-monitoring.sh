#!/bin/bash

# Deploy CloudWatch Monitoring and Alerting Stack
# This script deploys the monitoring stack with CloudWatch alarms and SNS topics

set -e

# Configuration
STACK_NAME="multi-agent-advisory-monitoring"
TEMPLATE_FILE="infrastructure/monitoring-stack.yaml"
REGION="${AWS_REGION:-us-east-1}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"

echo "Deploying monitoring stack..."
echo "Stack Name: $STACK_NAME"
echo "Environment: $ENVIRONMENT"
echo "Region: $REGION"
echo "Admin Email: $ADMIN_EMAIL"

# Deploy the stack
aws cloudformation deploy \
  --template-file "$TEMPLATE_FILE" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --parameter-overrides \
    Environment="$ENVIRONMENT" \
    AdminEmail="$ADMIN_EMAIL" \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset

echo "Monitoring stack deployment complete!"

# Get stack outputs
echo ""
echo "Stack Outputs:"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
  --output table

echo ""
echo "Note: Check your email for SNS subscription confirmation"
