# IAM Stack Documentation

## Overview

The IAM stack provides identity and access management infrastructure for the Multi-Agent Advisory AI System. It implements least-privilege security policies with resource-level permissions and user data isolation.

## Architecture

### IAM Roles

#### 1. AgentExecutionRole
**Purpose:** Execution role for Lambda functions running AI agent logic

**Trusted Entities:**
- `lambda.amazonaws.com` - Lambda service
- `bedrock.amazonaws.com` - Bedrock service

**Permissions:**
- **Bedrock Access:** Invoke Claude 3.5 Sonnet foundation models
- **DynamoDB Access:** Read/write portfolio data with user isolation
- **OpenSearch Access:** Query market intelligence data
- **CloudWatch Logs:** Write logs and metrics
- **KMS Access:** Decrypt/encrypt DynamoDB data
- **VPC Access:** Execute within VPC (via managed policy)

**Use Cases:**
- Portfolio Analyzer Agent Lambda functions
- Tax Optimizer Agent Lambda functions
- Rebalancing Agent Lambda functions
- Supervisor Agent Lambda functions
- Trade Executor Lambda functions

#### 2. StepFunctionsExecutionRole
**Purpose:** Execution role for Step Functions workflows orchestrating agent interactions

**Trusted Entities:**
- `states.amazonaws.com` - Step Functions service

**Permissions:**
- **Lambda Invocation:** Invoke all agent Lambda functions
- **CloudWatch Logs:** Write workflow logs
- **X-Ray Tracing:** Distributed tracing for debugging
- **SNS Publishing:** Send alerts and notifications

**Use Cases:**
- Portfolio rebalancing workflows
- Tax optimization workflows
- Trade execution workflows
- Human-in-the-loop approval workflows

### KMS Encryption Key

#### DynamoDBEncryptionKey
**Purpose:** Customer-managed KMS key for encrypting DynamoDB tables at rest

**Key Features:**
- **Automatic Key Rotation:** Enabled (rotates yearly)
- **Deletion Policy:** Retain (prevents accidental deletion)
- **Update Replace Policy:** Retain (preserves key during stack updates)
- **Key Alias:** `alias/${EnvironmentName}-dynamodb-encryption`

**Key Policy:**
- **Root Account Access:** Full key management permissions
- **DynamoDB Service Access:** Decrypt, DescribeKey, CreateGrant (via ViaService condition)
- **Lambda Service Access:** Decrypt, GenerateDataKey (via ViaService condition)

**Security Features:**
- Service-scoped access via `kms:ViaService` condition
- Prevents direct API access to key material
- Automatic yearly rotation with old material retained
- CloudTrail logging of all key operations

**Conditional Creation:**
- Created automatically if `KMSKeyArn` parameter is empty
- Uses existing key if `KMSKeyArn` parameter is provided
- Allows flexibility for different deployment scenarios

**Use Cases:**
- DynamoDB table encryption at rest
- Portfolio data encryption
- Transaction history encryption
- Agent session data encryption

### IAM Policies

#### BedrockAccessPolicy
Allows agents to invoke Amazon Bedrock foundation models.

**Permissions:**
- `bedrock:InvokeModel` - Synchronous model invocation
- `bedrock:InvokeModelWithResponseStream` - Streaming model invocation
- `bedrock:InvokeAgent` - Agent runtime invocation
- `bedrock:Retrieve` - Knowledge base retrieval

**Resources:**
- Claude 3.5 Sonnet models (all versions)
- Bedrock agents in the account
- Knowledge bases in the account

**Security Considerations:**
- Scoped to specific model families (anthropic.claude-3-5-sonnet-*)
- Region-specific resource ARNs
- No wildcard permissions

#### DynamoDBAccessPolicy
Allows agents to read and write portfolio data with user isolation.

**Permissions:**
- `dynamodb:GetItem` - Read single items
- `dynamodb:PutItem` - Write new items
- `dynamodb:UpdateItem` - Update existing items
- `dynamodb:DeleteItem` - Delete items
- `dynamodb:Query` - Query with partition key
- `dynamodb:Scan` - Full table scans (limited use)
- `dynamodb:BatchGetItem` - Batch reads
- `dynamodb:BatchWriteItem` - Batch writes
- `dynamodb:DescribeStream` - Access DynamoDB streams
- `dynamodb:GetRecords` - Read stream records
- `dynamodb:GetShardIterator` - Stream iteration
- `dynamodb:ListStreams` - List available streams

**Resources:**
- Portfolios table and indexes
- Transactions table and indexes
- AgentSessions table and indexes
- MarketDataCache table
- DynamoDB streams for all tables

**Security Considerations:**
- Resource-level permissions (specific table ARNs)
- User data isolation via application-level filtering (user_id partition key)
- No cross-account access
- Stream access for audit and event processing

**User Data Isolation:**
While the IAM policy grants access to tables, application code MUST enforce user data isolation by:
1. Always including `user_id` in partition key for queries
2. Validating user identity from request context
3. Never allowing cross-user data access
4. Using DynamoDB condition expressions for additional safety

Example application-level isolation:
```python
# CORRECT: User-isolated query
response = dynamodb.query(
    TableName='Portfolios',
    KeyConditionExpression='user_id = :uid',
    ExpressionAttributeValues={':uid': authenticated_user_id}
)

# INCORRECT: No user isolation (security violation)
response = dynamodb.scan(TableName='Portfolios')
```

#### OpenSearchAccessPolicy
Allows agents to query market intelligence data from OpenSearch Serverless.

**Permissions:**
- `aoss:APIAccessAll` - Full API access to collections
- `aoss:ListCollections` - List available collections
- `aoss:BatchGetCollection` - Get collection metadata

**Resources:**
- All OpenSearch Serverless collections in the account
- Scoped to specific region

**Security Considerations:**
- OpenSearch Serverless uses data access policies for fine-grained control
- IAM policy provides service-level access
- Collection-level access controlled separately
- No cross-region access

#### CloudWatchLogsPolicy
Allows agents to write logs and metrics.

**Permissions:**
- `logs:CreateLogGroup` - Create log groups
- `logs:CreateLogStream` - Create log streams
- `logs:PutLogEvents` - Write log events
- `logs:DescribeLogStreams` - Query log streams
- `cloudwatch:PutMetricData` - Publish custom metrics

**Resources:**
- Log groups: `/aws/lambda/${EnvironmentName}-*`
- Metrics namespace: `${EnvironmentName}/Agents`

**Security Considerations:**
- Scoped to environment-specific log groups
- Custom metrics isolated by namespace
- No access to other application logs

#### KMSAccessPolicy
Allows agents to decrypt and encrypt DynamoDB data.

**Permissions:**
- `kms:Decrypt` - Decrypt data keys
- `kms:GenerateDataKey` - Generate data encryption keys
- `kms:DescribeKey` - Get key metadata

**Resources:**
- DynamoDB encryption KMS key (created by stack or provided)

**Conditions:**
- `kms:ViaService: dynamodb.${Region}.amazonaws.com` - Only via DynamoDB service

**Security Considerations:**
- Condition key prevents direct KMS API calls
- Keys only usable through DynamoDB
- Separate key per environment recommended

#### StepFunctionsLambdaPolicy
Allows Step Functions to invoke agent Lambda functions.

**Permissions:**
- `lambda:InvokeFunction` - Invoke Lambda functions

**Resources:**
- All agent Lambda functions (pattern: `${EnvironmentName}-*`)

**Security Considerations:**
- Scoped to environment-specific functions
- No access to other Lambda functions
- No permission to modify functions

#### StepFunctionsLogsPolicy
Allows Step Functions to write workflow logs.

**Permissions:**
- `logs:CreateLogDelivery` - Create log delivery
- `logs:GetLogDelivery` - Get log delivery status
- `logs:UpdateLogDelivery` - Update log delivery
- `logs:DeleteLogDelivery` - Delete log delivery
- `logs:ListLogDeliveries` - List log deliveries
- `logs:PutResourcePolicy` - Set resource policies
- `logs:DescribeResourcePolicies` - Get resource policies
- `logs:DescribeLogGroups` - List log groups

**Resources:**
- All CloudWatch Logs resources (required for log delivery)

**Security Considerations:**
- Broad permissions required for Step Functions logging
- Scoped to CloudWatch Logs service
- No data access permissions

#### StepFunctionsXRayPolicy
Allows Step Functions to publish distributed tracing data.

**Permissions:**
- `xray:PutTraceSegments` - Write trace segments
- `xray:PutTelemetryRecords` - Write telemetry
- `xray:GetSamplingRules` - Get sampling configuration
- `xray:GetSamplingTargets` - Get sampling targets

**Resources:**
- All X-Ray resources (required for tracing)

**Security Considerations:**
- Standard X-Ray permissions
- No access to trace data
- Write-only permissions

#### StepFunctionsSNSPolicy
Allows Step Functions to publish alerts and notifications.

**Permissions:**
- `sns:Publish` - Publish messages to topics

**Resources:**
- SNS topics: `${EnvironmentName}-*`

**Security Considerations:**
- Scoped to environment-specific topics
- No topic management permissions
- Publish-only access

## Security Features

### Least-Privilege Access
- Each role has only the minimum permissions required
- Resource-level permissions (no wildcards where possible)
- Condition keys for additional constraints
- Separate roles for different components

### User Data Isolation
- Application-level enforcement via partition keys
- IAM policies scoped to user-owned resources
- No cross-user data access
- Audit logging for all data access

### Encryption
- KMS encryption for DynamoDB data at rest
- TLS 1.3 for data in transit
- Separate KMS keys per environment
- Automatic key rotation enabled (yearly)
- Customer-managed keys (not AWS-managed)

### Audit and Compliance
- CloudWatch Logs for all agent actions
- X-Ray tracing for distributed workflows
- DynamoDB streams for change tracking
- SNS alerts for critical events

## Deployment

### Prerequisites
- AWS CLI installed and configured
- Appropriate AWS credentials with IAM permissions
- CloudFormation permissions to create stacks

### Deployment Steps

1. **Set environment variables (optional):**
   ```bash
   export AWS_REGION=us-east-1
   export ENVIRONMENT=advisory
   export KMS_KEY_ARN=arn:aws:kms:us-east-1:123456789012:key/existing-key-id  # Optional
   ```

2. **Deploy the stack:**
   ```bash
   cd infrastructure
   ./deploy-iam.sh
   ```

3. **Verify deployment:**
   ```bash
   aws cloudformation describe-stacks \
     --stack-name advisory-iam-stack \
     --region us-east-1
   ```

4. **Review outputs:**
   - `AgentExecutionRoleArn` - Use for Lambda function configuration
   - `StepFunctionsExecutionRoleArn` - Use for Step Functions workflow configuration
   - `DynamoDBEncryptionKeyArn` - Use for DynamoDB table encryption

### Deployment Options

#### Using Existing KMS Key
If you have an existing KMS key for DynamoDB encryption:
```bash
export KMS_KEY_ARN=arn:aws:kms:us-east-1:123456789012:key/your-key-id
./deploy-iam.sh
```

#### Creating New KMS Key
If you don't specify a KMS key, the stack will create one automatically:
```bash
./deploy-iam.sh
```

### Stack Parameters

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| EnvironmentName | Environment prefix for resources | advisory | No |
| BedrockModelId | Bedrock model ID for Claude 3.5 Sonnet | anthropic.claude-3-5-sonnet-20241022-v2:0 | No |
| KMSKeyArn | ARN of existing KMS key | (creates new) | No |

### Stack Outputs

| Output | Description | Export Name |
|--------|-------------|-------------|
| AgentExecutionRoleArn | ARN of Agent Execution Role | ${EnvironmentName}-agent-execution-role-arn |
| AgentExecutionRoleName | Name of Agent Execution Role | ${EnvironmentName}-agent-execution-role-name |
| StepFunctionsExecutionRoleArn | ARN of Step Functions Execution Role | ${EnvironmentName}-stepfunctions-execution-role-arn |
| StepFunctionsExecutionRoleName | Name of Step Functions Execution Role | ${EnvironmentName}-stepfunctions-execution-role-name |
| DynamoDBEncryptionKeyArn | ARN of DynamoDB encryption KMS key | ${EnvironmentName}-dynamodb-encryption-key-arn |
| DynamoDBEncryptionKeyId | ID of DynamoDB encryption KMS key | ${EnvironmentName}-dynamodb-encryption-key-id |

## Usage

### Lambda Function Configuration

When creating Lambda functions for agents, use the AgentExecutionRole:

```yaml
# CloudFormation example
SupervisorAgentFunction:
  Type: AWS::Lambda::Function
  Properties:
    FunctionName: !Sub ${EnvironmentName}-supervisor-agent
    Role: !ImportValue advisory-agent-execution-role-arn
    Runtime: python3.11
    Handler: handler.lambda_handler
    # ... other properties
```

### Step Functions Configuration

When creating Step Functions workflows, use the StepFunctionsExecutionRole:

```yaml
# CloudFormation example
RebalancingWorkflow:
  Type: AWS::StepFunctions::StateMachine
  Properties:
    StateMachineName: !Sub ${EnvironmentName}-rebalancing-workflow
    RoleArn: !ImportValue advisory-stepfunctions-execution-role-arn
    DefinitionString: !Sub |
      {
        "Comment": "Portfolio Rebalancing Workflow",
        "StartAt": "InitializeSupervisor",
        ...
      }
```

### DynamoDB Table Configuration

When creating DynamoDB tables, use the KMS key for encryption:

```yaml
# CloudFormation example
PortfoliosTable:
  Type: AWS::DynamoDB::Table
  Properties:
    TableName: !Sub ${EnvironmentName}-portfolios
    SSESpecification:
      SSEEnabled: true
      SSEType: KMS
      KMSMasterKeyId: !ImportValue advisory-dynamodb-encryption-key-id
    # ... other properties
```

## Monitoring and Troubleshooting

### CloudWatch Logs
Agent logs are written to:
- `/aws/lambda/${EnvironmentName}-supervisor-agent`
- `/aws/lambda/${EnvironmentName}-portfolio-analyzer`
- `/aws/lambda/${EnvironmentName}-tax-optimizer`
- `/aws/lambda/${EnvironmentName}-rebalancing-agent`
- `/aws/lambda/${EnvironmentName}-trade-executor`

### CloudWatch Metrics
Custom metrics are published to namespace:
- `${EnvironmentName}/Agents`

### X-Ray Tracing
Step Functions workflows publish traces to X-Ray for distributed debugging.

### Common Issues

#### Issue: Lambda function cannot access DynamoDB
**Cause:** Missing VPC endpoints or incorrect IAM permissions
**Solution:**
1. Verify VPC endpoints for DynamoDB exist (from network stack)
2. Check Lambda function is using AgentExecutionRole
3. Verify table names match the pattern `${EnvironmentName}-*`

#### Issue: Bedrock invocation fails with AccessDenied
**Cause:** Model ID mismatch or region mismatch
**Solution:**
1. Verify model ID matches the policy (anthropic.claude-3-5-sonnet-*)
2. Ensure Lambda function is in the same region as Bedrock
3. Check Bedrock service is available in the region

#### Issue: KMS decryption fails
**Cause:** Missing ViaService condition or incorrect key
**Solution:**
1. Verify KMS key ARN is correct
2. Ensure DynamoDB is using the correct KMS key
3. Check the ViaService condition is satisfied

## Security Best Practices

### 1. Verify KMS Key Rotation
Automatic key rotation is enabled by default in the stack. Verify it's active:
```bash
aws kms get-key-rotation-status --key-id <key-id>
```

Expected output:
```json
{
    "KeyRotationEnabled": true
}
```

The KMS key automatically rotates yearly. Old key material is retained for decrypting existing data.

### 2. Monitor IAM Usage
Set up CloudWatch alarms for unusual IAM activity:
- Failed authentication attempts
- Unauthorized access attempts
- Unusual API call patterns

### 3. Regular Access Reviews
Periodically review IAM policies and remove unused permissions:
```bash
aws iam get-role-policy --role-name advisory-agent-execution-role --policy-name advisory-bedrock-access-policy
```

### 4. Use Separate Environments
Deploy separate stacks for dev, staging, and production:
```bash
export ENVIRONMENT=advisory-prod
./deploy-iam.sh
```

### 5. Enable CloudTrail
Ensure CloudTrail is enabled for audit logging of all IAM actions.

## Compliance

### Requirements Satisfied

This IAM stack satisfies the following requirements from the design document:

- **Requirement 13.1:** User authentication via IAM/Cognito
- **Requirement 13.2:** IAM-based authorization for agent data access
- **Requirement 13.5:** User data isolation via IAM policies and partition keys

### Security Controls

- **SC-1:** Least-privilege access control
- **SC-2:** Resource-level permissions
- **SC-3:** Encryption at rest (KMS)
- **SC-4:** Encryption in transit (TLS 1.3)
- **SC-5:** Audit logging (CloudWatch)
- **SC-6:** User data isolation

## Maintenance

### Updating Policies
To update IAM policies:
1. Modify `iam-stack.yaml`
2. Run `./deploy-iam.sh`
3. CloudFormation will update only changed resources

### Adding New Permissions
To add permissions for new services:
1. Create a new policy in `iam-stack.yaml`
2. Attach to appropriate role
3. Follow least-privilege principles
4. Test in dev environment first

### Removing Permissions
To remove unused permissions:
1. Identify unused permissions via CloudTrail
2. Remove from policy in `iam-stack.yaml`
3. Deploy and test
4. Monitor for access denied errors

## References

- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [DynamoDB Encryption at Rest](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/EncryptionAtRest.html)
- [Step Functions IAM Policies](https://docs.aws.amazon.com/step-functions/latest/dg/procedure-create-iam-role.html)
- [Bedrock Security](https://docs.aws.amazon.com/bedrock/latest/userguide/security.html)
- [OpenSearch Serverless Security](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-security.html)
