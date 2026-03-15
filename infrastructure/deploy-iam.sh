#!/bin/bash

# Deploy IAM Stack for Multi-Agent Advisory AI System
# This script deploys IAM roles and policies for agent execution and Step Functions orchestration

set -e

# Configuration
STACK_NAME="advisory-iam-stack"
TEMPLATE_FILE="iam-stack.yaml"
REGION="${AWS_REGION:-us-east-1}"
ENVIRONMENT="${ENVIRONMENT:-advisory}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if template file exists
if [ ! -f "$TEMPLATE_FILE" ]; then
    print_error "Template file $TEMPLATE_FILE not found!"
    exit 1
fi

# Validate CloudFormation template
print_info "Validating CloudFormation template..."
if aws cloudformation validate-template \
    --template-body file://$TEMPLATE_FILE \
    --region $REGION > /dev/null 2>&1; then
    print_info "Template validation successful"
else
    print_error "Template validation failed"
    exit 1
fi

# Check if stack exists
print_info "Checking if stack $STACK_NAME exists..."
if aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION > /dev/null 2>&1; then
    STACK_EXISTS=true
    print_info "Stack exists. Will update."
else
    STACK_EXISTS=false
    print_info "Stack does not exist. Will create."
fi

# Prepare parameters
PARAMETERS="ParameterKey=EnvironmentName,ParameterValue=$ENVIRONMENT"

# Add KMS key ARN if provided
if [ ! -z "$KMS_KEY_ARN" ]; then
    PARAMETERS="$PARAMETERS ParameterKey=KMSKeyArn,ParameterValue=$KMS_KEY_ARN"
fi

# Deploy stack
if [ "$STACK_EXISTS" = true ]; then
    print_info "Updating stack $STACK_NAME..."
    
    # Update stack
    UPDATE_OUTPUT=$(aws cloudformation update-stack \
        --stack-name $STACK_NAME \
        --template-body file://$TEMPLATE_FILE \
        --parameters $PARAMETERS \
        --capabilities CAPABILITY_NAMED_IAM \
        --region $REGION 2>&1) || true
    
    # Check if update was needed
    if echo "$UPDATE_OUTPUT" | grep -q "No updates are to be performed"; then
        print_warning "No updates needed for stack $STACK_NAME"
        exit 0
    elif echo "$UPDATE_OUTPUT" | grep -q "StackId"; then
        print_info "Stack update initiated"
        OPERATION="update"
    else
        print_error "Stack update failed: $UPDATE_OUTPUT"
        exit 1
    fi
else
    print_info "Creating stack $STACK_NAME..."
    
    # Create stack
    aws cloudformation create-stack \
        --stack-name $STACK_NAME \
        --template-body file://$TEMPLATE_FILE \
        --parameters $PARAMETERS \
        --capabilities CAPABILITY_NAMED_IAM \
        --region $REGION \
        --tags Key=Environment,Value=$ENVIRONMENT Key=ManagedBy,Value=CloudFormation
    
    OPERATION="create"
fi

# Wait for stack operation to complete
print_info "Waiting for stack $OPERATION to complete..."
if [ "$OPERATION" = "create" ]; then
    aws cloudformation wait stack-create-complete \
        --stack-name $STACK_NAME \
        --region $REGION
elif [ "$OPERATION" = "update" ]; then
    aws cloudformation wait stack-update-complete \
        --stack-name $STACK_NAME \
        --region $REGION
fi

# Check stack status
STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].StackStatus' \
    --output text)

if [[ "$STACK_STATUS" == *"COMPLETE"* ]]; then
    print_info "Stack $OPERATION completed successfully!"
    
    # Display outputs
    print_info "Stack Outputs:"
    aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
        --output table
    
    # Save outputs to file
    OUTPUT_FILE="iam-stack-outputs.json"
    aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs' \
        --output json > $OUTPUT_FILE
    print_info "Outputs saved to $OUTPUT_FILE"
    
else
    print_error "Stack $OPERATION failed with status: $STACK_STATUS"
    
    # Display stack events for debugging
    print_error "Recent stack events:"
    aws cloudformation describe-stack-events \
        --stack-name $STACK_NAME \
        --region $REGION \
        --max-items 10 \
        --query 'StackEvents[*].[Timestamp,ResourceStatus,ResourceType,LogicalResourceId,ResourceStatusReason]' \
        --output table
    
    exit 1
fi

print_info "IAM stack deployment complete!"
print_info ""
print_info "Next steps:"
print_info "1. Review the IAM roles and policies in the AWS Console"
print_info "2. Note the AgentExecutionRoleArn and StepFunctionsExecutionRoleArn from outputs"
print_info "3. Use these role ARNs when deploying Lambda functions and Step Functions"
print_info "4. Proceed with deploying the data stack (DynamoDB, OpenSearch)"
