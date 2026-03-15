# Deployment Guide

## Prerequisites

- AWS CLI v2 configured with appropriate credentials
- Python 3.11
- `jq` installed
- IAM permissions: CloudFormation, Lambda, DynamoDB, S3, OpenSearch, Step Functions, API Gateway, Cognito, KMS, IAM

---

## Environments

| Environment | Branch/Tag | Deployment |
|-------------|-----------|------------|
| dev | `main` | Automatic on push |
| staging | `release/*` | Automatic on tag |
| prod | manual | Requires approval |

---

## Deployment Steps

### 1. Package Lambda functions

```bash
./scripts/package_lambdas.sh
```

Packages all Lambda functions and uploads to S3.

### 2. Deploy all stacks

```bash
./scripts/deploy.sh <environment>
# e.g. ./scripts/deploy.sh dev
```

Stack deployment order:
1. `network-stack` — VPC, subnets, security groups
2. `iam-stack` — IAM roles, KMS keys, Cognito
3. `data-stack` — DynamoDB, OpenSearch, S3
4. `lambda-layers` — shared Lambda layers
5. `compute-stack` — Lambda functions
6. `observability-stack` — compliance bucket, LLM Judge
7. `adot-layer-stack` — ADOT tracing layer
8. `api-stack` — API Gateway, Step Functions

### 3. Run smoke tests

```bash
./scripts/smoke_tests.sh <environment>
```

---

## Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `EnvironmentName` | Resource name prefix | `advisory` |
| `KMSKeyId` | KMS key for encryption | (required) |
| `BedrockModelId` | Bedrock model ID | `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `RAG_TOP_K` | RAG top-k documents | `5` |
| `RAG_SIMILARITY_THRESHOLD` | Min similarity score | `0.6` |
| `GROUNDEDNESS_MIN_THRESHOLD` | Min groundedness | `0.5` |
| `RELEVANCE_MIN_THRESHOLD` | Min relevance | `0.4` |

Environment-specific configs: `infrastructure/config/{env}.yaml`

---

## Rollback

```bash
./scripts/rollback.sh <environment> <stack-name>
```

To rollback all stacks to previous version:
```bash
./scripts/rollback.sh <environment> all
```

---

## CI/CD Pipeline

GitHub Actions workflow: `.github/workflows/deploy.yml`

- **On push to main:** Deploy to dev
- **On release tag:** Deploy to staging
- **Manual trigger:** Deploy to prod (requires approval)
