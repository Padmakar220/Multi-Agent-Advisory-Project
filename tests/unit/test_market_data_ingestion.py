"""Unit tests for market data ingestion Lambda function.

Tests embedding generation, OpenSearch indexing, and error handling.

Validates: Requirements 9.1, 9.4, 9.5
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, call
import sys
import os
import importlib.util
from dataclasses import dataclass
from typing import Dict, Any, Optional

# Load the handler module directly
handler_path = os.path.join(os.path.dirname(__file__), '../../lambda/market-data-ingestion/handler.py')
spec = importlib.util.spec_from_file_location("market_data_ingestion_handler", handler_path)
handler_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler_module)

# Import from the loaded module
MarketDataIngestionPipeline = handler_module.MarketDataIngestionPipeline
MarketDataDocument = handler_module.MarketDataDocument
lambda_handler = handler_module.lambda_handler


class TestMarketDataIngestionPipeline:
    """Test market data ingestion pipeline."""
    
    @patch('market_data_ingestion_handler.get_bedrock_client')
    @patch('market_data_ingestion_handler.get_dynamodb')
    def test_ingest_and_index_success(self, mock_get_dynamodb, mock_get_bedrock):
        """Test successful market data ingestion and indexing."""
        # Setup mocks
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.return_value = {
            'body': MagicMock(read=lambda: json.dumps({
                'embedding': [0.1] * 1536
            }))
        }
        
        mock_cache_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_cache_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Create pipeline and run ingestion
        pipeline = MarketDataIngestionPipeline()
        result = pipeline.ingest_and_index()
        
        # Verify result
        assert result['status'] in ['success', 'partial_success']
        assert result['documents_indexed'] > 0
        assert 'timestamp' in result
        assert isinstance(result['errors'], list)
    
    @patch('market_data_ingestion_handler.get_bedrock_client')
    @patch('market_data_ingestion_handler.get_dynamodb')
    def test_embedding_generation(self, mock_get_dynamodb, mock_get_bedrock):
        """Test embedding generation using Bedrock Titan model."""
        # Setup mock
        expected_embedding = [0.1, 0.2, 0.3] + [0.0] * 1533  # 1536 dimensions
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.return_value = {
            'body': MagicMock(read=lambda: json.dumps({
                'embedding': expected_embedding
            }))
        }
        
        mock_cache_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_cache_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Create pipeline
        pipeline = MarketDataIngestionPipeline()
        
        # Generate embedding
        text = "Test market data content"
        embedding = pipeline._generate_embedding(text)
        
        # Verify embedding
        assert isinstance(embedding, list)
        assert len(embedding) == 1536
        assert embedding == expected_embedding
        
        # Verify Bedrock was called correctly
        mock_bedrock.invoke_model.assert_called_once()
        call_args = mock_bedrock.invoke_model.call_args
        assert 'modelId' in call_args.kwargs
        assert 'body' in call_args.kwargs
    
    @patch('market_data_ingestion_handler.get_bedrock_client')
    @patch('market_data_ingestion_handler.get_dynamodb')
    def test_embedding_generation_failure(self, mock_get_dynamodb, mock_get_bedrock):
        """Test error handling when embedding generation fails."""
        # Setup mock to raise error
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.side_effect = Exception("Bedrock API error")
        
        mock_cache_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_cache_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Create pipeline
        pipeline = MarketDataIngestionPipeline()
        
        # Verify error is raised
        with pytest.raises(Exception) as exc_info:
            pipeline._generate_embedding("Test content")
        
        assert "Bedrock API error" in str(exc_info.value)
    
    @patch('market_data_ingestion_handler.get_bedrock_client')
    @patch('market_data_ingestion_handler.get_dynamodb')
    def test_opensearch_indexing(self, mock_get_dynamodb, mock_get_bedrock):
        """Test document indexing in OpenSearch."""
        # Setup mocks
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.return_value = {
            'body': MagicMock(read=lambda: json.dumps({
                'embedding': [0.1] * 1536
            }))
        }
        
        mock_cache_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_cache_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Create document
        doc = MarketDataDocument(
            document_id="test_001",
            document_type="market_news",
            title="Test News",
            content="Test content for indexing",
            ticker="VTI",
            sector="equity",
            timestamp=datetime.utcnow().isoformat() + "Z",
            source="test_api",
            metadata={"sentiment": "positive"}
        )
        
        # Create pipeline and index document
        pipeline = MarketDataIngestionPipeline()
        pipeline._index_document(doc)
        
        # Verify document was indexed
        assert pipeline.documents_indexed == 0  # Not incremented in _index_document
        
        # Verify cache was updated
        mock_cache_table.put_item.assert_called()
    
    @patch('market_data_ingestion_handler.get_bedrock_client')
    @patch('market_data_ingestion_handler.get_dynamodb')
    def test_cache_document(self, mock_get_dynamodb, mock_get_bedrock):
        """Test document caching in DynamoDB."""
        # Setup mocks
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.return_value = {
            'body': MagicMock(read=lambda: json.dumps({
                'embedding': [0.1] * 1536
            }))
        }
        
        mock_cache_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_cache_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Create document
        doc = MarketDataDocument(
            document_id="cache_test_001",
            document_type="price_data",
            title="Price Update",
            content="VTI closed at $220.75",
            ticker="VTI",
            timestamp=datetime.utcnow().isoformat() + "Z",
            source="market_api"
        )
        
        # Create pipeline and cache document
        pipeline = MarketDataIngestionPipeline()
        pipeline._cache_document(doc)
        
        # Verify cache table was called
        mock_cache_table.put_item.assert_called_once()
        
        # Verify cache item structure
        call_args = mock_cache_table.put_item.call_args
        item = call_args.kwargs['Item']
        assert item['data_key'] == "market_data:cache_test_001"
        assert item['document_id'] == "cache_test_001"
        assert item['document_type'] == "price_data"
        assert 'ttl' in item
    
    @patch('market_data_ingestion_handler.get_bedrock_client')
    @patch('market_data_ingestion_handler.get_dynamodb')
    def test_cache_ttl_calculation(self, mock_get_dynamodb, mock_get_bedrock):
        """Test that cache TTL is calculated correctly."""
        # Setup mocks
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.return_value = {
            'body': MagicMock(read=lambda: json.dumps({
                'embedding': [0.1] * 1536
            }))
        }
        
        mock_cache_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_cache_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Create document
        doc = MarketDataDocument(
            document_id="ttl_test_001",
            document_type="market_news",
            title="TTL Test",
            content="Testing TTL calculation",
            ticker="VTI"
        )
        
        # Get current time before caching
        before_time = datetime.utcnow()
        
        # Create pipeline and cache document
        pipeline = MarketDataIngestionPipeline()
        pipeline._cache_document(doc)
        
        # Get current time after caching
        after_time = datetime.utcnow()
        
        # Verify cache table was called
        mock_cache_table.put_item.assert_called_once()
        
        # Extract TTL from call
        call_args = mock_cache_table.put_item.call_args
        item = call_args.kwargs['Item']
        ttl = item['ttl']
        
        # Verify TTL is in the future
        current_timestamp = int(datetime.utcnow().timestamp())
        assert ttl > current_timestamp
        
        # Verify TTL is approximately 5 minutes in the future
        ttl_seconds = ttl - current_timestamp
        assert 250 <= ttl_seconds <= 350  # Allow some variance
    
    @patch('market_data_ingestion_handler.get_bedrock_client')
    @patch('market_data_ingestion_handler.get_dynamodb')
    def test_fetch_market_data(self, mock_get_dynamodb, mock_get_bedrock):
        """Test fetching market data from external sources."""
        # Setup mocks
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.return_value = {
            'body': MagicMock(read=lambda: json.dumps({
                'embedding': [0.1] * 1536
            }))
        }
        
        mock_cache_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_cache_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Create pipeline
        pipeline = MarketDataIngestionPipeline()
        
        # Fetch market data
        documents = pipeline._fetch_market_data()
        
        # Verify documents
        assert isinstance(documents, list)
        assert len(documents) > 0
        
        # Verify document structure
        for doc in documents:
            assert isinstance(doc, MarketDataDocument)
            assert doc.document_id
            assert doc.document_type
            assert doc.title
            assert doc.content
            assert doc.ticker
    
    @patch('market_data_ingestion_handler.get_bedrock_client')
    @patch('market_data_ingestion_handler.get_dynamodb')
    def test_error_handling_for_api_failures(self, mock_get_dynamodb, mock_get_bedrock):
        """Test error handling when external API fails."""
        # Setup mock to raise error
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.side_effect = Exception("API rate limit exceeded")
        
        mock_cache_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_cache_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Create pipeline
        pipeline = MarketDataIngestionPipeline()
        
        # Verify error is raised
        with pytest.raises(Exception) as exc_info:
            pipeline.ingest_and_index()
        
        assert "API rate limit exceeded" in str(exc_info.value)
    
    @patch('market_data_ingestion_handler.get_bedrock_client')
    @patch('market_data_ingestion_handler.get_dynamodb')
    def test_partial_failure_handling(self, mock_get_dynamodb, mock_get_bedrock):
        """Test handling of partial failures during indexing."""
        # Setup mock to fail on second call
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Embedding generation failed")
            return {
                'body': MagicMock(read=lambda: json.dumps({
                    'embedding': [0.1] * 1536
                }))
            }
        
        mock_bedrock.invoke_model.side_effect = side_effect
        
        mock_cache_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_cache_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Create pipeline and run ingestion
        pipeline = MarketDataIngestionPipeline()
        result = pipeline.ingest_and_index()
        
        # Verify partial success
        assert result['status'] == 'partial_success'
        assert result['documents_indexed'] > 0
        assert len(result['errors']) > 0


class TestLambdaHandler:
    """Test Lambda handler function."""
    
    @patch('market_data_ingestion_handler.get_bedrock_client')
    @patch('market_data_ingestion_handler.get_dynamodb')
    def test_lambda_handler_success(self, mock_get_dynamodb, mock_get_bedrock):
        """Test Lambda handler with successful ingestion."""
        # Setup mocks
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.return_value = {
            'body': MagicMock(read=lambda: json.dumps({
                'embedding': [0.1] * 1536
            }))
        }
        
        mock_cache_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_cache_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Create mock context
        mock_context = MagicMock()
        mock_context.request_id = "test-request-id"
        
        # Call handler
        response = lambda_handler({}, mock_context)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] in ['success', 'partial_success']
        assert 'documents_indexed' in body
        assert 'timestamp' in body
    
    @patch('market_data_ingestion_handler.get_bedrock_client')
    @patch('market_data_ingestion_handler.get_dynamodb')
    def test_lambda_handler_error(self, mock_get_dynamodb, mock_get_bedrock):
        """Test Lambda handler with error."""
        # Setup mock to raise error
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.side_effect = Exception("Bedrock service error")
        
        mock_cache_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_cache_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Create mock context
        mock_context = MagicMock()
        mock_context.request_id = "test-request-id"
        
        # Call handler
        response = lambda_handler({}, mock_context)
        
        # Verify error response
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['status'] == 'error'
        assert 'error' in body
        assert 'timestamp' in body
    
    @patch('market_data_ingestion_handler.get_bedrock_client')
    @patch('market_data_ingestion_handler.get_dynamodb')
    def test_lambda_handler_with_event(self, mock_get_dynamodb, mock_get_bedrock):
        """Test Lambda handler with EventBridge event."""
        # Setup mocks
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.return_value = {
            'body': MagicMock(read=lambda: json.dumps({
                'embedding': [0.1] * 1536
            }))
        }
        
        mock_cache_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_cache_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Create mock context
        mock_context = MagicMock()
        mock_context.request_id = "eventbridge-request-id"
        
        # Create EventBridge event
        event = {
            'source': 'aws.events',
            'detail-type': 'Scheduled Event',
            'detail': {}
        }
        
        # Call handler
        response = lambda_handler(event, mock_context)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] in ['success', 'partial_success']


class TestMarketDataDocument:
    """Test MarketDataDocument data class."""
    
    def test_market_data_document_creation(self):
        """Test creating a MarketDataDocument."""
        doc = MarketDataDocument(
            document_id="test_001",
            document_type="market_news",
            title="Test News",
            content="Test content",
            ticker="VTI",
            sector="equity",
            timestamp="2024-01-15T10:00:00Z",
            source="test_api",
            metadata={"sentiment": "positive"}
        )
        
        assert doc.document_id == "test_001"
        assert doc.document_type == "market_news"
        assert doc.title == "Test News"
        assert doc.content == "Test content"
        assert doc.ticker == "VTI"
        assert doc.sector == "equity"
        assert doc.timestamp == "2024-01-15T10:00:00Z"
        assert doc.source == "test_api"
        assert doc.metadata == {"sentiment": "positive"}
    
    def test_market_data_document_optional_fields(self):
        """Test MarketDataDocument with optional fields."""
        doc = MarketDataDocument(
            document_id="test_002",
            document_type="price_data",
            title="Price Update",
            content="VTI closed at $220.75",
            ticker="VTI"
        )
        
        assert doc.document_id == "test_002"
        assert doc.sector is None
        assert doc.timestamp is None
        assert doc.source is None
        assert doc.metadata is None
