# Infrastructure as Code

This directory contains CloudFormation/CDK templates for deploying the Multi-Agent Advisory AI System.

## Stack Organization

- **network-stack.yaml**: VPC, subnets, security groups, VPC endpoints
- **iam-stack.yaml**: IAM roles and policies for agents and Step Functions
- **data-stack.yaml**: DynamoDB tables, OpenSearch Serverless, S3 buckets
- **compute-stack.yaml**: Lambda functions and configurations
- **ai-stack.yaml**: Bedrock agent configurations
- **api-stack.yaml**: API Gateway, Cognito User Pool
- **monitoring-stack.yaml**: CloudWatch dashboards, alarms, SNS topics

## Deployment Order

1. network-stack (VPC infrastructure)
2. iam-stack (IAM roles and policies)
3. data-stack (DynamoDB, OpenSearch)
4. compute-stack (Lambda functions)
5. ai-stack (Bedrock agents)
6. api-stack (API Gateway, Cognito)
7. monitoring-stack (CloudWatch, SNS)

## Prerequisites

- AWS CLI configured
- Appropriate IAM permissions
- Python 3.11 runtime available in target region
- Bedrock model access enabled

## Deployment Commands

```bash
# Deploy all stacks
./scripts/deploy.sh

# Deploy specific stack
aws cloudformation deploy --template-file network-stack.yaml --stack-name advisory-network

# Delete all stacks
./scripts/cleanup.sh
```
