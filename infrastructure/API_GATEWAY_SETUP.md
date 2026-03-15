# API Gateway and Authentication Setup

## Overview

This document describes the API Gateway and authentication setup for the Multi-Agent Advisory AI System. The API provides REST endpoints for portfolio management operations with Cognito-based authentication and rate limiting.

## Architecture

### Components

1. **API Gateway REST API**: Provides HTTP endpoints for client applications
2. **Cognito User Pool**: Manages user authentication and authorization
3. **Cognito Authorizer**: Validates JWT tokens from Cognito
4. **Step Functions Integration**: Initiates workflows via API
5. **Lambda Integration**: Handles approval responses
6. **Usage Plans**: Implements rate limiting and API key management

### API Endpoints

#### 1. POST /rebalance
Initiates a portfolio rebalancing workflow.

**Authentication**: Cognito User Pool
**Request Body**:
```json
{
  "user_id": "string",
  "portfolio_id": "string",
  "request_type": "rebalance",
  "parameters": {
    "include_tax_optimization": true
  }
}
```

**Response**:
```json
{
  "execution_arn": "arn:aws:states:region:account:execution:...",
  "execution_name": "string",
  "status": "RUNNING",
  "start_time": "2024-01-15T14:30:00Z"
}
```

**Requirements**: 1.1, 10.1

#### 2. POST /analyze
Initiates a portfolio analysis workflow.

**Authentication**: Cognito User Pool
**Request Body**:
```json
{
  "user_id": "string",
  "portfolio_id": "string",
  "request_type": "analyze",
  "parameters": {
    "analysis_type": "performance"
  }
}
```

**Response**: Same as /rebalance

**Requirements**: 1.1, 10.1

#### 3. POST /optimize-tax
Initiates a tax optimization workflow.

**Authentication**: Cognito User Pool
**Request Body**:
```json
{
  "user_id": "string",
  "portfolio_id": "string",
  "request_type": "tax_optimize",
  "parameters": {
    "tax_year": 2024
  }
}
```

**Response**: Same as /rebalance

**Requirements**: 1.1, 10.1

#### 4. POST /approval
Submits user approval or rejection of a trade plan.

**Authentication**: Cognito User Pool
**Request Body**:
```json
{
  "task_token": "string",
  "approval_status": "approved|rejected|cancelled",
  "feedback": "optional user feedback"
}
```

**Response**:
```json
{
  "status": "success",
  "message": "Approval processed"
}
```

**Requirements**: 5.3, 5.4

## Authentication

### Cognito User Pool Configuration

The Cognito User Pool is configured with:

- **Password Policy**: 
  - Minimum 12 characters
  - Uppercase letters required
  - Lowercase letters required
  - Numbers required
  - Symbols required

- **MFA**: Optional (SOFTWARE_TOKEN_MFA)

- **Account Recovery**: Email verification

- **User Attributes**:
  - Email (required, immutable)
  - Name (required, mutable)

### Token Validation

All API requests must include a valid Cognito JWT token in the Authorization header:

```
Authorization: Bearer <cognito_jwt_token>
```

The Cognito Authorizer validates the token and extracts user claims, which are passed to the Lambda integration.

### Authorization Scopes

The system supports the following scopes:
- `portfolio:read` - Read portfolio data
- `portfolio:write` - Modify portfolio data
- `portfolio:execute` - Execute trades

## Request Validation

### JSON Schema Validation

All requests are validated against JSON schemas:

1. **RebalanceRequest**: Validates rebalance endpoint requests
2. **AnalysisRequest**: Validates analysis endpoint requests
3. **TaxOptimizeRequest**: Validates tax optimization requests
4. **ApprovalResponse**: Validates approval endpoint requests

### Required Fields

All endpoints require:
- `user_id`: User identifier
- `portfolio_id`: Portfolio identifier

### Request Validator

API Gateway Request Validator is enabled to:
- Validate request body against schema
- Validate request parameters
- Return 400 Bad Request for invalid requests

## Rate Limiting

### Usage Plan Configuration

- **Rate Limit**: 100 requests per second per user
- **Burst Limit**: 200 requests
- **Daily Quota**: 1,000,000 requests per day

### API Keys

API keys are provided for external integrations:
- Each key is associated with a usage plan
- Keys can be enabled/disabled
- Keys are tracked for monitoring

## CORS Configuration

CORS is enabled for web client access:
- **Allowed Origins**: Configured per environment
- **Allowed Methods**: POST
- **Allowed Headers**: Content-Type, Authorization
- **Max Age**: 3600 seconds

## Integration with Step Functions

### Request Flow

1. Client sends authenticated request to API endpoint
2. API Gateway validates request and token
3. API Gateway invokes Step Functions StartExecution
4. Step Functions returns execution ARN
5. API Gateway returns execution ARN to client
6. Client can poll execution status using execution ARN

### Request Mapping

API Gateway maps HTTP request to Step Functions input:

```
{
  "stateMachineArn": "arn:aws:states:region:account:stateMachine:...",
  "input": {
    "user_id": "...",
    "portfolio_id": "...",
    "request_type": "...",
    "parameters": {...}
  }
}
```

## Integration with Lambda

### Approval Handler Integration

The /approval endpoint integrates with the approval-handler Lambda function:

1. Client sends approval decision with task token
2. API Gateway invokes approval-handler Lambda
3. Lambda validates payload and extracts task token
4. Lambda sends result to Step Functions using task token
5. Step Functions resumes workflow with approval status

## Deployment

### Prerequisites

- AWS CLI configured with appropriate credentials
- IAM stack deployed (for API Execution Role)
- Compute stack deployed (for Step Functions State Machine)

### Deployment Steps

1. Deploy IAM stack:
   ```bash
   ./infrastructure/deploy-iam.sh
   ```

2. Deploy compute stack:
   ```bash
   ./infrastructure/deploy-compute.sh
   ```

3. Deploy API stack:
   ```bash
   ./infrastructure/deploy-api.sh
   ```

### Environment Variables

- `ENVIRONMENT_NAME`: Environment name (default: advisory)
- `AWS_REGION`: AWS region (default: us-east-1)

## Testing

### Create Test User

```bash
aws cognito-idp admin-create-user \
  --user-pool-id <user-pool-id> \
  --username testuser \
  --temporary-password TempPassword123! \
  --region us-east-1
```

### Set Permanent Password

```bash
aws cognito-idp admin-set-user-password \
  --user-pool-id <user-pool-id> \
  --username testuser \
  --password Password123! \
  --permanent \
  --region us-east-1
```

### Authenticate

```bash
aws cognito-idp admin-initiate-auth \
  --user-pool-id <user-pool-id> \
  --client-id <client-id> \
  --auth-flow ADMIN_NO_SRP_AUTH \
  --auth-parameters USERNAME=testuser,PASSWORD=Password123! \
  --region us-east-1
```

### Test API Endpoint

```bash
curl -X POST https://<api-id>.execute-api.us-east-1.amazonaws.com/dev/rebalance \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "portfolio_id": "portfolio_456",
    "request_type": "rebalance"
  }'
```

## Monitoring

### CloudWatch Logs

API Gateway logs are sent to CloudWatch:
- Log Group: `/aws/apigateway/portfolio-management-api-{environment}`
- Log Level: INFO (configurable)

### CloudWatch Metrics

Custom metrics are emitted:
- `ApiRequestCount`: Number of API requests
- `ApiErrorCount`: Number of API errors
- `ApiLatency`: API response latency

### Alarms

Alarms are configured for:
- High error rate (> 5% of requests)
- High latency (> 5 seconds)
- Rate limit exceeded

## Security Considerations

### TLS/SSL

- All API communications use TLS 1.3
- Certificate is managed by AWS

### Data Encryption

- Request/response bodies are encrypted in transit
- Sensitive data (tokens, user IDs) are not logged

### IAM Authorization

- API Gateway assumes API Execution Role
- Role has minimal permissions (StartExecution, InvokeLambda)
- Resource-level permissions restrict access to specific state machines

### Token Security

- Tokens are short-lived (1 hour default)
- Tokens are validated on every request
- Expired tokens are rejected with 401 Unauthorized

## Troubleshooting

### 401 Unauthorized

**Cause**: Invalid or missing Authorization header

**Solution**:
1. Verify token is valid and not expired
2. Verify Authorization header format: `Bearer <token>`
3. Check Cognito User Pool configuration

### 400 Bad Request

**Cause**: Invalid request body or missing required fields

**Solution**:
1. Verify request body matches JSON schema
2. Verify all required fields are present
3. Check field types and values

### 429 Too Many Requests

**Cause**: Rate limit exceeded

**Solution**:
1. Reduce request rate
2. Wait for rate limit window to reset
3. Request higher rate limit quota

### 500 Internal Server Error

**Cause**: Step Functions or Lambda error

**Solution**:
1. Check CloudWatch logs for error details
2. Verify Step Functions state machine is deployed
3. Verify Lambda functions are deployed and have correct permissions

## References

- [AWS API Gateway Documentation](https://docs.aws.amazon.com/apigateway/)
- [AWS Cognito Documentation](https://docs.aws.amazon.com/cognito/)
- [AWS Step Functions Documentation](https://docs.aws.amazon.com/stepfunctions/)
- [Multi-Agent Advisory AI System Design](./design.md)
