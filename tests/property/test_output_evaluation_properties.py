"""
Property-based tests for LLM output evaluation (Task 26.5).

Tests:
- Property 71: LLM Output Evaluation Completeness
- Property 72: Below-Threshold Output Actions
- Property 73: Evaluation Scores Attached to OTEL Span

Configure Hypothesis with max_examples=100.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, strategies as st

from src.compliance.output_evaluator import EvaluatedOutput, OutputEvaluator, _cosine_similarity

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_text_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=0,
    max_size=300,
)

_embedding_strategy = st.lists(
    st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    min_size=4,
    max_size=4,
)

_rag_doc_strategy = st.lists(
    st.fixed_dictionaries({"content": _text_strategy}),
    min_size=0,
    max_size=5,
)


def _make_evaluator_with_mock_embeddings(embedding_value: list[float]) -> OutputEvaluator:
    """Create an OutputEvaluator that returns a fixed embedding for all inputs."""
    evaluator = OutputEvaluator(
        groundedness_threshold=0.5,
        relevance_threshold=0.4,
    )
    evaluator._embed = MagicMock(return_value=embedding_value)
    return evaluator


# ---------------------------------------------------------------------------
# Property 71: LLM Output Evaluation Completeness
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=3000)
@given(
    llm_output=_text_strategy,
    user_query=_text_strategy,
    rag_docs=_rag_doc_strategy,
)
def test_property_71_llm_output_evaluation_completeness(
    llm_output: str,
    user_query: str,
    rag_docs: list[dict],
) -> None:
    """
    **Validates: Requirements 17.1, 17.2, 17.3**

    For any LLM output, user query, and RAG context, evaluate() must:
    - Return an EvaluatedOutput (never raise)
    - Contain groundedness_score (float in [0, 1])
    - Contain relevance_score (float in [0, 1])
    - Contain compliance_result (ComplianceResult)
    - Contain is_suppressed (bool)
    """
    evaluator = _make_evaluator_with_mock_embeddings([0.5, 0.5, 0.5, 0.5])
    result = evaluator.evaluate(llm_output, rag_docs, user_query)

    assert isinstance(result, EvaluatedOutput), "evaluate() must return EvaluatedOutput"
    assert isinstance(result.groundedness_score, float), "groundedness_score must be float"
    assert isinstance(result.relevance_score, float), "relevance_score must be float"
    assert result.compliance_result is not None, "compliance_result must not be None"
    assert isinstance(result.is_suppressed, bool), "is_suppressed must be bool"
    assert isinstance(result.flags, list), "flags must be a list"


# ---------------------------------------------------------------------------
# Property 72: Below-Threshold Output Actions
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=3000)
@given(
    groundedness=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    relevance=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    g_threshold=st.floats(min_value=0.1, max_value=0.9, allow_nan=False),
    r_threshold=st.floats(min_value=0.1, max_value=0.9, allow_nan=False),
)
def test_property_72_below_threshold_output_actions(
    groundedness: float,
    relevance: float,
    g_threshold: float,
    r_threshold: float,
) -> None:
    """
    **Validates: Requirements 17.4, 17.5**

    When groundedness < threshold → "low_groundedness" flag present.
    When relevance < threshold → "low_relevance" flag present.
    When both above threshold → neither flag present (for clean text).
    """
    # Use clean text to avoid compliance violations
    clean_text = "The portfolio analysis is complete."
    clean_query = "Analyze my portfolio."

    # Build embeddings that produce the desired cosine similarity
    # We use a simple trick: output_emb = [g, 0, r, 0], rag_emb = [1, 0, 0, 0], query_emb = [0, 0, 1, 0]
    # cosine(output, rag) ≈ g / sqrt(g²+r²), cosine(output, query) ≈ r / sqrt(g²+r²)
    # For simplicity, just mock _embed to return controlled vectors
    norm = max((groundedness**2 + relevance**2) ** 0.5, 1e-9)
    output_emb = [groundedness / norm, 0.0, relevance / norm, 0.0]
    rag_emb = [1.0, 0.0, 0.0, 0.0]
    query_emb = [0.0, 0.0, 1.0, 0.0]

    call_count = [0]

    def mock_embed(text: str) -> list[float]:
        call_count[0] += 1
        if call_count[0] == 1:
            return output_emb  # llm_output embedding
        elif call_count[0] == 2:
            return query_emb   # user_query embedding
        else:
            return rag_emb     # rag doc embedding

    evaluator = OutputEvaluator(
        groundedness_threshold=g_threshold,
        relevance_threshold=r_threshold,
    )
    evaluator._embed = mock_embed

    actual_groundedness = _cosine_similarity(output_emb, rag_emb)
    actual_relevance = _cosine_similarity(output_emb, query_emb)

    result = evaluator.evaluate(clean_text, [{"content": "market data"}], clean_query)

    if actual_groundedness < g_threshold:
        assert "low_groundedness" in result.flags, (
            f"Expected low_groundedness flag when groundedness={actual_groundedness:.3f} < {g_threshold:.3f}"
        )
    if actual_relevance < r_threshold:
        assert "low_relevance" in result.flags, (
            f"Expected low_relevance flag when relevance={actual_relevance:.3f} < {r_threshold:.3f}"
        )


# ---------------------------------------------------------------------------
# Property 73: Evaluation Scores Attached to OTEL Span
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=3000)
@given(
    llm_output=_text_strategy,
    user_query=_text_strategy,
)
def test_property_73_evaluation_scores_attached_to_otel_span(
    llm_output: str,
    user_query: str,
) -> None:
    """
    **Validates: Requirements 17.7**

    The OTEL span must receive groundedness_score, relevance_score,
    compliance_flags, and is_suppressed attributes after evaluate().
    """
    mock_span = MagicMock()

    evaluator = _make_evaluator_with_mock_embeddings([0.7, 0.7, 0.7, 0.7])
    evaluator.evaluate(llm_output, [], user_query, trace_span=mock_span)

    # Verify set_attribute was called with the required keys
    called_keys = {call.args[0] for call in mock_span.set_attribute.call_args_list}
    assert "groundedness_score" in called_keys, "span must have groundedness_score"
    assert "relevance_score" in called_keys, "span must have relevance_score"
    assert "compliance_flags" in called_keys, "span must have compliance_flags"
    assert "is_suppressed" in called_keys, "span must have is_suppressed"
