# IAM Stack Quick Reference

## Quick Deploy
```bash
cd infrastructure
./deploy-iam.sh
```

## Stack Outputs (Use These ARNs)

### For Lambda Functions
```yaml
Role: !ImportValue advisory-agent-execution-role-arn
```

### For Step Functions
```yaml
RoleArn: !ImportValue advisory-stepfunctions-execution-role-arn
```

### For DynamoDB Tables
```yaml
SSESpecification:
  SSEEnabled: true
  SSEType: KMS
  KMSMasterKeyId: !ImportValue advisory-dynamodb-encryption-key-id
```

## Role Permissions Summary

### AgentExecutionRole
| Service | Permissions | Resources |
|---------|-------------|-----------|
| Bedrock | InvokeModel, InvokeModelWithResponseStream | Claude 3.5 Sonnet models |
| DynamoDB | GetItem, PutItem, UpdateItem, Query | Portfolios, Transactions, AgentSessions, MarketDataCache |
| OpenSearch | aoss:APIAccessAll | All collections |
| CloudWatch | CreateLogGroup, CreateLogStream, PutLogEvents | /aws/lambda/${Env}-* |
| KMS | Decrypt, GenerateDataKey | DynamoDB encryption key |

### StepFunctionsExecutionRole
| Service | Permissions | Resources |
|---------|-------------|-----------|
| Lambda | InvokeFunction | All agent functions |
| CloudWatch | Log delivery | All log groups |
| X-Ray | Tracing | All traces |
| SNS | Publish | ${Env}-* topics |

## User Data Isolation Pattern

### ✅ CORRECT: User-isolated query
```python
response = dynamodb.query(
    TableName='Portfolios',
    KeyConditionExpression='user_id = :uid',
    ExpressionAttributeValues={':uid': authenticated_user_id}
)
```

### ❌ INCORRECT: No user isolation
```python
response = dynamodb.scan(TableName='Portfolios')  # Security violation!
```

## Common Commands

### Get Role ARN
```bash
aws cloudformation describe-stacks \
  --stack-name advisory-iam-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`AgentExecutionRoleArn`].OutputValue' \
  --output text
```

### Update Stack
```bash
./deploy-iam.sh  # Automatically detects and updates
```

### Delete Stack
```bash
aws cloudformation delete-stack --stack-name advisory-iam-stack
```

### View Policies
```bash
aws iam list-attached-role-policies --role-name advisory-agent-execution-role
aws iam list-role-policies --role-name advisory-agent-execution-role
```

## Troubleshooting

### Lambda can't access DynamoDB
1. Check VPC endpoints exist (network stack)
2. Verify Lambda uses AgentExecutionRole
3. Confirm table names match pattern

### Bedrock AccessDenied
1. Verify model ID matches policy
2. Check region matches
3. Confirm Bedrock service available

### KMS decryption fails
1. Verify KMS key ARN correct
2. Check ViaService condition satisfied
3. Confirm DynamoDB using correct key

## Security Checklist

- [ ] Deployed to correct environment
- [ ] Role ARNs saved for other stacks
- [ ] KMS key rotation enabled
- [ ] CloudWatch alarms configured
- [ ] CloudTrail enabled
- [ ] Separate stacks for dev/staging/prod

## Next Steps

1. Deploy IAM stack → `./deploy-iam.sh`
2. Save role ARNs from outputs
3. Deploy data stack with KMS encryption
4. Deploy compute stack with AgentExecutionRole
5. Deploy Step Functions with StepFunctionsExecutionRole

## Requirements Satisfied

- ✅ 13.1: Authentication (IAM/Cognito)
- ✅ 13.2: Authorization (IAM policies)
- ✅ 13.5: User data isolation (partition keys)
