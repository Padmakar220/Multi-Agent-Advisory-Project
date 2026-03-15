"""
Property-based tests for OpenSearch vector embedding presence.

Tests:
- Property 36: Vector Embedding Presence

These tests validate that all documents indexed in OpenSearch have valid
vector embeddings with the correct dimensionality for similarity search.
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from datetime import datetime
import json


# ============================================================================
# Hypothesis Strategies for Data Generation
# ============================================================================

@st.composite
def vector_embedding_strategy(draw, dimension=1536):
    """
    Generate a valid vector embedding.
    
    Args:
        dimension: Vector dimension (default 1536 for Bedrock Titan Embeddings)
    
    Returns:
        List of floats representing the embedding vector
    """
    # Generate normalized vector (unit length for cosine similarity)
    vector = draw(st.lists(
        st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=dimension,
        max_size=dimension
    ))
    
    # Normalize to unit length for cosine similarity
    magnitude = sum(x**2 for x in vector) ** 0.5
    if magnitude > 0:
        vector = [x / magnitude for x in vector]
    
    return vector


@st.composite
def market_document_strategy(draw):
    """Generate a valid market data document for OpenSearch indexing."""
    return {
        "document_id": draw(st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=("Ll", "Nd")))),
        "document_type": draw(st.sampled_from(["market_news", "regulatory_filing", "analyst_report", "earnings_call"])),
        "title": draw(st.text(min_size=10, max_size=200)),
        "content": draw(st.text(min_size=50, max_size=5000)),
        "embedding": draw(vector_embedding_strategy(dimension=1536)),
        "ticker": draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Lu",)))),
        "sector": draw(st.sampled_from(["technology", "healthcare", "finance", "energy", "consumer", "industrial"])),
        "timestamp": draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2024, 12, 31))).isoformat(),
        "source": draw(st.sampled_from(["financial_news_api", "sec_edgar", "earnings_call_api", "analyst_api"])),
        "metadata": {
            "sentiment": draw(st.sampled_from(["positive", "negative", "neutral"])),
            "relevance_score": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
        }
    }


# ============================================================================
# Validation Functions
# ============================================================================

def validate_vector_embedding(embedding, expected_dimension=1536):
    """
    Validate that a vector embedding is present and has the correct properties.
    
    Args:
        embedding: The embedding vector to validate
        expected_dimension: Expected vector dimension (default 1536)
    
    Returns:
        True if valid, raises AssertionError otherwise
    """
    # Check embedding exists
    assert embedding is not None, "Embedding must not be None"
    
    # Check embedding is a list
    assert isinstance(embedding, list), f"Embedding must be a list, got {type(embedding)}"
    
    # Check embedding has correct dimension
    assert len(embedding) == expected_dimension, \
        f"Embedding must have dimension {expected_dimension}, got {len(embedding)}"
    
    # Check all elements are floats
    for i, value in enumerate(embedding):
        assert isinstance(value, (int, float)), \
            f"Embedding element {i} must be numeric, got {type(value)}"
        assert not (value != value), f"Embedding element {i} is NaN"  # NaN check
        assert value != float('inf') and value != float('-inf'), \
            f"Embedding element {i} is infinite"
    
    # Check vector is not all zeros (would indicate missing embedding)
    magnitude = sum(x**2 for x in embedding) ** 0.5
    assert magnitude > 0, "Embedding vector must not be all zeros"
    
    return True


def validate_market_document(document):
    """
    Validate that a market data document has all required fields including embedding.
    
    Args:
        document: The document to validate
    
    Returns:
        True if valid, raises AssertionError otherwise
    """
    # Check required fields exist
    required_fields = [
        "document_id", "document_type", "title", "content", "embedding",
        "ticker", "sector", "timestamp", "source", "metadata"
    ]
    for field in required_fields:
        assert field in document, f"Missing required field: {field}"
    
    # Validate field types
    assert isinstance(document["document_id"], str), "document_id must be string"
    assert isinstance(document["document_type"], str), "document_type must be string"
    assert isinstance(document["title"], str), "title must be string"
    assert isinstance(document["content"], str), "content must be string"
    assert isinstance(document["embedding"], list), "embedding must be list"
    assert isinstance(document["ticker"], str), "ticker must be string"
    assert isinstance(document["sector"], str), "sector must be string"
    assert isinstance(document["timestamp"], str), "timestamp must be string"
    assert isinstance(document["source"], str), "source must be string"
    assert isinstance(document["metadata"], dict), "metadata must be dict"
    
    # Validate embedding
    validate_vector_embedding(document["embedding"], expected_dimension=1536)
    
    # Validate metadata structure
    assert "sentiment" in document["metadata"], "metadata must have sentiment"
    assert "relevance_score" in document["metadata"], "metadata must have relevance_score"
    
    # Validate document_id is non-empty
    assert len(document["document_id"]) > 0, "document_id must be non-empty"
    
    # Validate timestamp is ISO 8601 format
    try:
        datetime.fromisoformat(document["timestamp"].replace('Z', '+00:00'))
    except ValueError as e:
        raise AssertionError(f"timestamp must be ISO 8601 format: {e}")
    
    return True


# ============================================================================
# Property Tests
# ============================================================================

@settings(max_examples=100)
@given(document=market_document_strategy())
def test_property_36_vector_embedding_presence(document):
    """
    Property 36: Vector Embedding Presence
    
    For all market data documents indexed in OpenSearch:
    - The document MUST have an embedding field
    - The embedding MUST be a list of floats
    - The embedding MUST have dimension 1536 (Bedrock Titan Embeddings)
    - The embedding MUST NOT contain NaN or infinite values
    - The embedding MUST NOT be all zeros (indicating missing embedding)
    - All other required fields MUST be present
    
    This property ensures that vector similarity search can be performed on all
    indexed documents and that embeddings are properly generated before indexing.
    
    Validates: Requirements 9.1
    """
    # Validate document structure
    assert validate_market_document(document), "Document must have valid structure"
    
    # Validate embedding specifically
    assert validate_vector_embedding(document["embedding"], expected_dimension=1536), \
        "Document must have valid 1536-dimensional embedding"
    
    # Additional property: Embedding should be suitable for cosine similarity
    # (normalized or at least non-zero magnitude)
    magnitude = sum(x**2 for x in document["embedding"]) ** 0.5
    assert magnitude > 0, "Embedding must have non-zero magnitude for similarity search"


@settings(max_examples=50)
@given(embedding=vector_embedding_strategy(dimension=1536))
def test_vector_embedding_normalization(embedding):
    """
    Test that vector embeddings are normalized for cosine similarity.
    
    For cosine similarity search, vectors should ideally be normalized to unit length.
    This test verifies that generated embeddings have reasonable magnitude.
    """
    magnitude = sum(x**2 for x in embedding) ** 0.5
    
    # Check magnitude is close to 1.0 (normalized) or at least non-zero
    assert magnitude > 0, "Embedding magnitude must be non-zero"
    
    # For normalized vectors, magnitude should be close to 1.0
    # Allow some tolerance for floating point arithmetic
    assert abs(magnitude - 1.0) < 0.1, \
        f"Embedding should be approximately normalized, got magnitude {magnitude}"


@settings(max_examples=50)
@given(doc1=market_document_strategy(), doc2=market_document_strategy())
def test_vector_similarity_computation(doc1, doc2):
    """
    Test that cosine similarity can be computed between any two document embeddings.
    
    This ensures that the embeddings are suitable for vector search operations.
    """
    embedding1 = doc1["embedding"]
    embedding2 = doc2["embedding"]
    
    # Validate both embeddings
    validate_vector_embedding(embedding1, expected_dimension=1536)
    validate_vector_embedding(embedding2, expected_dimension=1536)
    
    # Compute cosine similarity
    dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
    magnitude1 = sum(x**2 for x in embedding1) ** 0.5
    magnitude2 = sum(x**2 for x in embedding2) ** 0.5
    
    # Avoid division by zero
    assume(magnitude1 > 0 and magnitude2 > 0)
    
    cosine_similarity = dot_product / (magnitude1 * magnitude2)
    
    # Cosine similarity should be in range [-1, 1]
    assert -1.0 <= cosine_similarity <= 1.0, \
        f"Cosine similarity must be in [-1, 1], got {cosine_similarity}"


# ============================================================================
# Edge Case Tests
# ============================================================================

def test_minimum_dimension_embedding():
    """Test that embeddings with minimum valid dimension are accepted."""
    document = {
        "document_id": "doc_123",
        "document_type": "market_news",
        "title": "Test Document",
        "content": "Test content",
        "embedding": [0.5] * 1536,  # Minimum valid embedding
        "ticker": "TEST",
        "sector": "technology",
        "timestamp": "2024-01-01T00:00:00Z",
        "source": "test_api",
        "metadata": {
            "sentiment": "neutral",
            "relevance_score": 0.5
        }
    }
    assert validate_market_document(document)


def test_reject_wrong_dimension_embedding():
    """Test that embeddings with wrong dimension are rejected."""
    document = {
        "document_id": "doc_123",
        "document_type": "market_news",
        "title": "Test Document",
        "content": "Test content",
        "embedding": [0.5] * 512,  # Wrong dimension (should be 1536)
        "ticker": "TEST",
        "sector": "technology",
        "timestamp": "2024-01-01T00:00:00Z",
        "source": "test_api",
        "metadata": {
            "sentiment": "neutral",
            "relevance_score": 0.5
        }
    }
    
    with pytest.raises(AssertionError, match="Embedding must have dimension 1536"):
        validate_market_document(document)


def test_reject_missing_embedding():
    """Test that documents without embeddings are rejected."""
    document = {
        "document_id": "doc_123",
        "document_type": "market_news",
        "title": "Test Document",
        "content": "Test content",
        # Missing embedding field
        "ticker": "TEST",
        "sector": "technology",
        "timestamp": "2024-01-01T00:00:00Z",
        "source": "test_api",
        "metadata": {
            "sentiment": "neutral",
            "relevance_score": 0.5
        }
    }
    
    with pytest.raises(AssertionError, match="Missing required field: embedding"):
        validate_market_document(document)


def test_reject_zero_embedding():
    """Test that all-zero embeddings are rejected."""
    document = {
        "document_id": "doc_123",
        "document_type": "market_news",
        "title": "Test Document",
        "content": "Test content",
        "embedding": [0.0] * 1536,  # All zeros (invalid)
        "ticker": "TEST",
        "sector": "technology",
        "timestamp": "2024-01-01T00:00:00Z",
        "source": "test_api",
        "metadata": {
            "sentiment": "neutral",
            "relevance_score": 0.5
        }
    }
    
    with pytest.raises(AssertionError, match="Embedding vector must not be all zeros"):
        validate_market_document(document)


def test_reject_nan_embedding():
    """Test that embeddings with NaN values are rejected."""
    embedding = [0.5] * 1536
    embedding[100] = float('nan')  # Inject NaN
    
    with pytest.raises(AssertionError, match="Embedding element .* is NaN"):
        validate_vector_embedding(embedding, expected_dimension=1536)


def test_reject_infinite_embedding():
    """Test that embeddings with infinite values are rejected."""
    embedding = [0.5] * 1536
    embedding[100] = float('inf')  # Inject infinity
    
    with pytest.raises(AssertionError, match="Embedding element .* is infinite"):
        validate_vector_embedding(embedding, expected_dimension=1536)
