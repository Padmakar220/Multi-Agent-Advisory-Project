# AWS Setup Guide

This guide covers the AWS-specific setup required for the Multi-Agent Advisory AI System.

## AWS Account Prerequisites

### 1. Enable Amazon Bedrock Model Access

1. Sign in to the AWS Console
2. Navigate to **Amazon Bedrock**
3. Click on **Model access** in the left sidebar
4. Click **Manage model access**
5. Find **Anthropic** → **Claude 3.5 Sonnet**
6. Check the box next to the model
7. Click **Request model access**
8. Wait for approval (usually instant for Claude models)

### 2. Configure AWS CLI

```bash
# Install AWS CLI if not already installed
pip install awscli

# Configure credentials
aws configure

# Verify configuration
aws sts get-caller-identity
```

Enter the following when prompted:
- **AWS Access Key ID**: Your IAM user access key
- **AWS Secret Access Key**: Your IAM user secret key
- **Default region name**: us-east-1 (or your preferred region)
- **Default output format**: json

### 3. Required IAM Permissions

Your IAM user or role needs the following permissions:

#### Bedrock Permissions
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:GetFoundationModel",
        "bedrock:ListFoundationModels"
      ],
      "Resource": "*"
    }
  ]
}
```

#### Lambda Permissions
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:CreateFunction",
        "lambda:UpdateFunctionCode",
        "lambda:UpdateFunctionConfiguration",
        "lambda:InvokeFunction",
        "lambda:GetFunction",
        "lambda:ListFunctions"
      ],
      "Resource": "*"
    }
  ]
}
```

#### DynamoDB Permissions
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:CreateTable",
        "dynamodb:DescribeTable",
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem"
      ],
      "Resource": "*"
    }
  ]
}
```

#### OpenSearch Serverless Permissions
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "aoss:CreateCollection",
        "aoss:DeleteCollection",
        "aoss:UpdateCollection",
        "aoss:BatchGetCollection",
        "aoss:APIAccessAll"
      ],
      "Resource": "*"
    }
  ]
}
```

#### Step Functions Permissions
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "states:CreateStateMachine",
        "states:UpdateStateMachine",
        "states:StartExecution",
        "states:DescribeExecution",
        "states:StopExecution"
      ],
      "Resource": "*"
    }
  ]
}
```

### 4. Service Quotas

Verify you have sufficient service quotas:

```bash
# Check Lambda concurrent executions quota
aws service-quotas get-service-quota \
  --service-code lambda \
  --quota-code L-B99A9384

# Check DynamoDB table quota
aws service-quotas get-service-quota \
  --service-code dynamodb \
  --quota-code L-F98FE922

# Request quota increase if needed
aws service-quotas request-service-quota-increase \
  --service-code lambda \
  --quota-code L-B99A9384 \
  --desired-value 1000
```

### 5. Region Availability

Ensure the following services are available in your chosen region:
- Amazon Bedrock (with Claude 3.5 Sonnet)
- AWS Lambda
- Amazon DynamoDB
- Amazon OpenSearch Serverless
- AWS Step Functions
- Amazon API Gateway
- Amazon Cognito

**Recommended Regions:**
- us-east-1 (N. Virginia)
- us-west-2 (Oregon)
- eu-west-1 (Ireland)

### 6. Cost Estimation

Approximate monthly costs for development environment:

| Service | Usage | Estimated Cost |
|---------|-------|----------------|
| Bedrock (Claude 3.5 Sonnet) | 1M input tokens, 100K output tokens | $3.00 - $15.00 |
| Lambda | 100K invocations, 1GB memory | $0.20 - $2.00 |
| DynamoDB | On-demand, 1M reads, 100K writes | $1.25 - $2.50 |
| OpenSearch Serverless | 1 OCU | $700/month |
| Step Functions | 10K state transitions | $0.25 |
| API Gateway | 100K requests | $0.35 |
| **Total** | | **~$705 - $720/month** |

**Note:** OpenSearch Serverless is the primary cost driver. Consider using standard OpenSearch for development to reduce costs.

### 7. Security Best Practices

1. **Use IAM Roles for Lambda Functions**
   - Never hardcode credentials
   - Use least-privilege IAM policies
   - Enable CloudTrail for audit logging

2. **Enable Encryption**
   - Use KMS for DynamoDB encryption
   - Enable S3 bucket encryption
   - Use TLS 1.3 for all communications

3. **Network Security**
   - Deploy Lambda functions in VPC
   - Use VPC endpoints for AWS services
   - Configure security groups with minimal access

4. **Monitoring and Alerts**
   - Enable CloudWatch Logs
   - Set up CloudWatch Alarms
   - Configure SNS for critical alerts

### 8. Testing AWS Setup

Run the following commands to verify your AWS setup:

```bash
# Test Bedrock access
aws bedrock list-foundation-models --region us-east-1

# Test Lambda permissions
aws lambda list-functions --region us-east-1

# Test DynamoDB permissions
aws dynamodb list-tables --region us-east-1

# Test Step Functions permissions
aws stepfunctions list-state-machines --region us-east-1
```

### 9. Local Development with LocalStack

For local development without AWS costs:

```bash
# Install LocalStack
pip install localstack

# Start LocalStack
localstack start

# Configure AWS CLI for LocalStack
export AWS_ENDPOINT_URL=http://localhost:4566
```

## Troubleshooting

### Bedrock Access Denied

**Error:** `AccessDeniedException: User is not authorized to perform: bedrock:InvokeModel`

**Solution:**
1. Verify model access is enabled in Bedrock console
2. Check IAM permissions include `bedrock:InvokeModel`
3. Ensure you're using the correct region

### Lambda Timeout

**Error:** `Task timed out after 3.00 seconds`

**Solution:**
1. Increase Lambda timeout in configuration
2. Optimize code for faster execution
3. Use provisioned concurrency for warm starts

### DynamoDB Throttling

**Error:** `ProvisionedThroughputExceededException`

**Solution:**
1. Switch to on-demand billing mode
2. Implement exponential backoff retry logic
3. Use batch operations where possible

## Next Steps

- Review [Setup Guide](SETUP.md) for local development
- Deploy infrastructure using CloudFormation templates
- Run smoke tests to verify deployment
- Monitor CloudWatch metrics and logs
