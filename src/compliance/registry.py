"""
PolicyRegistry — runtime rule registration for the Compliance-as-a-Code library.

Allows new rules to be registered at runtime without modifying core library code.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Optional


class PolicyRegistry:
    """
    Registry that maps (domain, rule_id) → rule function.

    Rule functions must have the signature:
        (text: str, metadata: dict) -> Optional[ComplianceViolation]
    """

    def __init__(self) -> None:
        # domain → {rule_id: rule_fn}
        self._rules: dict[str, dict[str, Callable]] = defaultdict(dict)

    def register(self, rule_fn: Callable, domain: str, rule_id: str) -> None:
        """Register a rule function under the given domain and rule_id.

        Args:
            rule_fn:  Callable with signature (text, metadata) -> Optional[ComplianceViolation]
            domain:   Policy domain string, e.g. "FINRA", "NIST", "PCI_DSS"
            rule_id:  Unique rule identifier, e.g. "FINRA-001"
        """
        self._rules[domain][rule_id] = rule_fn

    def get_rules(self, domain: Optional[str] = None) -> list[Callable]:
        """Return all registered rule functions, optionally filtered by domain.

        Args:
            domain: If provided, return only rules for that domain.
                    If None, return all rules across all domains.

        Returns:
            List of callable rule functions.
        """
        if domain is not None:
            return list(self._rules.get(domain, {}).values())

        all_rules: list[Callable] = []
        for domain_rules in self._rules.values():
            all_rules.extend(domain_rules.values())
        return all_rules

    def get_rule_ids(self, domain: Optional[str] = None) -> list[tuple[str, str]]:
        """Return (domain, rule_id) pairs for all registered rules.

        Args:
            domain: If provided, filter to that domain only.

        Returns:
            List of (domain, rule_id) tuples.
        """
        if domain is not None:
            return [(domain, rid) for rid in self._rules.get(domain, {})]

        result: list[tuple[str, str]] = []
        for dom, rules in self._rules.items():
            for rid in rules:
                result.append((dom, rid))
        return result

    def has_rule(self, domain: str, rule_id: str) -> bool:
        """Check whether a specific rule is registered."""
        return rule_id in self._rules.get(domain, {})
