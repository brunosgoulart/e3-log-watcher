from __future__ import annotations

from app.config.models import CompositeRuleConfig


def calculate_risk(triggered_rules: list[CompositeRuleConfig]) -> int:
    """Bounded additive score; every contribution is visible in the alarm evidence."""

    return min(100, sum(rule.risk_weight for rule in triggered_rules))
