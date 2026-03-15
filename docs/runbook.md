# Operational Runbook

## Monitoring

### CloudWatch Dashboard

Navigate to CloudWatch → Dashboards → `advisory-{env}-dashboard`

Key widgets:
- Lambda Duration / Errors / Invocations
- Agent Response Time (p99)
- Workflow Duration (avg)
- DynamoDB Read/Write Latency
- Compliance Violations (count by severity)

### Key Alarms

| Alarm | Threshold | Action |
|-------|-----------|--------|
| `HighAgentResponseTime` | > 5s for 2 periods | Page on-call |
| `HighDynamoDBLatency` | > 200ms for 3 periods | Investigate DynamoDB |
| `TradeExecutionFailures` | < 5 successes/period | Page on-call |
| `ComplianceViolationRate` | > 10/hour | Notify compliance team |

---

## Troubleshooting

### Agent Lambda timeout

1. Check CloudWatch Logs: `/aws/lambda/{env}-{agent-name}`
2. Look for `Task timed out` errors
3. Check Bedrock throttling: `ThrottlingException` in logs
4. Increase Lambda timeout or add retry backoff

### DynamoDB throttling

1. Check `ConsumedWriteCapacityUnits` metric
2. Table uses PAY_PER_REQUEST — throttling indicates burst
3. Add exponential backoff in application code
4. Consider enabling DynamoDB DAX for read-heavy workloads

### Step Functions workflow stuck

1. Navigate to Step Functions → Executions
2. Find stuck execution and check current state
3. For `WaitForApproval` state: check if approval Lambda received the task token
4. For agent states: check Lambda CloudWatch logs for errors

### Compliance violations spike

1. Check `advisory-{env}-compliance-violations` DynamoDB table
2. Query by `investigation_status = pending`
3. Review LLM Judge Lambda logs: `/aws/lambda/{env}-llm-judge`
4. Escalate to compliance officer if `escalate` verdicts > 5/hour

### OpenSearch unavailable

1. Check OpenSearch Serverless collection status in AWS Console
2. Verify VPC endpoint connectivity
3. RAG enrichment will degrade gracefully (no context injected)
4. Market data queries will fail — check `QueryMarketDataTool` logs

---

## Incident Response

### Severity 1 (System Down)

1. Page on-call engineer immediately
2. Check all Lambda function error rates in CloudWatch
3. Verify API Gateway is returning 200s
4. If trade execution is affected: halt all pending workflows via Step Functions console
5. Engage AWS Support if infrastructure issue suspected

### Severity 2 (Degraded Performance)

1. Notify on-call within 15 minutes
2. Identify bottleneck (Lambda, DynamoDB, Bedrock, OpenSearch)
3. Scale up if needed (increase Lambda concurrency)
4. Monitor for 30 minutes before declaring resolved

---

## Backup and Recovery

### DynamoDB

- All tables have Point-in-Time Recovery (PITR) enabled
- Restore: AWS Console → DynamoDB → Table → Backups → Restore to point in time
- Target: restore to new table, then swap application config

### S3 Compliance Bucket

- Versioning enabled; 7-year lifecycle retention
- Restore deleted objects: AWS Console → S3 → Bucket → Versions

### OpenSearch

- No automated backup for Serverless collections
- Re-index from source data if collection is lost
- Market data ingestion Lambda will re-populate on next scheduled run
