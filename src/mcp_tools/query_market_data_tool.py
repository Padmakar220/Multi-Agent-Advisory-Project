"""QueryMarketDataTool for OpenSearch vector search with caching."""

import boto3
import json
import time
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from decimal import Decimal
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from botocore.exceptions import ClientError

from src.models.responses import MarketData
from src.error_handling import ErrorClassifier, ErrorCategory


class QueryMarketDataTool:
    """
    MCP Tool for querying market data using OpenSearch vector search.
    
    This tool performs knn vector search on OpenSearch Serverless,
    generates query embeddings using Bedrock Titan Embeddings,
    and implements caching with 5-minute TTL.
    """
    
    name: str = "query_market_data"
    description: str = "Search market data and news using vector similarity with caching"
    
    def __init__(
        self,
        opensearch_endpoint: str,
        index_name: str = "market-intelligence",
        cache_table_name: str = "MarketDataCache",
        region_name: str = "us-east-1",
        cache_ttl_seconds: int = 300  # 5 minutes
    ):
        """
        Initialize the QueryMarketDataTool.
        
        Args:
            opensearch_endpoint: OpenSearch Serverless endpoint URL
            index_name: Name of the OpenSearch index
            cache_table_name: Name of the DynamoDB cache table
            region_name: AWS region name
            cache_ttl_seconds: Cache TTL in seconds (default 300 = 5 minutes)
        """
        self.opensearch_endpoint = opensearch_endpoint
        self.index_name = index_name
        self.cache_table_name = cache_table_name
        self.region_name = region_name
        self.cache_ttl_seconds = cache_ttl_seconds
        
        # Initialize Bedrock client for embeddings
        self.bedrock_runtime = boto3.client('bedrock-runtime', region_name=region_name)
        
        # Initialize DynamoDB for caching
        self.dynamodb = boto3.resource('dynamodb', region_name=region_name)
        self.cache_table = self.dynamodb.Table(cache_table_name)
        
        # Initialize OpenSearch client
        credentials = boto3.Session().get_credentials()
        awsauth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            region_name,
            'aoss',
            session_token=credentials.token
        )
        
        self.opensearch_client = OpenSearch(
            hosts=[{'host': opensearch_endpoint.replace('https://', ''), 'port': 443}],
            http_auth=awsauth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=30
        )
    
    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector using Bedrock Titan Embeddings.
        
        Args:
            text: Text to generate embedding for
            
        Returns:
            List of floats representing the embedding vector
        """
        try:
            response = self.bedrock_runtime.invoke_model(
                modelId='amazon.titan-embed-text-v1',
                body=json.dumps({
                    'inputText': text
                })
            )
            
            response_body = json.loads(response['body'].read())
            embedding = response_body['embedding']
            
            return embedding
            
        except Exception as e:
            raise RuntimeError(f"Failed to generate embedding: {str(e)}")
    
    def _get_cache_key(self, query: str, filters: Dict) -> str:
        """
        Generate cache key from query and filters.
        
        Args:
            query: Search query text
            filters: Filter dictionary
            
        Returns:
            Cache key string
        """
        # Create deterministic cache key
        filters_str = json.dumps(filters, sort_keys=True) if filters else ""
        return f"market_data:{query}:{filters_str}"
    
    def _get_cached_results(self, cache_key: str) -> Optional[List[MarketData]]:
        """
        Retrieve cached results from DynamoDB.
        
        Args:
            cache_key: Cache key to lookup
            
        Returns:
            List of MarketData objects if cache hit and not expired, None otherwise
        """
        try:
            response = self.cache_table.get_item(
                Key={'data_key': cache_key}
            )
            
            if 'Item' not in response:
                return None
            
            item = response['Item']
            
            # Check if cache is still valid (TTL not expired)
            current_time = int(time.time())
            if item['ttl'] < current_time:
                return None
            
            # Deserialize cached results
            cached_data = item['cached_results']
            results = []
            
            for data_dict in cached_data:
                market_data = MarketData(
                    document_id=data_dict['document_id'],
                    document_type=data_dict['document_type'],
                    title=data_dict['title'],
                    content=data_dict['content'],
                    ticker=data_dict.get('ticker'),
                    sector=data_dict.get('sector'),
                    timestamp=data_dict['timestamp'],
                    source=data_dict['source'],
                    similarity_score=float(data_dict['similarity_score']),
                    metadata=data_dict.get('metadata', {})
                )
                results.append(market_data)
            
            return results
            
        except Exception:
            # If cache retrieval fails, continue without cache
            return None
    
    def _cache_results(self, cache_key: str, results: List[MarketData]):
        """
        Cache results in DynamoDB.
        
        Args:
            cache_key: Cache key
            results: List of MarketData objects to cache
        """
        try:
            # Serialize results
            cached_data = []
            for result in results:
                data_dict = {
                    'document_id': result.document_id,
                    'document_type': result.document_type,
                    'title': result.title,
                    'content': result.content,
                    'ticker': result.ticker,
                    'sector': result.sector,
                    'timestamp': result.timestamp,
                    'source': result.source,
                    'similarity_score': Decimal(str(result.similarity_score)),
                    'metadata': result.metadata
                }
                cached_data.append(data_dict)
            
            # Calculate TTL
            current_time = int(time.time())
            ttl = current_time + self.cache_ttl_seconds
            
            # Store in cache
            self.cache_table.put_item(
                Item={
                    'data_key': cache_key,
                    'cached_results': cached_data,
                    'timestamp': datetime.utcnow().isoformat(),
                    'cache_timestamp': current_time,
                    'ttl': ttl
                }
            )
            
        except Exception:
            # If caching fails, continue without caching
            pass
    
    def _get_stale_cached_results(self, cache_key: str) -> Optional[tuple]:
        """
        Retrieve stale cached results (expired cache) for fallback.
        
        Args:
            cache_key: Cache key to lookup
            
        Returns:
            Tuple of (results, data_age_seconds) if cache exists, None otherwise
        """
        try:
            response = self.cache_table.get_item(
                Key={'data_key': cache_key}
            )
            
            if 'Item' not in response:
                return None
            
            item = response['Item']
            
            # Calculate data age
            current_time = int(time.time())
            cache_timestamp = int(item.get('cache_timestamp', current_time))
            data_age_seconds = current_time - cache_timestamp
            
            # Deserialize cached results
            cached_data = item['cached_results']
            results = []
            
            for data_dict in cached_data:
                market_data = MarketData(
                    document_id=data_dict['document_id'],
                    document_type=data_dict['document_type'],
                    title=data_dict['title'],
                    content=data_dict['content'],
                    ticker=data_dict.get('ticker'),
                    sector=data_dict.get('sector'),
                    timestamp=data_dict['timestamp'],
                    source=data_dict['source'],
                    similarity_score=float(data_dict['similarity_score']),
                    metadata=data_dict.get('metadata', {})
                )
                results.append(market_data)
            
            return (results, data_age_seconds)
            
        except Exception:
            return None
    
    def execute(self, query: str, filters: Optional[Dict] = None, top_k: int = 10) -> tuple:
        """
        Query market data using vector search with caching and fallback.
        
        Args:
            query: Search query text
            filters: Optional filters (e.g., {'ticker': 'AAPL', 'sector': 'technology'})
            top_k: Number of results to return (default 10)
            
        Returns:
            Tuple of (results, metadata) where:
            - results: List of MarketData objects ranked by similarity score
            - metadata: Dict with 'is_cached', 'data_age_seconds', 'is_stale' flags
            
        Raises:
            ValueError: If query is empty or invalid
            RuntimeError: If search operation fails and no cache available
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        
        if top_k <= 0:
            raise ValueError(f"top_k must be positive, got {top_k}")
        
        filters = filters or {}
        
        # Check cache first
        cache_key = self._get_cache_key(query, filters)
        cached_results = self._get_cached_results(cache_key)
        
        if cached_results is not None:
            return (cached_results[:top_k], {
                'is_cached': True,
                'data_age_seconds': 0,
                'is_stale': False,
                'notification': None
            })
        
        try:
            # Generate query embedding
            query_embedding = self._generate_embedding(query)
            
            # Build OpenSearch query
            search_body = {
                'size': top_k,
                'query': {
                    'bool': {
                        'must': [
                            {
                                'knn': {
                                    'embedding': {
                                        'vector': query_embedding,
                                        'k': top_k
                                    }
                                }
                            }
                        ]
                    }
                }
            }
            
            # Add filters if provided
            if filters:
                filter_clauses = []
                for field, value in filters.items():
                    filter_clauses.append({'term': {field: value}})
                
                search_body['query']['bool']['filter'] = filter_clauses
            
            # Execute search
            response = self.opensearch_client.search(
                index=self.index_name,
                body=search_body
            )
            
            # Parse results
            results = []
            for hit in response['hits']['hits']:
                source = hit['_source']
                
                market_data = MarketData(
                    document_id=source['document_id'],
                    document_type=source['document_type'],
                    title=source['title'],
                    content=source['content'],
                    ticker=source.get('ticker'),
                    sector=source.get('sector'),
                    timestamp=source['timestamp'],
                    source=source['source'],
                    similarity_score=hit['_score'],
                    metadata=source.get('metadata', {})
                )
                results.append(market_data)
            
            # Cache results
            self._cache_results(cache_key, results)
            
            return (results, {
                'is_cached': False,
                'data_age_seconds': 0,
                'is_stale': False,
                'notification': None
            })
            
        except Exception as e:
            error_message = str(e)
            
            # Try to use stale cache as fallback
            stale_cache = self._get_stale_cached_results(cache_key)
            if stale_cache is not None:
                results, data_age_seconds = stale_cache
                notification = f"Live market data unavailable. Using cached data from {data_age_seconds} seconds ago."
                return (results[:top_k], {
                    'is_cached': True,
                    'data_age_seconds': data_age_seconds,
                    'is_stale': True,
                    'notification': notification
                })
            
            # Check if this is a transient error
            if any(keyword in error_message.lower() for keyword in ['timeout', 'unavailable', 'connection']):
                raise RuntimeError(f"Transient OpenSearch error: {error_message}")
            else:
                raise RuntimeError(f"Failed to query market data: {error_message}")
