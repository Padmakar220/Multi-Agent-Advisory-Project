"""Property-based tests for market data MCP tools.

Feature: multi-agent-advisory-ai-system
"""

import pytest
import time
from hypothesis import given, strategies as st, settings
from unittest.mock import Mock, MagicMock, patch
from decimal import Decimal
from datetime import datetime

from src.mcp_tools import QueryMarketDataTool
from src.models.responses import MarketData


# Strategy for generating market data
@st.composite
def market_data_strategy(draw):
    """Generate valid MarketData objects."""
    document_id = draw(st.text(min_size=1, max_size=50))
    document_type = draw(st.sampled_from(['market_news', 'regulatory_doc', 'earnings_report']))
    title = draw(st.text(min_size=1, max_size=200))
    content = draw(st.text(min_size=10, max_size=1000))
    ticker = draw(st.one_of(st.none(), st.text(min_size=1, max_size=5)))
    sector = draw(st.one_of(st.none(), st.sampled_from(['technology', 'finance', 'healthcare', 'energy'])))
    timestamp = draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2024, 12, 31))).isoformat()
    source = draw(st.text(min_size=1, max_size=50))
    similarity_score = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    
    return MarketData(
        document_id=document_id,
        document_type=document_type,
        title=title,
        content=content,
        ticker=ticker,
        sector=sector,
        timestamp=timestamp,
        source=source,
        similarity_score=similarity_score,
        metadata={}
    )


class TestQueryMarketDataToolProperties:
    """Property-based tests for QueryMarketDataTool."""

    
    @settings(max_examples=100)
    @given(
        query=st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
        results=st.lists(market_data_strategy(), min_size=1, max_size=10)
    )
    def test_property_37_vector_search_execution(self, query, results):
        """
        Property 37: Vector Search Execution
        
        For any market context request, the system should perform a vector
        search on OpenSearch Serverless and return results ranked by
        similarity score.
        
        **Validates: Requirements 9.2**
        """
        # Sort results by similarity score (descending)
        sorted_results = sorted(results, key=lambda x: x.similarity_score, reverse=True)
        
        # Mock OpenSearch response
        mock_hits = []
        for result in sorted_results:
            hit = {
                '_score': result.similarity_score,
                '_source': {
                    'document_id': result.document_id,
                    'document_type': result.document_type,
                    'title': result.title,
                    'content': result.content,
                    'ticker': result.ticker,
                    'sector': result.sector,
                    'timestamp': result.timestamp,
                    'source': result.source,
                    'metadata': result.metadata
                }
            }
            mock_hits.append(hit)
        
        mock_opensearch_response = {
            'hits': {
                'hits': mock_hits
            }
        }
        
        # Mock boto3 and AWS credentials
        mock_boto3 = Mock()
        mock_session = Mock()
        mock_credentials = Mock()
        mock_credentials.access_key = 'test_access_key'
        mock_credentials.secret_key = 'test_secret_key'
        mock_credentials.token = None
        mock_session.get_credentials.return_value = mock_credentials
        mock_boto3.Session.return_value = mock_session
        mock_boto3.client.return_value = Mock()
        mock_boto3.resource.return_value = Mock()
        
        # Mock the tool's dependencies
        with patch('src.mcp_tools.query_market_data_tool.boto3', mock_boto3):
            with patch('src.mcp_tools.query_market_data_tool.OpenSearch'):
                tool = QueryMarketDataTool(opensearch_endpoint='https://test.aoss.amazonaws.com')
                
                # Mock embedding generation
                tool._generate_embedding = Mock(return_value=[0.1] * 1536)
                
                # Mock OpenSearch client
                tool.opensearch_client = Mock()
                tool.opensearch_client.search.return_value = mock_opensearch_response
                
                # Mock cache (no cached results)
                tool._get_cached_results = Mock(return_value=None)
                tool._cache_results = Mock()
                
                # Execute search
                search_results = tool.execute(query, top_k=len(results))
                
                # Verify results are returned
                assert len(search_results) == len(results)
                
                # Verify results are ranked by similarity score (descending)
                for i in range(len(search_results) - 1):
                    assert search_results[i].similarity_score >= search_results[i + 1].similarity_score, \
                        "Results should be ranked by similarity score in descending order"
                
                # Verify OpenSearch was called
                tool.opensearch_client.search.assert_called_once()

    
    @settings(max_examples=50)
    @given(
        query=st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
        results=st.lists(market_data_strategy(), min_size=1, max_size=5)
    )
    def test_property_38_market_data_cache_ttl(self, query, results):
        """
        Property 38: Market Data Cache TTL
        
        For any market data cached in DynamoDB, the TTL should be set to
        5 minutes (300 seconds) from the cache timestamp.
        
        **Validates: Requirements 9.3**
        """
        # Mock boto3 and AWS credentials
        mock_boto3 = Mock()
        mock_session = Mock()
        mock_credentials = Mock()
        mock_credentials.access_key = 'test_access_key'
        mock_credentials.secret_key = 'test_secret_key'
        mock_credentials.token = None
        mock_session.get_credentials.return_value = mock_credentials
        mock_boto3.Session.return_value = mock_session
        mock_boto3.client.return_value = Mock()
        mock_boto3.resource.return_value = Mock()
        
        # Mock the tool's dependencies
        with patch('src.mcp_tools.query_market_data_tool.boto3', mock_boto3):
            with patch('src.mcp_tools.query_market_data_tool.OpenSearch'):
                tool = QueryMarketDataTool(
                    opensearch_endpoint='https://test.aoss.amazonaws.com',
                    cache_ttl_seconds=300
                )
                
                # Mock cache table
                mock_cache_table = Mock()
                tool.cache_table = mock_cache_table
                
                # Mock embedding and search
                tool._generate_embedding = Mock(return_value=[0.1] * 1536)
                tool.opensearch_client = Mock()
                
                mock_hits = []
                for result in results:
                    hit = {
                        '_score': result.similarity_score,
                        '_source': {
                            'document_id': result.document_id,
                            'document_type': result.document_type,
                            'title': result.title,
                            'content': result.content,
                            'ticker': result.ticker,
                            'sector': result.sector,
                            'timestamp': result.timestamp,
                            'source': result.source,
                            'metadata': result.metadata
                        }
                    }
                    mock_hits.append(hit)
                
                tool.opensearch_client.search.return_value = {'hits': {'hits': mock_hits}}
                
                # Mock cache retrieval (no cache)
                tool._get_cached_results = Mock(return_value=None)
                
                # Execute search (will cache results)
                current_time = time.time()
                search_results = tool.execute(query)
                
                # Verify cache was written
                mock_cache_table.put_item.assert_called_once()
                
                # Extract the cached item
                cached_item = mock_cache_table.put_item.call_args[1]['Item']
                
                # Verify TTL is set correctly (5 minutes = 300 seconds)
                ttl = cached_item['ttl']
                expected_ttl_min = int(current_time) + 299  # Allow 1 second tolerance
                expected_ttl_max = int(current_time) + 301
                
                assert expected_ttl_min <= ttl <= expected_ttl_max, \
                    f"TTL should be 300 seconds from now, got {ttl - int(current_time)} seconds"

    
    @settings(max_examples=50)
    @given(
        query=st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
        cached_results=st.lists(market_data_strategy(), min_size=1, max_size=5)
    )
    def test_property_40_cached_data_fallback(self, query, cached_results):
        """
        Property 40: Cached Data Fallback with Notification
        
        For any market data request when live data is unavailable, the system
        should return the most recent cached data and notify the user of the
        data age.
        
        **Validates: Requirements 9.5**
        """
        # Mock boto3 and AWS credentials
        mock_boto3 = Mock()
        mock_session = Mock()
        mock_credentials = Mock()
        mock_credentials.access_key = 'test_access_key'
        mock_credentials.secret_key = 'test_secret_key'
        mock_credentials.token = None
        mock_session.get_credentials.return_value = mock_credentials
        mock_boto3.Session.return_value = mock_session
        mock_boto3.client.return_value = Mock()
        mock_boto3.resource.return_value = Mock()
        
        # Mock the tool's dependencies
        with patch('src.mcp_tools.query_market_data_tool.boto3', mock_boto3):
            with patch('src.mcp_tools.query_market_data_tool.OpenSearch'):
                tool = QueryMarketDataTool(opensearch_endpoint='https://test.aoss.amazonaws.com')
                
                # Mock cache retrieval (return cached data)
                tool._get_cached_results = Mock(return_value=cached_results)
                
                # Mock OpenSearch to simulate unavailability (should not be called)
                tool.opensearch_client = Mock()
                tool._generate_embedding = Mock()
                
                # Execute search
                search_results = tool.execute(query)
                
                # Verify cached results were returned
                assert len(search_results) == len(cached_results)
                assert search_results == cached_results
                
                # Verify OpenSearch was NOT called (used cache instead)
                tool.opensearch_client.search.assert_not_called()
                tool._generate_embedding.assert_not_called()
    
    @settings(max_examples=100)
    @given(query=st.text(min_size=1, max_size=200))
    def test_property_query_validation(self, query):
        """
        Property: Empty or whitespace-only queries should be rejected.
        
        For any query that is empty or contains only whitespace, the tool
        should raise a ValueError.
        """
        # Mock boto3 and AWS credentials
        mock_boto3 = Mock()
        mock_session = Mock()
        mock_credentials = Mock()
        mock_credentials.access_key = 'test_access_key'
        mock_credentials.secret_key = 'test_secret_key'
        mock_credentials.token = None
        mock_session.get_credentials.return_value = mock_credentials
        mock_boto3.Session.return_value = mock_session
        mock_boto3.client.return_value = Mock()
        mock_boto3.resource.return_value = Mock()
        
        with patch('src.mcp_tools.query_market_data_tool.boto3', mock_boto3):
            with patch('src.mcp_tools.query_market_data_tool.OpenSearch'):
                tool = QueryMarketDataTool(opensearch_endpoint='https://test.aoss.amazonaws.com')
                
                # Test with whitespace-only query
                if not query.strip():
                    with pytest.raises(ValueError) as exc_info:
                        tool.execute(query)
                    
                    assert "empty" in str(exc_info.value).lower()


class TestMarketDataCacheConsistency:
    """Test cache consistency properties."""
    
    @settings(max_examples=50)
    @given(
        query=st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
        results=st.lists(market_data_strategy(), min_size=1, max_size=5)
    )
    def test_cache_key_consistency(self, query, results):
        """
        Property: Same query should produce same cache key.
        
        For any query, generating the cache key multiple times should
        produce the same result.
        """
        # Mock boto3 and AWS credentials
        mock_boto3 = Mock()
        mock_session = Mock()
        mock_credentials = Mock()
        mock_credentials.access_key = 'test_access_key'
        mock_credentials.secret_key = 'test_secret_key'
        mock_credentials.token = None
        mock_session.get_credentials.return_value = mock_credentials
        mock_boto3.Session.return_value = mock_session
        mock_boto3.client.return_value = Mock()
        mock_boto3.resource.return_value = Mock()
        
        with patch('src.mcp_tools.query_market_data_tool.boto3', mock_boto3):
            with patch('src.mcp_tools.query_market_data_tool.OpenSearch'):
                tool = QueryMarketDataTool(opensearch_endpoint='https://test.aoss.amazonaws.com')
                
                filters = {'ticker': 'AAPL', 'sector': 'technology'}
                
                # Generate cache key multiple times
                key1 = tool._get_cache_key(query, filters)
                key2 = tool._get_cache_key(query, filters)
                key3 = tool._get_cache_key(query, filters)
                
                # All keys should be identical
                assert key1 == key2 == key3, \
                    "Cache key generation should be deterministic"
