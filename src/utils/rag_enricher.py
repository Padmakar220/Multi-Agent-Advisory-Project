"""
RAGEnricher — Retrieval-Augmented Generation context enrichment (Requirement 20 / Task 29).

Performs knn vector search on both:
  - market-intelligence  (market data and news)
  - agent-interactions   (prior agent I/O within the same session)

Uses Bedrock Titan Embeddings for query embedding generation.

Environment variables:
  OPENSEARCH_ENDPOINT   — OpenSearch Serverless collection endpoint
  RAG_TOP_K             — Number of top documents to return (default: 5)
  RAG_SIMILARITY_THRESHOLD — Minimum cosine similarity (default: 0.6)
  BEDROCK_EMBEDDING_MODEL_ID — Bedrock embedding model (default: amazon.titan-embed-text-v1)
  AWS_REGION            — AWS region (default: us-east-1)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "")
RAG_TOP_K = int(os.environ.get("RAG_TOP_K", "5"))
RAG_SIMILARITY_THRESHOLD = float(os.environ.get("RAG_SIMILARITY_THRESHOLD", "0.6"))
BEDROCK_EMBEDDING_MODEL = os.environ.get(
    "BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1"
)
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

MARKET_INTELLIGENCE_INDEX = "market-intelligence"
AGENT_INTERACTIONS_INDEX = "agent-interactions"

CONTEXT_DELIMITER_START = "--- RETRIEVED CONTEXT ---"
CONTEXT_DELIMITER_END = "--- END RETRIEVED CONTEXT ---"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RAGDocument:
    """A single retrieved document from OpenSearch."""

    doc_id: str
    content: str
    similarity_score: float
    index: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RAGContext:
    """Result of a RAG enrichment call."""

    documents: list[RAGDocument]
    query: str
    session_id: str
    duration_ms: float
    has_context: bool

    def format_context_block(self) -> str:
        """Format retrieved documents as a structured context block for LLM prompts."""
        if not self.documents:
            return ""
        lines = [CONTEXT_DELIMITER_START]
        for i, doc in enumerate(self.documents, 1):
            lines.append(f"[Document {i} | score={doc.similarity_score:.3f} | index={doc.index}]")
            lines.append(doc.content.strip())
            lines.append("")
        lines.append(CONTEXT_DELIMITER_END)
        return "\n".join(lines)

    @property
    def document_ids(self) -> list[str]:
        return [d.doc_id for d in self.documents]

    @property
    def similarity_scores(self) -> list[float]:
        return [d.similarity_score for d in self.documents]


# ---------------------------------------------------------------------------
# RAGEnricher
# ---------------------------------------------------------------------------


class RAGEnricher:
    """Retrieves relevant context from OpenSearch for LLM prompt enrichment.

    Args:
        opensearch_client: Optional pre-configured OpenSearch client.
        bedrock_client:    Optional pre-configured Bedrock runtime client.
        top_k:             Number of top documents to return.
        similarity_threshold: Minimum similarity score to include a document.
    """

    def __init__(
        self,
        opensearch_client: Any = None,
        bedrock_client: Any = None,
        top_k: int = RAG_TOP_K,
        similarity_threshold: float = RAG_SIMILARITY_THRESHOLD,
    ) -> None:
        self._opensearch = opensearch_client
        self._bedrock = bedrock_client
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enrich(
        self,
        query: str,
        session_id: str,
        span: Any = None,
    ) -> RAGContext:
        """Perform knn search and return RAG context for the given query.

        Args:
            query:      The user query or agent task description.
            session_id: Current session identifier.
            span:       Optional OTEL span to record retrieval attributes.

        Returns:
            RAGContext with retrieved documents (may be empty if none exceed threshold).
        """
        start_ms = time.monotonic() * 1000

        embedding = self._embed(query)
        documents: list[RAGDocument] = []

        # Search both indices
        for index_name in (MARKET_INTELLIGENCE_INDEX, AGENT_INTERACTIONS_INDEX):
            try:
                results = self._knn_search(index_name, embedding, session_id)
                documents.extend(results)
            except Exception as exc:
                logger.warning(
                    "RAG search failed for index %s: %s", index_name, exc,
                    extra={"session_id": session_id, "index": index_name},
                )

        # Filter by similarity threshold and take top-k
        filtered = [d for d in documents if d.similarity_score >= self.similarity_threshold]
        filtered.sort(key=lambda d: d.similarity_score, reverse=True)
        top_docs = filtered[: self.top_k]

        duration_ms = time.monotonic() * 1000 - start_ms
        has_context = len(top_docs) > 0

        if not has_context:
            top_score = max((d.similarity_score for d in documents), default=0.0)
            logger.warning(
                "RAG no context found",
                extra={
                    "event": "rag_no_context",
                    "query": query[:200],
                    "session_id": session_id,
                    "threshold": self.similarity_threshold,
                    "top_score": top_score,
                },
            )

        rag_context = RAGContext(
            documents=top_docs,
            query=query,
            session_id=session_id,
            duration_ms=duration_ms,
            has_context=has_context,
        )

        self._record_span(span, rag_context)
        return rag_context

    def index_interaction(
        self,
        content: str,
        agent_type: str,
        interaction_type: str,
        session_id: str,
        workflow_id: str = "",
    ) -> None:
        """Index an agent interaction into the agent-interactions OpenSearch index.

        Args:
            content:          The text content to index (agent input, output, or LLM response).
            agent_type:       Agent type (e.g. "supervisor", "portfolio_analyzer").
            interaction_type: Type of interaction (e.g. "input", "output", "llm_response").
            session_id:       Current session identifier.
            workflow_id:      Optional workflow execution identifier.
        """
        embedding = self._embed(content)
        doc = {
            "content": content,
            "agent_type": agent_type,
            "interaction_type": interaction_type,
            "session_id": session_id,
            "workflow_id": workflow_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "embedding": embedding,
        }
        try:
            client = self._get_opensearch()
            client.index(index=AGENT_INTERACTIONS_INDEX, body=doc)
        except Exception as exc:
            logger.warning(
                "Failed to index agent interaction: %s",
                exc,
                extra={
                    "agent_type": agent_type,
                    "interaction_type": interaction_type,
                    "session_id": session_id,
                },
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _knn_search(
        self, index_name: str, embedding: list[float], session_id: str
    ) -> list[RAGDocument]:
        """Execute a knn vector search on the given OpenSearch index."""
        client = self._get_opensearch()

        query_body: dict[str, Any] = {
            "size": self.top_k * 2,  # fetch extra to allow filtering
            "query": {
                "knn": {
                    "embedding": {
                        "vector": embedding,
                        "k": self.top_k * 2,
                    }
                }
            },
            "_source": {"excludes": ["embedding"]},
        }

        # For agent-interactions, filter by session_id
        if index_name == AGENT_INTERACTIONS_INDEX:
            query_body["query"] = {
                "bool": {
                    "must": [
                        {
                            "knn": {
                                "embedding": {
                                    "vector": embedding,
                                    "k": self.top_k * 2,
                                }
                            }
                        }
                    ],
                    "filter": [{"term": {"session_id": session_id}}],
                }
            }

        response = client.search(index=index_name, body=query_body)
        hits = response.get("hits", {}).get("hits", [])

        documents = []
        for hit in hits:
            score = hit.get("_score", 0.0)
            source = hit.get("_source", {})
            documents.append(
                RAGDocument(
                    doc_id=hit.get("_id", ""),
                    content=source.get("content", ""),
                    similarity_score=float(score),
                    index=index_name,
                    metadata={k: v for k, v in source.items() if k != "content"},
                )
            )
        return documents

    def _embed(self, text: str) -> list[float]:
        """Generate a text embedding using Bedrock Titan Embeddings."""
        if not text or not text.strip():
            return [0.0] * 1536
        try:
            client = self._get_bedrock()
            response = client.invoke_model(
                modelId=BEDROCK_EMBEDDING_MODEL,
                body=json.dumps({"inputText": text[:8192]}),
                contentType="application/json",
                accept="application/json",
            )
            body = json.loads(response["body"].read())
            return body.get("embedding", [0.0] * 1536)
        except Exception as exc:
            logger.warning("Bedrock embedding failed: %s; using zero vector", exc)
            return [0.0] * 1536

    def _record_span(self, span: Any, rag_context: RAGContext) -> None:
        """Record RAG retrieval attributes on the OTEL span."""
        if span is None:
            return
        try:
            span.set_attribute("rag_document_ids", json.dumps(rag_context.document_ids))
            span.set_attribute("rag_similarity_scores", json.dumps(rag_context.similarity_scores))
            span.set_attribute("rag_duration_ms", rag_context.duration_ms)
            span.set_attribute("rag_has_context", rag_context.has_context)
        except Exception as exc:
            logger.debug("Failed to set RAG span attributes: %s", exc)

    def _get_opensearch(self) -> Any:
        if self._opensearch is None:
            # Import here to avoid hard dependency when mocking
            try:
                from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
                import boto3 as _boto3
                credentials = _boto3.Session().get_credentials()
                auth = AWSV4SignerAuth(credentials, AWS_REGION, "aoss")
                self._opensearch = OpenSearch(
                    hosts=[{"host": OPENSEARCH_ENDPOINT, "port": 443}],
                    http_auth=auth,
                    use_ssl=True,
                    verify_certs=True,
                    connection_class=RequestsHttpConnection,
                )
            except ImportError:
                raise RuntimeError(
                    "opensearch-py is required. Install with: pip install opensearch-py"
                )
        return self._opensearch

    def _get_bedrock(self) -> Any:
        if self._bedrock is None:
            self._bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)
        return self._bedrock
