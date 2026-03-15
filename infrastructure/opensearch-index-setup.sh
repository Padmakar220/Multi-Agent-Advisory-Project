#!/bin/bash

# Set up OpenSearch Serverless index mappings for market intelligence collection
# This script creates the index with vector search configuration

set -e

# Configuration
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-advisory}"
REGION="${AWS_REGION:-us-east-1}"
INDEX_NAME="market-data"

echo "========================================="
echo "OpenSearch Index Setup"
echo "========================================="
echo "Environment: $ENVIRONMENT_NAME"
echo "Region: $REGION"
echo "Index Name: $INDEX_NAME"
echo "========================================="

# Get OpenSearch collection endpoint
echo "Retrieving OpenSearch collection endpoint..."
COLLECTION_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name "${ENVIRONMENT_NAME}-data-stack" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='MarketIntelligenceCollectionEndpoint'].OutputValue" \
  --output text)

if [ -z "$COLLECTION_ENDPOINT" ]; then
  echo "ERROR: Could not retrieve OpenSearch collection endpoint"
  echo "Please ensure the data stack is deployed first"
  exit 1
fi

echo "Collection Endpoint: $COLLECTION_ENDPOINT"

# Create index with vector search mapping
echo ""
echo "Creating index with vector search configuration..."

# Index mapping JSON
INDEX_MAPPING='{
  "settings": {
    "index": {
      "knn": true,
      "knn.algo_param.ef_search": 512
    }
  },
  "mappings": {
    "properties": {
      "document_id": {
        "type": "keyword"
      },
      "document_type": {
        "type": "keyword"
      },
      "title": {
        "type": "text"
      },
      "content": {
        "type": "text"
      },
      "embedding": {
        "type": "knn_vector",
        "dimension": 1536,
        "method": {
          "name": "hnsw",
          "space_type": "cosinesimil",
          "engine": "nmslib",
          "parameters": {
            "ef_construction": 512,
            "m": 16
          }
        }
      },
      "ticker": {
        "type": "keyword"
      },
      "sector": {
        "type": "keyword"
      },
      "timestamp": {
        "type": "date"
      },
      "source": {
        "type": "keyword"
      },
      "metadata": {
        "type": "object",
        "properties": {
          "sentiment": {
            "type": "keyword"
          },
          "relevance_score": {
            "type": "float"
          }
        }
      }
    }
  }
}'

# Create the index using AWS Signature Version 4 authentication
curl -X PUT \
  --aws-sigv4 "aws:amz:${REGION}:aoss" \
  --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" \
  -H "Content-Type: application/json" \
  -d "$INDEX_MAPPING" \
  "${COLLECTION_ENDPOINT}/${INDEX_NAME}"

if [ $? -eq 0 ]; then
  echo ""
  echo "========================================="
  echo "Index created successfully!"
  echo "========================================="
  echo ""
  echo "Index details:"
  echo "  Name: $INDEX_NAME"
  echo "  Vector dimension: 1536"
  echo "  Algorithm: HNSW (cosine similarity)"
  echo ""
  echo "Next steps:"
  echo "1. Ingest market data using the market-data-ingestion Lambda"
  echo "2. Test vector search queries"
else
  echo ""
  echo "ERROR: Index creation failed"
  echo "Note: You may need to use the AWS SDK or boto3 for authentication"
  echo "See: infrastructure/opensearch-index-setup.py for Python alternative"
  exit 1
fi
