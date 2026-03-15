# Data Stack Documentation

## Overview

The data stack provides the foundational data layer for the Multi-Agent Advisory AI System, including:
- DynamoDB tables for portfolio data, transactions, agent sessions, and market data caching
- OpenSearch Serverless collection for vector-based market intelligence search
- S3 buckets for portfolio reports and document storage

## Components

### DynamoDB Tables

#### 1. Portfolios Table
- **Purpose**: Store portfolio holdings and metadata
- **Key Schema**: 
  - HASH: `user_id` (String)
  - RANGE: `portfolio_id` (String)
- **Features**:
  - KMS encryption at rest
  - DynamoDB Streams enabled (NEW_AND_OLD_IMAGES)
  - Point-in-time recovery enabled
  - PAY_PER_REQUEST billing mode
- **Item Structure**:
  ```json
  {
    "user_id": "user_123",
    "portfolio_id": "portfolio_456",
    "portfolio_name": "Retirement Account",
    "target_allocation": {
      "stocks": 0.60,
      "bonds": 0.30,
      "cash": 0.10
    },
    "holdings": [
      {
        "ticker": "VTI",
        "quantity": 100,
        "cost_basis": 200.50,
        "current_price": 220.75,
        "purchase_date": "2023-01-15T00:00:00Z"
      }
    ],
    "total_value": 150000.00,
    "risk_tolerance": "moderate",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-15T10:30:00Z"
  }
  ```

#### 2. Transactions Table
- **Purpose**: Store transaction history for audit and tax reporting
- **Key Schema**:
  - HASH: `user_id` (String)
  - RANGE: `timestamp` (String, ISO 8601 format)
- **Global Secondary Indexes**:
  - PortfolioIndex: `portfolio_id` (HASH), `timestamp` (RANGE)
- **Features**:
  - KMS encryption at rest
  - DynamoDB Streams enabled
  - Point-in-time recovery enabled
  - PAY_PER_REQUEST billing mode
- **Item Structure**:
  ```json
  {
    "user_id": "user_123",
    "timestamp": "2024-01-15T14:30:00Z",
    "transaction_id": "txn_789",
    "portfolio_id": "portfolio_456",
    "action": "buy",
    "ticker": "VTI",
    "quantity": 10,
    "price": 220.75,
    "commission": 0.00,
    "total_cost": 2207.50,
    "execution_status": "completed",
    "order_type": "market",
    "initiated_by": "rebalancing_agent"
  }
  ```

#### 3. AgentSessions Table
- **Purpose**: Store agent state and session context
- **Key Schema**:
  - HASH: `session_id` (String)
- **Global Secondary Indexes**:
  - UserIndex: `user_id` (HASH)
- **Features**:
  - KMS encryption at rest
  - TTL enabled (24 hours from last update)
  - Point-in-time recovery enabled
  - PAY_PER_REQUEST billing mode
- **Item Structure**:
  ```json
  {
    "session_id": "session_abc123",
    "user_id": "user_123",
    "agent_type": "supervisor",
    "state": {
      "current_step": "waiting_approval",
      "subtasks_completed": ["portfolio_analysis", "tax_optimization"],
      "pending_subtasks": ["rebalancing"],
      "conversation_history": [],
      "user_preferences": {}
    },
    "created_at": "2024-01-15T14:00:00Z",
    "last_updated": "2024-01-15T14:30:00Z",
    "ttl": 1705334400
  }
  ```

#### 4. MarketDataCache Table
- **Purpose**: Cache frequently accessed market data with TTL
- **Key Schema**:
  - HASH: `data_key` (String, format: "type:identifier", e.g., "price:VTI")
- **Features**:
  - KMS encryption at rest
  - TTL enabled (5 minutes)
  - PAY_PER_REQUEST billing mode
- **Item Structure**:
  ```json
  {
    "data_key": "price:VTI",
    "data_type": "price",
    "ticker": "VTI",
    "value": 220.75,
    "timestamp": "2024-01-15T14:30:00Z",
    "ttl": 1705334700,
    "source": "market_data_api"
  }
  ```

### OpenSearch Serverless Collection

#### Market Intelligence Collection
- **Name**: `{environment}-market-intelligence`
- **Type**: VECTORSEARCH
- **Purpose**: Vector-based search for market data, news, and regulatory documents
- **Index Name**: `market-data`
- **Vector Configuration**:
  - Dimension: 1536 (Bedrock Titan Embeddings)
  - Algorithm: HNSW (Hierarchical Navigable Small World)
  - Space Type: Cosine Similarity
  - Engine: nmslib
- **Index Mapping**:
  ```json
  {
    "document_id": "keyword",
    "document_type": "keyword",
    "title": "text",
    "content": "text",
    "embedding": "knn_vector (1536 dimensions)",
    "ticker": "keyword",
    "sector": "keyword",
    "timestamp": "date",
    "source": "keyword",
    "metadata": {
      "sentiment": "keyword",
      "relevance_score": "float"
    }
  }
  ```
- **Security**:
  - Encryption at rest (AWS-owned key)
  - Network policy (private access only)
  - Data access policy (agent execution role only)

### S3 Buckets

#### Portfolio Reports Bucket
- **Name**: `{environment}-portfolio-reports-{account-id}`
- **Purpose**: Store portfolio reports and documents
- **Features**:
  - SSE-KMS encryption at rest
  - Versioning enabled
  - Lifecycle policies:
    - Transition to STANDARD_IA after 30 days
    - Transition to GLACIER after 90 days
    - Delete old versions after 90 days
  - Public access blocked
  - Bucket policy for agent access only
  - Deny insecure transport (enforce HTTPS)

## Deployment

### Prerequisites
1. IAM stack deployed (provides KMS key)
2. Network stack deployed (provides VPC endpoints)
3. AWS CLI configured with appropriate permissions

### Deploy Data Stack

```bash
# Set environment variables
export ENVIRONMENT_NAME=advisory
export AWS_REGION=us-east-1

# Deploy the stack
./infrastructure/deploy-data.sh
```

### Set Up OpenSearch Index

After deploying the data stack, create the OpenSearch index:

```bash
# Using Python script (recommended)
python3 infrastructure/opensearch-index-setup.py

# Or using bash script
./infrastructure/opensearch-index-setup.sh
```

### Verify Deployment

```bash
# List DynamoDB tables
aws dynamodb list-tables --region us-east-1

# Describe Portfolios table
aws dynamodb describe-table \
  --table-name advisory-portfolios \
  --region us-east-1

# List OpenSearch collections
aws opensearchserverless list-collections --region us-east-1

# List S3 buckets
aws s3 ls | grep portfolio-reports
```

## Access Patterns

### DynamoDB Access Patterns

#### Portfolios Table
1. Get portfolio by user and portfolio ID
   ```python
   response = dynamodb.get_item(
       TableName='advisory-portfolios',
       Key={'user_id': 'user_123', 'portfolio_id': 'portfolio_456'}
   )
   ```

2. Query all portfolios for a user
   ```python
   response = dynamodb.query(
       TableName='advisory-portfolios',
       KeyConditionExpression='user_id = :uid',
       ExpressionAttributeValues={':uid': 'user_123'}
   )
   ```

#### Transactions Table
1. Get transactions for a user in time range
   ```python
   response = dynamodb.query(
       TableName='advisory-transactions',
       KeyConditionExpression='user_id = :uid AND #ts BETWEEN :start AND :end',
       ExpressionAttributeNames={'#ts': 'timestamp'},
       ExpressionAttributeValues={
           ':uid': 'user_123',
           ':start': '2024-01-01T00:00:00Z',
           ':end': '2024-01-31T23:59:59Z'
       }
   )
   ```

2. Query transactions by portfolio (using GSI)
   ```python
   response = dynamodb.query(
       TableName='advisory-transactions',
       IndexName='PortfolioIndex',
       KeyConditionExpression='portfolio_id = :pid',
       ExpressionAttributeValues={':pid': 'portfolio_456'}
   )
   ```

### OpenSearch Access Patterns

#### Vector Search
```python
from opensearchpy import OpenSearch

# Perform knn vector search
query = {
    "size": 10,
    "query": {
        "knn": {
            "embedding": {
                "vector": embedding_vector,  # 1536-dimensional array
                "k": 10
            }
        }
    },
    "filter": {
        "term": {"ticker": "VTI"}
    }
}

response = client.search(index='market-data', body=query)
```

### S3 Access Patterns

#### Upload Report
```python
s3.put_object(
    Bucket='advisory-portfolio-reports-123456789012',
    Key=f'reports/{user_id}/{portfolio_id}/analysis_{timestamp}.pdf',
    Body=report_data,
    ServerSideEncryption='aws:kms',
    SSEKMSKeyId=kms_key_id
)
```

## Monitoring

### CloudWatch Metrics

#### DynamoDB
- ConsumedReadCapacityUnits
- ConsumedWriteCapacityUnits
- UserErrors
- SystemErrors
- ThrottledRequests

#### OpenSearch Serverless
- SearchRate
- SearchLatency
- IndexingRate
- IndexingLatency

#### S3
- NumberOfObjects
- BucketSizeBytes
- AllRequests
- 4xxErrors
- 5xxErrors

### Alarms

Set up CloudWatch alarms for:
- DynamoDB throttling (> 10 throttled requests in 5 minutes)
- OpenSearch search latency (> 1 second p99)
- S3 4xx/5xx errors (> 5% error rate)

## Cost Optimization

### DynamoDB
- PAY_PER_REQUEST billing mode scales to zero
- Enable point-in-time recovery only for critical tables
- Use TTL to automatically delete expired data
- Monitor and optimize GSI usage

### OpenSearch Serverless
- Collection scales automatically based on usage
- No idle capacity charges
- Monitor OCU (OpenSearch Compute Units) usage

### S3
- Lifecycle policies reduce storage costs
- Transition to cheaper storage classes over time
- Delete old versions to reduce costs

## Security

### Encryption
- All DynamoDB tables encrypted with KMS customer-managed key
- OpenSearch collection encrypted at rest
- S3 bucket encrypted with SSE-KMS
- All data in transit uses TLS 1.3

### Access Control
- IAM policies enforce least-privilege access
- DynamoDB condition keys enforce user data isolation
- OpenSearch data access policy restricts to agent role only
- S3 bucket policy denies insecure transport

### Audit
- DynamoDB Streams capture all data changes
- CloudWatch Logs capture all API calls
- S3 access logging available if needed

## Troubleshooting

### Common Issues

#### 1. KMS Key Not Found
**Error**: "KMS key not found or not accessible"
**Solution**: Ensure IAM stack is deployed and KMS key is created

#### 2. OpenSearch Index Creation Fails
**Error**: "Authentication failed"
**Solution**: Ensure agent execution role has data access policy permissions

#### 3. S3 Access Denied
**Error**: "Access Denied when uploading to S3"
**Solution**: Verify bucket policy includes agent execution role ARN

#### 4. DynamoDB Throttling
**Error**: "ProvisionedThroughputExceededException"
**Solution**: PAY_PER_REQUEST mode should prevent this; check for hot partitions

## Next Steps

After deploying the data stack:
1. Deploy compute stack (Lambda functions)
2. Implement MCP tools for data access
3. Set up market data ingestion pipeline
4. Configure monitoring and alarms
5. Run integration tests
