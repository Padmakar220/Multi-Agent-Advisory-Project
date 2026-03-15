"""
ComplianceEngine — public API for the Compliance-as-a-Code library.

Loads compliance_config.yaml, registers default rules, and evaluates
text+metadata against all active policy rules within a 500ms budget.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

from src.compliance.config import (
    get_halt_threshold,
    get_severity_override,
    is_rule_enabled,
    load_config,
)
from src.compliance.models import ComplianceResult, ComplianceViolation, Severity
from src.compliance.registry import PolicyRegistry
from src.compliance.rules.finra import FINRA_RULES
from src.compliance.rules.nist import NIST_RULES
from src.compliance.rules.pci_dss import PCI_DSS_RULES

logger = logging.getLogger(__name__)

# Latency budget in seconds
_LATENCY_BUDGET_S = 0.5

# Default config path (bundled with the package)
_DEFAULT_CONFIG = Path(__file__).parent / "compliance_config.yaml"


class ComplianceEngine:
    """Evaluates text and metadata against all active compliance policy rules.

    Usage::

        engine = ComplianceEngine()
        result = engine.evaluate("You should buy AAPL now!", metadata={})
        if not result.is_compliant:
            for v in result.violations:
                print(v.rule_id, v.severity, v.description)
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        """Initialise the engine.

        Args:
            config_path: Path to a compliance_config.yaml file.
                         Defaults to the bundled compliance_config.yaml.
        """
        resolved = config_path or str(_DEFAULT_CONFIG)
        self.config = load_config(resolved)
        self.registry = PolicyRegistry()
        self._register_default_rules()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, text: str, metadata: dict[str, Any]) -> ComplianceResult:
        """Evaluate *text* and *metadata* against all active policy rules.

        Runs within a 500ms latency budget; logs a warning if exceeded.

        Args:
            text:     The text payload to screen (user input or LLM output).
            metadata: Arbitrary key/value context (e.g. user_id, session_id,
                      ai_disclosure flag, bias_score, etc.).

        Returns:
            ComplianceResult with a list of violations and an is_compliant flag.
            is_compliant is False when any violation's severity meets or exceeds
            the configured halt_threshold for its domain.
        """
        start = time.monotonic()

        violations: list[ComplianceViolation] = []

        for rule_fn in self.registry.get_rules():
            try:
                violation = rule_fn(text, metadata)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Rule function %s raised an exception: %s", rule_fn, exc)
                continue

            if violation is None:
                continue

            # Apply severity override from config if set
            override = get_severity_override(
                self.config, violation.policy_domain, violation.rule_id
            )
            if override:
                try:
                    violation.severity = Severity(override)
                except ValueError:
                    logger.warning(
                        "Invalid severity_override '%s' for %s; ignoring.",
                        override,
                        violation.rule_id,
                    )

            violations.append(violation)

        elapsed = time.monotonic() - start
        if elapsed > _LATENCY_BUDGET_S:
            logger.warning(
                "ComplianceEngine.evaluate() exceeded 500ms budget: %.0fms",
                elapsed * 1000,
            )

        is_compliant = self._compute_is_compliant(violations)
        return ComplianceResult(violations=violations, is_compliant=is_compliant)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_default_rules(self) -> None:
        """Register all built-in FINRA, NIST, and PCI DSS rules that are enabled."""
        all_rules = [
            ("FINRA", FINRA_RULES),
            ("NIST", NIST_RULES),
            ("PCI_DSS", PCI_DSS_RULES),
        ]
        for domain, rules in all_rules:
            for rule_id, rule_fn in rules:
                if is_rule_enabled(self.config, domain, rule_id):
                    self.registry.register(rule_fn, domain, rule_id)

    def _compute_is_compliant(self, violations: list[ComplianceViolation]) -> bool:
        """Return False if any violation meets or exceeds its domain halt_threshold."""
        for violation in violations:
            threshold_str = get_halt_threshold(self.config, violation.policy_domain)
            try:
                threshold = Severity(threshold_str)
            except ValueError:
                logger.warning(
                    "Invalid halt_threshold '%s' for domain %s; defaulting to critical.",
                    threshold_str,
                    violation.policy_domain,
                )
                threshold = Severity.CRITICAL

            if violation.severity >= threshold:
                return False
        return True
