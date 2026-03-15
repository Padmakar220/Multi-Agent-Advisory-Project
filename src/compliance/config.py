"""
Configuration loader for the Compliance-as-a-Code library.

Loads compliance_config.yaml at runtime; no code changes required to adjust
thresholds, enable/disable rules, or set custom rule parameters.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

# Default config path relative to this file
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "compliance_config.yaml"


def load_config(config_path: Optional[str] = None) -> dict[str, Any]:
    """Load and return the compliance configuration dictionary.

    Args:
        config_path: Path to a YAML config file.  If None, the bundled
                     compliance_config.yaml is used.

    Returns:
        Parsed configuration dictionary.

    Raises:
        FileNotFoundError: If the specified config file does not exist.
        yaml.YAMLError:    If the file cannot be parsed.
    """
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(f"Compliance config not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    return config or {}


def get_domain_config(config: dict[str, Any], domain: str) -> dict[str, Any]:
    """Return the configuration block for a specific policy domain.

    Args:
        config: Full config dict as returned by load_config().
        domain: Domain name, e.g. "FINRA", "NIST", "PCI_DSS".

    Returns:
        Domain-specific config dict, or empty dict if domain not found.
    """
    return config.get("domains", {}).get(domain, {})


def is_rule_enabled(config: dict[str, Any], domain: str, rule_id: str) -> bool:
    """Check whether a specific rule is enabled in the config.

    Args:
        config:  Full config dict.
        domain:  Policy domain.
        rule_id: Rule identifier, e.g. "FINRA-001".

    Returns:
        True if the rule is enabled (default True if not specified).
    """
    domain_cfg = get_domain_config(config, domain)
    rule_cfg = domain_cfg.get("rules", {}).get(rule_id, {})
    return rule_cfg.get("enabled", True)


def get_severity_override(
    config: dict[str, Any], domain: str, rule_id: str
) -> Optional[str]:
    """Return the severity override for a rule, or None if not set.

    Args:
        config:  Full config dict.
        domain:  Policy domain.
        rule_id: Rule identifier.

    Returns:
        Severity string override (e.g. "critical") or None.
    """
    domain_cfg = get_domain_config(config, domain)
    rule_cfg = domain_cfg.get("rules", {}).get(rule_id, {})
    return rule_cfg.get("severity_override")


def get_halt_threshold(config: dict[str, Any], domain: str) -> str:
    """Return the halt_threshold severity for a domain.

    Args:
        config: Full config dict.
        domain: Policy domain.

    Returns:
        Severity string, e.g. "high".  Defaults to "critical" if not set.
    """
    domain_cfg = get_domain_config(config, domain)
    return domain_cfg.get("halt_threshold", "critical")
