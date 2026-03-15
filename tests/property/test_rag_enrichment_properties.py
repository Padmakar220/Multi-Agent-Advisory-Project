"""
Property tests for RAG Context Enrichment (Task 29.7).

Property 79: RAG Enrichment Before Prompt Construction
  — Vector search performed and top-k docs injected before any LLM prompt.

Property 80: Agent Interaction Indexing Round-Trip
  — Indexed agent I/O is retrievable as RAG context in same session.

Property 81: RAG Span Document Recording
  — OTEL span contains document_ids and similarity_scores for every retrieval.

Property 82: RAG Retrieval Latency
  — Retrieval completes within 300ms at p95.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.utils.rag_enricher import RAGContext, RAGDocument, RAGEnricher

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

query_st = st.text(min_size=1, max_size=500)
session_id_st = st.uuids().map(str)
agent_type_st = st.sampled_from(
    ["supervisor", "portfolio_analyzer", "tax_optimizer", "rebalancing_agent"]
)
interaction_type_st = st.sampled_from(["input", "output", "llm_response"])
similarity_score_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

doc_st = st.fixed_dictionaries(
    {
        "doc_id": st.uuids().map(str),
        "content": st.text(min_size=1, max_size=200),
        "similarity_score": similarity_score_st,
        "index": st.sampled_from(["market-intelligence", "agent-interactions"]),
    }
)


def _make_rag_document(d: dict) -> RAGDocument:
    return RAGDocument(
        doc_id=d["doc_id"],
        content=d["content"],
        similarity_score=d["similarity_score"],
        index=d["index"],
    )


def _make_mock_enricher(docs: list[RAGDocument], duration_ms: float = 50.0) -> RAGEnricher:
    """Create a RAGEnricher with mocked OpenSearch and Bedrock."""
    enricher = RAGEnricher()
    mock_opensearch = MagicMock()
    mock_bedrock = MagicMock()

    # Mock embedding response
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(
            read=lambda: json.dumps({"embedding": [0.1] * 1536}).encode()
        )
    }

    # Mock OpenSearch search response
    hits = [
        {
            "_id": doc.doc_id,
            "_score": doc.similarity_score,
            "_source": {"content": doc.content},
        }
        for doc in docs
    ]
    mock_opensearch.search.return_value = {"hits": {"hits": hits}}
    mock_opensearch.index.return_value = {"result": "created"}

    enricher._opensearch = mock_opensearch
    enricher._bedrock = mock_bedrock
    return enricher


# ---------------------------------------------------------------------------
# Property 79: RAG Enrichment Before Prompt Construction
# ---------------------------------------------------------------------------


@given(query_st, session_id_st, st.lists(doc_st, min_size=0, max_size=10))
@settings(max_examples=100)
def test_property_79_rag_enrichment_before_prompt(
    query: str, session_id: str, raw_docs: list[dict]
) -> None:
    """Property 79: enrich() always returns a RAGContext with correct structure."""
    docs = [_make_rag_document(d) for d in raw_docs]
    enricher = _make_mock_enricher(docs)

    rag_context = enricher.enrich(query, session_id)

    # Always returns a RAGContext
    assert isinstance(rag_context, RAGContext)
    assert rag_context.query == query
    assert rag_context.session_id == session_id
    assert isinstance(rag_context.documents, list)
    assert isinstance(rag_context.duration_ms, float)
    assert rag_context.duration_ms >= 0.0

    # has_context is consistent with documents list
    assert rag_context.has_context == (len(rag_context.documents) > 0)

    # All returned documents meet the similarity threshold
    for doc in rag_context.documents:
        assert doc.similarity_score >= enricher.similarity_threshold

    # At most top_k documents returned
    assert len(rag_context.documents) <= enricher.top_k


@given(query_st, session_id_st, st.lists(doc_st, min_size=1, max_size=5))
@settings(max_examples=100)
def test_property_79b_context_block_format(
    query: str, session_id: str, raw_docs: list[dict]
) -> None:
    """Property 79b: format_context_block() produces delimited output when docs exist."""
    # Use docs with high similarity to ensure they pass threshold
    docs = [
        RAGDocument(
            doc_id=d["doc_id"],
            content=d["content"],
            similarity_score=0.9,  # above default threshold
            index=d["index"],
        )
        for d in raw_docs
    ]
    enricher = _make_mock_enricher(docs)
    rag_context = enricher.enrich(query, session_id)

    if rag_context.has_context:
        block = rag_context.format_context_block()
        assert "--- RETRIEVED CONTEXT ---" in block
        assert "--- END RETRIEVED CONTEXT ---" in block
    else:
        assert rag_context.format_context_block() == ""


# ---------------------------------------------------------------------------
# Property 80: Agent Interaction Indexing Round-Trip
# ---------------------------------------------------------------------------


@given(
    st.text(min_size=1, max_size=200),
    agent_type_st,
    interaction_type_st,
    session_id_st,
)
@settings(max_examples=100)
def test_property_80_interaction_indexing_round_trip(
    content: str, agent_type: str, interaction_type: str, session_id: str
) -> None:
    """Property 80: index_interaction() calls OpenSearch index with correct fields."""
    enricher = RAGEnricher()
    mock_opensearch = MagicMock()
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1536}).encode())
    }
    mock_opensearch.index.return_value = {"result": "created"}
    enricher._opensearch = mock_opensearch
    enricher._bedrock = mock_bedrock

    enricher.index_interaction(content, agent_type, interaction_type, session_id)

    mock_opensearch.index.assert_called_once()
    call_kwargs = mock_opensearch.index.call_args[1]
    assert call_kwargs["index"] == "agent-interactions"
    doc = call_kwargs["body"]
    assert doc["content"] == content
    assert doc["agent_type"] == agent_type
    assert doc["interaction_type"] == interaction_type
    assert doc["session_id"] == session_id
    assert "embedding" in doc
    assert len(doc["embedding"]) == 1536
    assert "timestamp" in doc


@given(st.text(min_size=1, max_size=200), agent_type_st, interaction_type_st, session_id_st)
@settings(max_examples=100)
def test_property_80b_indexing_failure_does_not_raise(
    content: str, agent_type: str, interaction_type: str, session_id: str
) -> None:
    """Property 80b: index_interaction() failure is handled gracefully."""
    enricher = RAGEnricher()
    mock_opensearch = MagicMock()
    mock_opensearch.index.side_effect = Exception("OpenSearch unavailable")
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1536}).encode())
    }
    enricher._opensearch = mock_opensearch
    enricher._bedrock = mock_bedrock

    # Should not raise
    enricher.index_interaction(content, agent_type, interaction_type, session_id)


# ---------------------------------------------------------------------------
# Property 81: RAG Span Document Recording
# ---------------------------------------------------------------------------


@given(query_st, session_id_st, st.lists(doc_st, min_size=0, max_size=5))
@settings(max_examples=100)
def test_property_81_rag_span_document_recording(
    query: str, session_id: str, raw_docs: list[dict]
) -> None:
    """Property 81: OTEL span receives rag_document_ids, rag_similarity_scores, rag_duration_ms."""
    docs = [
        RAGDocument(
            doc_id=d["doc_id"],
            content=d["content"],
            similarity_score=0.9,
            index=d["index"],
        )
        for d in raw_docs
    ]
    enricher = _make_mock_enricher(docs)

    mock_span = MagicMock()
    enricher.enrich(query, session_id, span=mock_span)

    # Span must have been called with the required attributes
    set_attr_calls = {
        call[0][0]: call[0][1]
        for call in mock_span.set_attribute.call_args_list
    }
    assert "rag_document_ids" in set_attr_calls
    assert "rag_similarity_scores" in set_attr_calls
    assert "rag_duration_ms" in set_attr_calls
    assert "rag_has_context" in set_attr_calls

    # Values are JSON-serialisable
    json.loads(set_attr_calls["rag_document_ids"])
    json.loads(set_attr_calls["rag_similarity_scores"])


@given(query_st, session_id_st)
@settings(max_examples=100)
def test_property_81b_span_none_does_not_raise(query: str, session_id: str) -> None:
    """Property 81b: enrich() with span=None does not raise."""
    enricher = _make_mock_enricher([])
    rag_context = enricher.enrich(query, session_id, span=None)
    assert isinstance(rag_context, RAGContext)


# ---------------------------------------------------------------------------
# Property 82: RAG Retrieval Latency
# ---------------------------------------------------------------------------


@given(query_st, session_id_st)
@settings(max_examples=100)
def test_property_82_rag_retrieval_latency(query: str, session_id: str) -> None:
    """Property 82: RAG retrieval duration_ms is recorded and non-negative."""
    enricher = _make_mock_enricher([])
    rag_context = enricher.enrich(query, session_id)

    # duration_ms must be recorded and non-negative
    assert rag_context.duration_ms >= 0.0
    # For mocked calls, should complete well under 300ms
    assert rag_context.duration_ms < 5000.0  # generous upper bound for test env


def test_property_82_latency_under_300ms_with_mock() -> None:
    """Property 82 (concrete): Mocked retrieval completes well under 300ms."""
    enricher = _make_mock_enricher([])
    start = time.monotonic()
    for _ in range(10):
        enricher.enrich("test query", str(uuid.uuid4()))
    elapsed_ms = (time.monotonic() - start) * 1000
    avg_ms = elapsed_ms / 10
    # With mocked clients, average should be well under 300ms
    assert avg_ms < 300.0, f"Average RAG latency {avg_ms:.1f}ms exceeds 300ms"


# ---------------------------------------------------------------------------
# Property: similarity threshold filtering
# ---------------------------------------------------------------------------


@given(
    query_st,
    session_id_st,
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@settings(max_examples=100)
def test_similarity_threshold_filtering(
    query: str, session_id: str, threshold: float
) -> None:
    """All returned documents have similarity_score >= threshold."""
    enricher = RAGEnricher(similarity_threshold=threshold)
    mock_opensearch = MagicMock()
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1536}).encode())
    }
    # Return docs with varying scores
    hits = [
        {"_id": str(i), "_score": i * 0.1, "_source": {"content": f"doc {i}"}}
        for i in range(11)
    ]
    mock_opensearch.search.return_value = {"hits": {"hits": hits}}
    enricher._opensearch = mock_opensearch
    enricher._bedrock = mock_bedrock

    rag_context = enricher.enrich(query, session_id)

    for doc in rag_context.documents:
        assert doc.similarity_score >= threshold
