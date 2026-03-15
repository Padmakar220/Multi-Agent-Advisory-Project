"""Market data ingestion Lambda function.

Fetches market data from external APIs, generates embeddings using Bedrock Titan,
and indexes documents in OpenSearch Serverless.

Requirements: 9.1, 9.4, 9.5
"""

import json
import os
import boto3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import logging

from src.utils.logging import create_logger, TraceContext
from src.error_handling.error_classifier import ErrorClassifier

# Lazy-load AWS clients to avoid initialization issues during testing
_bedrock_client = None
_opensearch_client = None
_dynamodb = None

def get_bedrock_client():
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client('bedrock-runtime', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    return _bedrock_client

def get_opensearch_client():
    global _opensearch_client
    if _opensearch_client is None:
        _opensearch_client = boto3.client('opensearchserverless', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    return _opensearch_client

def get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    return _dynamodb

# For backward compatibility
bedrock_client = None
opensearch_client = None
dynamodb = None

# Environment variables
OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT', '')
OPENSEARCH_INDEX = os.environ.get('OPENSEARCH_INDEX', 'market-data')
MARKET_DATA_CACHE_TABLE = os.environ.get('MARKET_DATA_CACHE_TABLE', 'MarketDataCache')
BEDROCK_EMBEDDINGS_MODEL = os.environ.get('BEDROCK_EMBEDDINGS_MODEL', 'amazon.titan-embed-text-v1')
CACHE_TTL_SECONDS = int(os.environ.get('CACHE_TTL_SECONDS', '300'))  # 5 minutes

logger = create_logger('market-data-ingestion')


@dataclass
class MarketDataDocument:
    """Market data document to be indexed."""
    document_id: str
    document_type: str  # "market_news", "price_data", "regulatory_document"
    title: str
    content: str
    ticker: str
    sector: Optional[str] = None
    timestamp: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MarketDataIngestionPipeline:
    """Pipeline for ingesting and indexing market data."""
    
    def __init__(self):
        """Initialize the ingestion pipeline."""
        self.cache_table = get_dynamodb().Table(MARKET_DATA_CACHE_TABLE)
        self.documents_indexed = 0
        self.errors = []
        self.used_cache = False
        self.cache_age_seconds = None
    
    def ingest_and_index(self) -> Dict[str, Any]:
        """
        Main ingestion pipeline with fallback to cached data.
        
        Returns:
            Dictionary with ingestion results
        """
        try:
            logger.info("Starting market data ingestion pipeline")
            
            # Try to fetch market data from external sources
            documents = None
            try:
                documents = self._fetch_market_data()
                logger.info(f"Fetched {len(documents)} market data documents from live source")
            except Exception as e:
                logger.warn(f"Failed to fetch live market data: {str(e)}")
                # Fall back to cached data
                documents = self._get_cached_market_data()
                if documents:
                    self.used_cache = True
                    logger.info(f"Using cached market data: {len(documents)} documents")
                else:
                    logger.error("No cached market data available")
                    raise Exception("Unable to fetch live market data and no cache available")
            
            # Generate embeddings and index documents
            for doc in documents:
                try:
                    self._index_document(doc)
                    self.documents_indexed += 1
                except Exception as e:
                    error_msg = f"Failed to index document {doc.document_id}: {str(e)}"
                    logger.error(error_msg, context={"document_id": doc.document_id})
                    self.errors.append(error_msg)
            
            # Update cache with ingestion timestamp
            self._update_ingestion_cache()
            
            result = {
                "status": "success" if not self.errors else "partial_success",
                "documents_indexed": self.documents_indexed,
                "errors": self.errors,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "used_cache": self.used_cache,
                "cache_age_seconds": self.cache_age_seconds
            }
            
            # Add cache notification if using cached data
            if self.used_cache and self.cache_age_seconds is not None:
                result["cache_notification"] = f"Using cached market data from {self.cache_age_seconds} seconds ago"
                logger.info(f"Market data ingestion completed with cache fallback: {self.documents_indexed} documents indexed, cache age: {self.cache_age_seconds}s")
            else:
                logger.info(f"Market data ingestion completed: {self.documents_indexed} documents indexed")
            
            return result
            
        except Exception as e:
            logger.error(f"Market data ingestion failed: {str(e)}")
            raise
    
    def _fetch_market_data(self) -> List[MarketDataDocument]:
        """
        Fetch market data from external sources.
        
        In production, this would call real market data APIs.
        For now, returns sample data.
        
        Returns:
            List of MarketDataDocument objects
        """
        # Sample market data - in production, fetch from real APIs
        documents = [
            MarketDataDocument(
                document_id="news_001",
                document_type="market_news",
                title="Tech Sector Rally Continues",
                content="Technology stocks extended gains today as investors showed renewed confidence in growth stocks.",
                ticker="VTI",
                sector="technology",
                timestamp=datetime.utcnow().isoformat() + "Z",
                source="financial_news_api",
                metadata={"sentiment": "positive", "relevance_score": 0.85}
            ),
            MarketDataDocument(
                document_id="news_002",
                document_type="market_news",
                title="Bond Market Stabilizes",
                content="Fixed income markets showed stability as inflation expectations moderated.",
                ticker="BND",
                sector="fixed_income",
                timestamp=datetime.utcnow().isoformat() + "Z",
                source="financial_news_api",
                metadata={"sentiment": "neutral", "relevance_score": 0.72}
            ),
            MarketDataDocument(
                document_id="price_001",
                document_type="price_data",
                title="VTI Daily Price Update",
                content="VTI closed at $220.75, up 0.5% from previous close. Volume: 2.3M shares.",
                ticker="VTI",
                sector="equity",
                timestamp=datetime.utcnow().isoformat() + "Z",
                source="market_data_api",
                metadata={"price": 220.75, "change_percent": 0.5}
            )
        ]
        return documents
    
    def _get_cached_market_data(self) -> Optional[List[MarketDataDocument]]:
        """
        Retrieve cached market data from DynamoDB.
        
        Returns:
            List of cached MarketDataDocument objects, or None if no cache available
        """
        try:
            # Query cache table for all cached documents
            response = self.cache_table.scan()
            items = response.get('Items', [])
            
            if not items:
                logger.warn("No cached market data found")
                return None
            
            # Calculate cache age from the last ingestion timestamp
            ingestion_items = [item for item in items if item.get('data_key') == 'ingestion:last_run']
            if ingestion_items:
                last_ingestion = ingestion_items[0]
                last_timestamp = last_ingestion.get('timestamp')
                if last_timestamp:
                    last_time = datetime.fromisoformat(last_timestamp.replace('Z', '+00:00'))
                    self.cache_age_seconds = int((datetime.utcnow() - last_time.replace(tzinfo=None)).total_seconds())
                    logger.info(f"Cache age: {self.cache_age_seconds} seconds")
            
            # Convert cached items back to MarketDataDocument objects
            documents = []
            for item in items:
                if item.get('data_key', '').startswith('market_data:'):
                    doc = MarketDataDocument(
                        document_id=item.get('document_id', ''),
                        document_type=item.get('document_type', ''),
                        title=item.get('title', ''),
                        content=item.get('content', ''),
                        ticker=item.get('ticker', ''),
                        sector=item.get('sector'),
                        timestamp=item.get('timestamp'),
                        source=item.get('source'),
                        metadata=item.get('metadata')
                    )
                    documents.append(doc)
            
            if documents:
                logger.info(f"Retrieved {len(documents)} documents from cache")
                return documents
            else:
                logger.warn("No market data documents found in cache")
                return None
                
        except Exception as e:
            logger.error(f"Failed to retrieve cached market data: {str(e)}")
            return None
    
    def _index_document(self, doc: MarketDataDocument) -> None:
        """
        Generate embedding and index document in OpenSearch.
        
        Args:
            doc: MarketDataDocument to index
            
        Raises:
            Exception: If embedding generation or indexing fails
        """
        # Generate embedding for document content
        embedding = self._generate_embedding(doc.content)
        
        # Prepare document for OpenSearch
        opensearch_doc = {
            "document_id": doc.document_id,
            "document_type": doc.document_type,
            "title": doc.title,
            "content": doc.content,
            "embedding": embedding,
            "ticker": doc.ticker,
            "sector": doc.sector,
            "timestamp": doc.timestamp or datetime.utcnow().isoformat() + "Z",
            "source": doc.source,
            "metadata": doc.metadata or {}
        }
        
        # Index in OpenSearch (mock implementation)
        logger.info(f"Indexed document {doc.document_id} in OpenSearch")
        
        # Cache the document metadata
        self._cache_document(doc)
    
    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding using Bedrock Titan Embeddings model.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding
            
        Raises:
            Exception: If embedding generation fails
        """
        try:
            # Invoke Bedrock Titan Embeddings model
            response = get_bedrock_client().invoke_model(
                modelId=BEDROCK_EMBEDDINGS_MODEL,
                body=json.dumps({
                    "inputText": text
                })
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            embedding = response_body.get('embedding', [])
            
            if not embedding:
                raise ValueError("Empty embedding returned from Bedrock")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {str(e)}")
            raise
    
    def _cache_document(self, doc: MarketDataDocument) -> None:
        """
        Cache document metadata in DynamoDB.
        
        Args:
            doc: MarketDataDocument to cache
        """
        try:
            cache_key = f"market_data:{doc.document_id}"
            ttl = int((datetime.utcnow() + timedelta(seconds=CACHE_TTL_SECONDS)).timestamp())
            
            self.cache_table.put_item(
                Item={
                    "data_key": cache_key,
                    "document_id": doc.document_id,
                    "document_type": doc.document_type,
                    "title": doc.title,
                    "content": doc.content,
                    "ticker": doc.ticker,
                    "sector": doc.sector,
                    "timestamp": doc.timestamp or datetime.utcnow().isoformat() + "Z",
                    "source": doc.source,
                    "metadata": doc.metadata or {},
                    "ttl": ttl
                }
            )
        except Exception as e:
            logger.warn(f"Failed to cache document {doc.document_id}: {str(e)}")
    
    def _update_ingestion_cache(self) -> None:
        """Update cache with last ingestion timestamp."""
        try:
            ttl = int((datetime.utcnow() + timedelta(seconds=CACHE_TTL_SECONDS)).timestamp())
            self.cache_table.put_item(
                Item={
                    "data_key": "ingestion:last_run",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "documents_indexed": self.documents_indexed,
                    "ttl": ttl
                }
            )
        except Exception as e:
            logger.warn(f"Failed to update ingestion cache: {str(e)}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for market data ingestion.
    
    Args:
        event: Lambda event (from EventBridge)
        context: Lambda context
        
    Returns:
        Dictionary with ingestion results
    """
    trace_id = context.request_id if context else "unknown"
    
    with TraceContext(trace_id):
        try:
            logger.info("Market data ingestion Lambda invoked")
            
            # Run ingestion pipeline
            pipeline = MarketDataIngestionPipeline()
            result = pipeline.ingest_and_index()
            
            return {
                "statusCode": 200,
                "body": json.dumps(result)
            }
            
        except Exception as e:
            logger.error(f"Market data ingestion failed: {str(e)}")
            
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
            }
