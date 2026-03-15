"""
Unit tests for RAGEnricher (Task 29.8).

Tests:
  - Mocked OpenSearch and Bedrock clients
  - Top-k selection and similarity threshold filtering
  - No-context fallback path and warning log
  - Prompt context block formatting
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest

from src.utils.rag_enricher import (
    AGENT_INTERACTIONS_INDEX,
    CONTEXT_DELIMITER_END,
    CONTEXT_DELIMITER_START,
    MARKET_INTELLIGENCE_INDEX,
    RAGContext,
    RAGDocument,
    RAGEnricher,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_enricher(hits: list[dict] | None = None, embedding: list[float] | None = None) -> RAGEnricher:
    enricher = RAGEnricher()
    mock_opensearch = MagicMock()
    mock_bedrock = MagicMock()

    emb = embedding or [0.5] * 1536
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: json.dumps({"embedding": emb}).encode())
    }

    search_hits = hits if hits is not None else []
    mock_opensearch.search.return_value = {"hits": {"hits": search_hits}}
    mock_opensearch.index.return_value = {"result": "created"}

    enricher._opensearch = mock_opensearch
    enricher._bedrock = mock_bedrock
    return enricher


def _hit(doc_id: str, score: float, content: str = "test content") -> dict:
    return {"_id": doc_id, "_score": score, "_source": {"content": content}}


# ---------------------------------------------------------------------------
# Tests: enrich()
# ---------------------------------------------------------------------------


class TestEnrich:
    def test_returns_rag_context(self):
        enricher = _make_enricher()
        result = enricher.enrich("test query", "session-1")
        assert isinstance(result, RAGContext)

    def test_filters_below_threshold(self):
        enricher = _make_enricher(
            hits=[_hit("d1", 0.3), _hit("d2", 0.7), _hit("d3", 0.9)],
        )
        enricher.similarity_threshold = 0.6
        result = enricher.enrich("query", "session-1")
        assert all(d.similarity_score >= 0.6 for d in result.documents)
        assert len(result.documents) == 2

    def test_top_k_limit(self):
        hits = [_hit(f"d{i}", 0.9) for i in range(20)]
        enricher = _make_enricher(hits=hits)
        enricher.top_k = 5
        result = enricher.enrich("query", "session-1")
        assert len(result.documents) <= 5

    def test_documents_sorted_by_score_descending(self):
        hits = [_hit("d1", 0.7), _hit("d2", 0.9), _hit("d3", 0.8)]
        enricher = _make_enricher(hits=hits)
        enricher.similarity_threshold = 0.0
        result = enricher.enrich("query", "session-1")
        scores = [d.similarity_score for d in result.documents]
        assert scores == sorted(scores, reverse=True)

    def test_has_context_true_when_docs_returned(self):
        enricher = _make_enricher(hits=[_hit("d1", 0.9)])
        enricher.similarity_threshold = 0.0
        result = enricher.enrich("query", "session-1")
        assert result.has_context is True

    def test_has_context_false_when_no_docs(self):
        enricher = _make_enricher(hits=[])
        result = enricher.enrich("query", "session-1")
        assert result.has_context is False

    def test_searches_both_indices(self):
        enricher = _make_enricher()
        enricher.enrich("query", "session-1")
        search_calls = enricher._opensearch.search.call_args_list
        indices_searched = [c[1]["index"] for c in search_calls]
        assert MARKET_INTELLIGENCE_INDEX in indices_searched
        assert AGENT_INTERACTIONS_INDEX in indices_searched

    def test_agent_interactions_filtered_by_session(self):
        enricher = _make_enricher()
        enricher.enrich("query", "my-session-id")
        # Find the agent-interactions search call
        for c in enricher._opensearch.search.call_args_list:
            if c[1]["index"] == AGENT_INTERACTIONS_INDEX:
                body = c[1]["body"]
                # Should have a filter on session_id
                query_str = json.dumps(body)
                assert "my-session-id" in query_str
                break

    def test_duration_ms_recorded(self):
        enricher = _make_enricher()
        result = enricher.enrich("query", "session-1")
        assert result.duration_ms >= 0.0

    def test_opensearch_failure_returns_empty_context(self):
        enricher = RAGEnricher()
        mock_opensearch = MagicMock()
        mock_opensearch.search.side_effect = Exception("OpenSearch down")
        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = {
            "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1536}).encode())
        }
        enricher._opensearch = mock_opensearch
        enricher._bedrock = mock_bedrock

        result = enricher.enrich("query", "session-1")
        assert isinstance(result, RAGContext)
        assert result.has_context is False


# ---------------------------------------------------------------------------
# Tests: no-context fallback
# ---------------------------------------------------------------------------


class TestNoContextFallback:
    def test_no_context_logs_warning(self, caplog):
        import logging
        enricher = _make_enricher(hits=[])
        with caplog.at_level(logging.WARNING, logger="src.utils.rag_enricher"):
            result = enricher.enrich("query", "session-1")
        assert result.has_context is False
        # Warning should mention rag_no_context
        assert any("rag_no_context" in r.message for r in caplog.records)

    def test_no_context_format_block_is_empty(self):
        enricher = _make_enricher(hits=[])
        result = enricher.enrich("query", "session-1")
        assert result.format_context_block() == ""


# ---------------------------------------------------------------------------
# Tests: format_context_block()
# ---------------------------------------------------------------------------


class TestFormatContextBlock:
    def test_contains_delimiters(self):
        docs = [RAGDocument("d1", "content here", 0.9, "market-intelligence")]
        ctx = RAGContext(documents=docs, query="q", session_id="s", duration_ms=10.0, has_context=True)
        block = ctx.format_context_block()
        assert CONTEXT_DELIMITER_START in block
        assert CONTEXT_DELIMITER_END in block

    def test_contains_document_content(self):
        docs = [RAGDocument("d1", "important market data", 0.85, "market-intelligence")]
        ctx = RAGContext(documents=docs, query="q", session_id="s", duration_ms=10.0, has_context=True)
        block = ctx.format_context_block()
        assert "important market data" in block

    def test_multiple_documents_numbered(self):
        docs = [
            RAGDocument("d1", "doc one", 0.9, "market-intelligence"),
            RAGDocument("d2", "doc two", 0.8, "agent-interactions"),
        ]
        ctx = RAGContext(documents=docs, query="q", session_id="s", duration_ms=10.0, has_context=True)
        block = ctx.format_context_block()
        assert "Document 1" in block
        assert "Document 2" in block

    def test_empty_documents_returns_empty_string(self):
        ctx = RAGContext(documents=[], query="q", session_id="s", duration_ms=10.0, has_context=False)
        assert ctx.format_context_block() == ""

    def test_similarity_score_in_block(self):
        docs = [RAGDocument("d1", "content", 0.753, "market-intelligence")]
        ctx = RAGContext(documents=docs, query="q", session_id="s", duration_ms=10.0, has_context=True)
        block = ctx.format_context_block()
        assert "0.753" in block


# ---------------------------------------------------------------------------
# Tests: index_interaction()
# ---------------------------------------------------------------------------


class TestIndexInteraction:
    def test_indexes_to_agent_interactions(self):
        enricher = _make_enricher()
        enricher.index_interaction("agent output text", "portfolio_analyzer", "output", "sess-1")
        enricher._opensearch.index.assert_called_once()
        call_kwargs = enricher._opensearch.index.call_args[1]
        assert call_kwargs["index"] == AGENT_INTERACTIONS_INDEX

    def test_document_has_required_fields(self):
        enricher = _make_enricher()
        enricher.index_interaction("content", "supervisor", "input", "sess-2", "wf-123")
        doc = enricher._opensearch.index.call_args[1]["body"]
        assert doc["content"] == "content"
        assert doc["agent_type"] == "supervisor"
        assert doc["interaction_type"] == "input"
        assert doc["session_id"] == "sess-2"
        assert doc["workflow_id"] == "wf-123"
        assert "embedding" in doc
        assert "timestamp" in doc

    def test_opensearch_failure_does_not_raise(self):
        enricher = _make_enricher()
        enricher._opensearch.index.side_effect = Exception("write failed")
        # Should not raise
        enricher.index_interaction("content", "supervisor", "input", "sess-3")

    def test_bedrock_failure_does_not_raise(self):
        enricher = RAGEnricher()
        mock_opensearch = MagicMock()
        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.side_effect = Exception("Bedrock down")
        enricher._opensearch = mock_opensearch
        enricher._bedrock = mock_bedrock
        # Should not raise — uses zero vector fallback
        enricher.index_interaction("content", "supervisor", "input", "sess-4")


# ---------------------------------------------------------------------------
# Tests: _embed()
# ---------------------------------------------------------------------------


class TestEmbed:
    def test_returns_1536_dim_vector(self):
        enricher = _make_enricher()
        result = enricher._embed("hello world")
        assert len(result) == 1536

    def test_empty_string_returns_zero_vector(self):
        enricher = _make_enricher()
        result = enricher._embed("")
        assert result == [0.0] * 1536

    def test_whitespace_only_returns_zero_vector(self):
        enricher = _make_enricher()
        result = enricher._embed("   ")
        assert result == [0.0] * 1536

    def test_bedrock_failure_returns_zero_vector(self):
        enricher = RAGEnricher()
        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.side_effect = Exception("Bedrock error")
        enricher._bedrock = mock_bedrock
        result = enricher._embed("some text")
        assert result == [0.0] * 1536


# ---------------------------------------------------------------------------
# Tests: RAGContext properties
# ---------------------------------------------------------------------------


class TestRAGContextProperties:
    def test_document_ids_property(self):
        docs = [
            RAGDocument("id-1", "c1", 0.9, "market-intelligence"),
            RAGDocument("id-2", "c2", 0.8, "agent-interactions"),
        ]
        ctx = RAGContext(documents=docs, query="q", session_id="s", duration_ms=10.0, has_context=True)
        assert ctx.document_ids == ["id-1", "id-2"]

    def test_similarity_scores_property(self):
        docs = [
            RAGDocument("id-1", "c1", 0.9, "market-intelligence"),
            RAGDocument("id-2", "c2", 0.75, "agent-interactions"),
        ]
        ctx = RAGContext(documents=docs, query="q", session_id="s", duration_ms=10.0, has_context=True)
        assert ctx.similarity_scores == [0.9, 0.75]

    def test_empty_context_properties(self):
        ctx = RAGContext(documents=[], query="q", session_id="s", duration_ms=5.0, has_context=False)
        assert ctx.document_ids == []
        assert ctx.similarity_scores == []
