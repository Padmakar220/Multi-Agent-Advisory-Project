#!/usr/bin/env python3
"""
Set up OpenSearch Serverless index mappings for market intelligence collection.
This script creates the index with vector search configuration using AWS authentication.
"""

import boto3
import json
import sys
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

def get_collection_endpoint(environment_name, region):
    """Retrieve OpenSearch collection endpoint from CloudFormation stack."""
    cfn = boto3.client('cloudformation', region_name=region)
    
    try:
        response = cfn.describe_stacks(StackName=f"{environment_name}-data-stack")
        outputs = response['Stacks'][0]['Outputs']
        
        for output in outputs:
            if output['OutputKey'] == 'MarketIntelligenceCollectionEndpoint':
                return output['OutputValue']
        
        print("ERROR: Could not find OpenSearch collection endpoint in stack outputs")
        return None
    except Exception as e:
        print(f"ERROR: Failed to retrieve collection endpoint: {e}")
        return None

def create_index(endpoint, region, index_name):
    """Create OpenSearch index with vector search configuration."""
    
    # Set up AWS authentication
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, region, 'aoss')
    
    # Create OpenSearch client
    client = OpenSearch(
        hosts=[{'host': endpoint.replace('https://', ''), 'port': 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30
    )
    
    # Index mapping configuration
    index_mapping = {
        "settings": {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 512
            }
        },
        "mappings": {
            "properties": {
                "document_id": {"type": "keyword"},
                "document_type": {"type": "keyword"},
                "title": {"type": "text"},
                "content": {"type": "text"},
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
                "ticker": {"type": "keyword"},
                "sector": {"type": "keyword"},
                "timestamp": {"type": "date"},
                "source": {"type": "keyword"},
                "metadata": {
                    "type": "object",
                    "properties": {
                        "sentiment": {"type": "keyword"},
                        "relevance_score": {"type": "float"}
                    }
                }
            }
        }
    }
    
    try:
        # Check if index already exists
        if client.indices.exists(index=index_name):
            print(f"Index '{index_name}' already exists")
            response = input("Do you want to delete and recreate it? (yes/no): ")
            if response.lower() == 'yes':
                client.indices.delete(index=index_name)
                print(f"Deleted existing index '{index_name}'")
            else:
                print("Keeping existing index")
                return True
        
        # Create the index
        response = client.indices.create(index=index_name, body=index_mapping)
        print(f"Index '{index_name}' created successfully!")
        print(json.dumps(response, indent=2))
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to create index: {e}")
        return False

def main():
    """Main function."""
    import os
    
    # Configuration
    environment_name = os.environ.get('ENVIRONMENT_NAME', 'advisory')
    region = os.environ.get('AWS_REGION', 'us-east-1')
    index_name = 'market-data'
    
    print("=" * 50)
    print("OpenSearch Index Setup")
    print("=" * 50)
    print(f"Environment: {environment_name}")
    print(f"Region: {region}")
    print(f"Index Name: {index_name}")
    print("=" * 50)
    
    # Get collection endpoint
    print("\nRetrieving OpenSearch collection endpoint...")
    endpoint = get_collection_endpoint(environment_name, region)
    
    if not endpoint:
        print("ERROR: Could not retrieve collection endpoint")
        print("Please ensure the data stack is deployed first")
        sys.exit(1)
    
    print(f"Collection Endpoint: {endpoint}")
    
    # Create index
    print("\nCreating index with vector search configuration...")
    success = create_index(endpoint, region, index_name)
    
    if success:
        print("\n" + "=" * 50)
        print("Index created successfully!")
        print("=" * 50)
        print("\nIndex details:")
        print(f"  Name: {index_name}")
        print("  Vector dimension: 1536")
        print("  Algorithm: HNSW (cosine similarity)")
        print("\nNext steps:")
        print("1. Ingest market data using the market-data-ingestion Lambda")
        print("2. Test vector search queries")
    else:
        print("\nERROR: Index creation failed")
        sys.exit(1)

if __name__ == '__main__':
    main()
