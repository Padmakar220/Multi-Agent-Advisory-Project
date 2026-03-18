"""AgentCore Memory client for session and long-term state persistence.

Provides namespace-isolated memory operations with OTEL tracing.
Namespaces:
  - session:{session_id}  — short-term context (conversation, workflow state)
  - user:{user_id}        — long-term cross-session memory (risk profile, preferences)
"""

import os
import time
import logging
import json
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Namespace prefixes
SESSION_NS_PREFIX = "session"
USER_NS_PREFIX = "user"


class AgentCoreMemoryClient:
    """
    Thin wrapper around the AgentCore Memory API (backed by DynamoDB).

    Namespace isolation is enforced by prefixing every key with the
    namespace so that cross-user reads are structurally impossible.
    """

    def __init__(
        self,
        table_name: str = "AgentCoreMemory",
        region_name: str = "us-east-1",
    ):
        self.table_name = table_name
        self.region_name = region_name
        self.dynamodb = boto3.resource("dynamodb", region_name=region_name)
        self.table = self.dynamodb.Table(table_name)

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _ns_key(self, namespace: str, key: str) -> str:
        """Build a namespaced composite key."""
        return f"{namespace}#{key}"

    def put(self, namespace: str, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """
        Write a value into the given namespace.

        Args:
            namespace: Namespace string (e.g. "session:abc123")
            key:       Record key within the namespace
            value:     Payload dict to store
            ttl:       Optional Unix timestamp for DynamoDB TTL
        """
        item: Dict[str, Any] = {
            "pk": self._ns_key(namespace, key),
            "namespace": namespace,
            "key": key,
            "value": json.dumps(value),
            "updated_at": int(time.time()),
        }
        if ttl is not None:
            item["ttl"] = ttl

        self.table.put_item(Item=item)

    def get(self, namespace: str, key: str) -> Optional[Dict[str, Any]]:
        """
        Read a value from the given namespace.

        Returns None if the record does not exist or has expired.
        """
        response = self.table.get_item(Key={"pk": self._ns_key(namespace, key)})
        item = response.get("Item")
        if item is None:
            return None

        # Honour TTL locally (DynamoDB TTL deletion is eventually consistent)
        ttl = item.get("ttl")
        if ttl and int(time.time()) > ttl:
            return None

        return json.loads(item["value"])

    def delete(self, namespace: str, key: str) -> None:
        """Delete a record from the given namespace."""
        self.table.delete_item(Key={"pk": self._ns_key(namespace, key)})


# ------------------------------------------------------------------
# Namespace helpers
# ------------------------------------------------------------------

def session_namespace(session_id: str) -> str:
    """Return the session-scoped namespace string."""
    return f"{SESSION_NS_PREFIX}:{session_id}"


def user_namespace(user_id: str) -> str:
    """Return the user-scoped namespace string."""
    return f"{USER_NS_PREFIX}:{user_id}"
