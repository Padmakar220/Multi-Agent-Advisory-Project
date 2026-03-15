"""
OutputEvaluator — LLM output quality and compliance evaluation (Requirement 17).

Evaluates every LLM-generated output for:
  1. Groundedness  — cosine similarity between output embedding and RAG context embeddings
  2. Relevance     — cosine similarity between output embedding and user query embedding
  3. Compliance    — ComplianceEngine policy check (FINRA, NIST, PCI DSS)

Suppression / routing logic:
  - groundedness < groundedness_min_threshold  → flag, log, route to investigation queue
  - relevance < relevance_min_threshold        → flag, log
  - compliance violation >= halt_threshold     → suppress output, log, route to investigation queue

All scores are attached to the provided OTEL trace span.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import boto3

from src.compliance.engine import ComplianceEngine
from src.compliance.models import ComplianceResult, Severity

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# ---------------------------------------------------------------------------
# Configuration defaults (overridable via compliance_config.yaml or env vars)
# ---------------------------------------------------------------------------

_DEFAULT_GROUNDEDNESS_THRESHOLD = float(
    os.environ.get("GROUNDEDNESS_MIN_THRESHOLD", "0.5")
)
_DEFAULT_RELEVANCE_THRESHOLD = float(
    os.environ.get("RELEVANCE_MIN_THRESHOLD", "0.4")
)
_BEDROCK_EMBEDDING_MODEL = os.environ.get(
    "BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1"
)
COMPLIANCE_VIOLATIONS_TABLE = os.environ.get(
    "COMPLIANCE_VIOLATIONS_TABLE", "advisory-compliance-violations"
)
INVESTIGATION_QUEUE_URL = os.environ.get("INVESTIGATION_QUEUE_URL", "")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EvaluatedOutput:
    """Result of evaluating a single LLM output."""

    llm_output: str
    groundedness_score: float
    relevance_score: float
    compliance_result: ComplianceResult
    is_suppressed: bool = False
    suppression_reason: Optional[str] = None
    flags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# OutputEvaluator
# ---------------------------------------------------------------------------


class OutputEvaluator:
    """Evaluates LLM outputs for groundedness, relevance, and compliance.

    Args:
        compliance_engine: Optional pre-configured ComplianceEngine instance.
                           If None, a default engine is created.
        bedrock_client:    Optional pre-configured boto3 Bedrock runtime client.
                           If None, a client is created on first use.
        dynamodb_resource: Optional pre-configured boto3 DynamoDB resource.
        sqs_client:        Optional pre-configured boto3 SQS client.
        groundedness_threshold: Minimum acceptable groundedness score (0–1).
        relevance_threshold:    Minimum acceptable relevance score (0–1).
    """

    def __init__(
        self,
        compliance_engine: Optional[ComplianceEngine] = None,
        bedrock_client: Any = None,
        dynamodb_resource: Any = None,
        sqs_client: Any = None,
        groundedness_threshold: float = _DEFAULT_GROUNDEDNESS_THRESHOLD,
        relevance_threshold: float = _DEFAULT_RELEVANCE_THRESHOLD,
    ) -> None:
        self._engine = compliance_engine or ComplianceEngine()
        self._bedrock = bedrock_client
        self._dynamodb = dynamodb_resource
        self._sqs = sqs_client
        self.groundedness_threshold = groundedness_threshold
        self.relevance_threshold = relevance_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        llm_output: str,
        rag_context: list[dict[str, Any]],
        user_query: str,
        trace_span: Any = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> EvaluatedOutput:
        """Evaluate an LLM output for groundedness, relevance, and compliance.

        Args:
            llm_output:  The text produced by the LLM.
            rag_context: List of RAG documents used to construct the prompt.
                         Each dict should have at least a "content" key.
            user_query:  The original user query / agent task description.
            trace_span:  An OpenTelemetry span to attach evaluation scores to.
                         May be None (e.g. in unit tests).
            metadata:    Optional extra metadata passed to ComplianceEngine.

        Returns:
            EvaluatedOutput with all scores and suppression status.
        """
        metadata = metadata or {}

        # 1. Compute embeddings
        output_embedding = self._embed(llm_output)
        query_embedding = self._embed(user_query)
        rag_embeddings = [
            self._embed(doc.get("content", "")) for doc in rag_context
        ]

        # 2. Groundedness score
        if rag_embeddings:
            groundedness_score = max(
                _cosine_similarity(output_embedding, rag_emb)
                for rag_emb in rag_embeddings
            )
        else:
            groundedness_score = 0.0

        # 3. Relevance score
        relevance_score = _cosine_similarity(output_embedding, query_embedding)

        # 4. Compliance check
        compliance_result = self._engine.evaluate(llm_output, metadata)

        # 5. Build EvaluatedOutput
        evaluated = EvaluatedOutput(
            llm_output=llm_output,
            groundedness_score=groundedness_score,
            relevance_score=relevance_score,
            compliance_result=compliance_result,
        )

        # 6. Apply suppression / routing logic
        self._apply_suppression_logic(evaluated, metadata)

        # 7. Attach scores to OTEL span
        self._attach_to_span(trace_span, evaluated)

        return evaluated

    # ------------------------------------------------------------------
    # Suppression and routing logic (task 26.3)
    # ------------------------------------------------------------------

    def _apply_suppression_logic(
        self, evaluated: EvaluatedOutput, metadata: dict[str, Any]
    ) -> None:
        """Apply suppression and routing based on scores and compliance."""
        user_id = metadata.get("user_id", "unknown")
        session_id = metadata.get("session_id", "unknown")
        trace_id = metadata.get("trace_id", "")

        # Groundedness check
        if evaluated.groundedness_score < self.groundedness_threshold:
            evaluated.flags.append("low_groundedness")
            logger.warning(
                "LLM output groundedness below threshold",
                extra={
                    "groundedness_score": evaluated.groundedness_score,
                    "threshold": self.groundedness_threshold,
                    "user_id": user_id,
                    "trace_id": trace_id,
                },
            )
            self._route_to_investigation(
                reason="low_groundedness",
                llm_output=evaluated.llm_output,
                score=evaluated.groundedness_score,
                threshold=self.groundedness_threshold,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
            )

        # Relevance check
        if evaluated.relevance_score < self.relevance_threshold:
            evaluated.flags.append("low_relevance")
            logger.warning(
                "LLM output relevance below threshold",
                extra={
                    "relevance_score": evaluated.relevance_score,
                    "threshold": self.relevance_threshold,
                    "user_id": user_id,
                    "trace_id": trace_id,
                },
            )

        # Compliance check — suppress if any violation meets/exceeds halt threshold
        if not evaluated.compliance_result.is_compliant:
            evaluated.is_suppressed = True
            evaluated.suppression_reason = "compliance_violation"
            evaluated.flags.append("compliance_violation")
            logger.warning(
                "LLM output suppressed due to compliance violation",
                extra={
                    "violations": [
                        {"rule_id": v.rule_id, "severity": v.severity.value}
                        for v in evaluated.compliance_result.violations
                    ],
                    "user_id": user_id,
                    "trace_id": trace_id,
                },
            )
            for violation in evaluated.compliance_result.violations:
                self._write_violation_record(
                    violation=violation,
                    llm_output=evaluated.llm_output,
                    user_id=user_id,
                    session_id=session_id,
                    trace_id=trace_id,
                )
                self._enqueue_for_investigation(
                    violation=violation,
                    user_id=user_id,
                    session_id=session_id,
                    trace_id=trace_id,
                )

    # ------------------------------------------------------------------
    # OTEL span attachment (task 26.4)
    # ------------------------------------------------------------------

    def _attach_to_span(self, span: Any, evaluated: EvaluatedOutput) -> None:
        """Attach evaluation scores and flags to the OTEL trace span."""
        if span is None:
            return
        try:
            span.set_attribute("groundedness_score", evaluated.groundedness_score)
            span.set_attribute("relevance_score", evaluated.relevance_score)
            span.set_attribute(
                "compliance_flags",
                json.dumps([v.rule_id for v in evaluated.compliance_result.violations]),
            )
            span.set_attribute("is_suppressed", evaluated.is_suppressed)

            if evaluated.is_suppressed or evaluated.flags:
                from opentelemetry.trace import StatusCode
                span.set_status(StatusCode.ERROR, evaluated.suppression_reason or "evaluation_flags")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to set OTEL span attributes: %s", exc)

    # ------------------------------------------------------------------
    # Embedding helper
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        """Generate a text embedding using Bedrock Titan Embeddings."""
        if not text or not text.strip():
            return [0.0] * 1536

        try:
            client = self._get_bedrock()
            response = client.invoke_model(
                modelId=_BEDROCK_EMBEDDING_MODEL,
                body=json.dumps({"inputText": text[:8192]}),
                contentType="application/json",
                accept="application/json",
            )
            body = json.loads(response["body"].read())
            return body.get("embedding", [0.0] * 1536)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bedrock embedding failed: %s; using zero vector", exc)
            return [0.0] * 1536

    def _get_bedrock(self) -> Any:
        if self._bedrock is None:
            self._bedrock = boto3.client(
                "bedrock-runtime",
                region_name=os.environ.get("AWS_REGION", "us-east-1"),
            )
        return self._bedrock

    # ------------------------------------------------------------------
    # DynamoDB / SQS helpers
    # ------------------------------------------------------------------

    def _get_dynamodb(self) -> Any:
        if self._dynamodb is None:
            self._dynamodb = boto3.resource("dynamodb")
        return self._dynamodb

    def _get_sqs(self) -> Any:
        if self._sqs is None:
            self._sqs = boto3.client("sqs")
        return self._sqs

    def _write_violation_record(
        self,
        *,
        violation: Any,
        llm_output: str,
        user_id: str,
        session_id: str,
        trace_id: str,
    ) -> None:
        try:
            table = self._get_dynamodb().Table(COMPLIANCE_VIOLATIONS_TABLE)
            table.put_item(
                Item={
                    "violation_id": str(uuid.uuid4()),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "user_id": user_id,
                    "session_id": session_id,
                    "stage": "llm_output_evaluation",
                    "policy_domain": violation.policy_domain,
                    "rule_id": violation.rule_id,
                    "severity": violation.severity.value,
                    "raw_content_hash": hashlib.sha256(llm_output.encode()).hexdigest(),
                    "investigation_status": "pending",
                    "llm_judge_verdict": None,
                    "trace_id": trace_id,
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to write output violation record: %s", exc)

    def _route_to_investigation(
        self,
        *,
        reason: str,
        llm_output: str,
        score: float,
        threshold: float,
        user_id: str,
        session_id: str,
        trace_id: str,
    ) -> None:
        if not INVESTIGATION_QUEUE_URL:
            return
        try:
            self._get_sqs().send_message(
                QueueUrl=INVESTIGATION_QUEUE_URL,
                MessageBody=json.dumps(
                    {
                        "reason": reason,
                        "score": score,
                        "threshold": threshold,
                        "user_id": user_id,
                        "session_id": session_id,
                        "trace_id": trace_id,
                        "output_hash": hashlib.sha256(llm_output.encode()).hexdigest(),
                    }
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to enqueue output evaluation to SQS: %s", exc)

    def _enqueue_for_investigation(
        self,
        *,
        violation: Any,
        user_id: str,
        session_id: str,
        trace_id: str,
    ) -> None:
        if not INVESTIGATION_QUEUE_URL:
            return
        try:
            self._get_sqs().send_message(
                QueueUrl=INVESTIGATION_QUEUE_URL,
                MessageBody=json.dumps(
                    {
                        "rule_id": violation.rule_id,
                        "policy_domain": violation.policy_domain,
                        "severity": violation.severity.value,
                        "user_id": user_id,
                        "session_id": session_id,
                        "trace_id": trace_id,
                    }
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to enqueue compliance violation to SQS: %s", exc)


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
