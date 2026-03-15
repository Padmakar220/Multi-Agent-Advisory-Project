# Production Deployment Checklist

## Pre-Deployment Verification

### Code and Tests
- [ ] All 84 property-based tests pass (`pytest tests/property/ -v`)
- [ ] Unit test coverage ≥ 80% overall; 100% for `src/compliance/`
- [ ] All integration tests pass with LocalStack
- [ ] No critical or high severity findings in static analysis (`flake8 src/ lambda/`)
- [ ] Compliance library rules reviewed by compliance officer

### Infrastructure
- [ ] `compliance_config.yaml` thresholds reviewed and approved
- [ ] KMS keys exist and rotation is enabled
- [ ] All CloudFormation stacks validate without errors: `aws cloudformation validate-template`
- [ ] IAM policies reviewed for least-privilege compliance
- [ ] ComplianceViolations table access restricted to authorised roles only
- [ ] S3 compliance bucket has 7-year lifecycle policy configured
- [ ] ADOT Lambda layer ARN is current for target region

### Configuration
- [ ] `infrastructure/config/prod.yaml` reviewed and approved
- [ ] Bedrock model ID confirmed: `anthropic.claude-3-5-sonnet-20241022-v2:0`
- [ ] RAG thresholds set: `RAG_TOP_K=5`, `RAG_SIMILARITY_THRESHOLD=0.6`
- [ ] Compliance thresholds set: `GROUNDEDNESS_MIN_THRESHOLD=0.5`, `RELEVANCE_MIN_THRESHOLD=0.4`
- [ ] SNS alert topics have valid email subscriptions confirmed

---

## Deployment Sequence

1. Deploy `network-stack` (VPC, subnets, security groups)
2. Deploy `iam-stack` (IAM roles, KMS, Cognito)
3. Deploy `data-stack` (DynamoDB, OpenSearch, S3)
4. Deploy `lambda-layers` (shared layers)
5. Deploy `compute-stack` (Lambda functions)
6. Deploy `observability-stack` (compliance bucket, LLM Judge)
7. Deploy `adot-layer-stack` (ADOT tracing)
8. Deploy `api-stack` (API Gateway, Step Functions)
9. Run smoke tests: `./scripts/smoke_tests.sh prod`

---

## Post-Deployment Validation

### Functional
- [ ] API Gateway health check returns 200
- [ ] Cognito authentication flow works end-to-end
- [ ] Portfolio analysis workflow completes successfully
- [ ] Compliance screening blocks a test violation input
- [ ] LLM Judge processes a test violation record
- [ ] RAG enrichment returns context for a test query
- [ ] Distributed tracing shows all 11 spans in X-Ray

### Performance
- [ ] Input compliance screening p95 latency ≤ 500ms
- [ ] RAG retrieval p95 latency ≤ 300ms
- [ ] Agent response time p99 ≤ 5 seconds
- [ ] DynamoDB query latency p99 ≤ 200ms

### Security
- [ ] Unauthenticated API requests return 401
- [ ] Cross-user data access returns 403
- [ ] ComplianceViolations table rejects access from non-authorised roles
- [ ] All data in transit uses TLS 1.3

---

## Rollback Criteria

Initiate rollback if any of the following occur within 1 hour of deployment:

- Error rate > 5% on any Lambda function
- Trade execution failure rate > 1%
- Compliance screening false-positive rate > 10%
- API Gateway 5xx rate > 2%
- Any data corruption detected in DynamoDB

### Rollback procedure

```bash
./scripts/rollback.sh prod all
```

Then notify stakeholders and open incident ticket.

---

## Latency Requirements Reference

| Operation | Requirement | Measurement |
|-----------|-------------|-------------|
| Input compliance screening | ≤ 500ms p95 | CloudWatch `ComplianceScreeningDuration` |
| RAG retrieval | ≤ 300ms p95 | CloudWatch `RAGRetrievalDuration` |
| Agent response | ≤ 5s p99 | CloudWatch `AgentResponseTime` |
| DynamoDB query | ≤ 200ms p99 | CloudWatch `DynamoDBQueryLatency` |
| End-to-end workflow | ≤ 30s | Step Functions execution duration |
