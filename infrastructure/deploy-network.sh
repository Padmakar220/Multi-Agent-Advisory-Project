#!/bin/bash

# Deploy Network Stack for Multi-Agent Advisory AI System
# This script deploys the VPC, subnets, NAT gateways, security groups, and VPC endpoints

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT=${1:-advisory}
REGION=${AWS_REGION:-us-east-1}
STACK_NAME="${ENVIRONMENT}-network"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Network Stack Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Environment: ${ENVIRONMENT}"
echo "Region: ${REGION}"
echo "Stack Name: ${STACK_NAME}"
echo ""

# Validate template
echo -e "${YELLOW}Validating CloudFormation template...${NC}"
aws cloudformation validate-template \
    --template-body file://network-stack.yaml \
    --region ${REGION} > /dev/null

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Template validation successful${NC}"
else
    echo -e "${RED}✗ Template validation failed${NC}"
    exit 1
fi

# Check if stack exists
STACK_EXISTS=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} 2>&1 || true)

if echo "${STACK_EXISTS}" | grep -q "does not exist"; then
    echo -e "${YELLOW}Creating new stack...${NC}"
    OPERATION="create-stack"
else
    echo -e "${YELLOW}Updating existing stack...${NC}"
    OPERATION="update-stack"
fi

# Deploy stack
echo -e "${YELLOW}Deploying network stack...${NC}"
aws cloudformation ${OPERATION} \
    --stack-name ${STACK_NAME} \
    --template-body file://network-stack.yaml \
    --parameters ParameterKey=EnvironmentName,ParameterValue=${ENVIRONMENT} \
    --region ${REGION} \
    --capabilities CAPABILITY_NAMED_IAM \
    --tags Key=Project,Value=MultiAgentAdvisory Key=Environment,Value=${ENVIRONMENT}

if [ $? -ne 0 ]; then
    if echo "${OPERATION}" | grep -q "update" && aws cloudformation describe-stacks --stack-name ${STACK_NAME} --region ${REGION} 2>&1 | grep -q "No updates are to be performed"; then
        echo -e "${GREEN}✓ No updates needed - stack is already up to date${NC}"
        exit 0
    else
        echo -e "${RED}✗ Stack deployment failed${NC}"
        exit 1
    fi
fi

# Wait for stack operation to complete
echo -e "${YELLOW}Waiting for stack operation to complete...${NC}"
if echo "${OPERATION}" | grep -q "create"; then
    aws cloudformation wait stack-create-complete \
        --stack-name ${STACK_NAME} \
        --region ${REGION}
else
    aws cloudformation wait stack-update-complete \
        --stack-name ${STACK_NAME} \
        --region ${REGION}
fi

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Stack deployment completed successfully${NC}"
else
    echo -e "${RED}✗ Stack deployment failed${NC}"
    exit 1
fi

# Display outputs
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Stack Outputs${NC}"
echo -e "${GREEN}========================================${NC}"
aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
    --output table

echo ""
echo -e "${GREEN}✓ Network stack deployment complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Deploy data stack: ./deploy-data.sh ${ENVIRONMENT}"
echo "  2. Deploy compute stack: ./deploy-compute.sh ${ENVIRONMENT}"
echo "  3. Deploy AI stack: ./deploy-ai.sh ${ENVIRONMENT}"
