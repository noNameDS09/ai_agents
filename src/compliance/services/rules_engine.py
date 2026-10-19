"""Deterministic rules engine for jurisdiction-specific compliance rules.

Computes deadlines, escalation levels, severity scores, and coverage assessments.
All logic is pure Python — no LLM involvement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional


@dataclass
class DeadlineRule:
    """A jurisdiction-specific deadline rule."""
    jurisdiction_id: str
    license_type: str
    renewal_window_days: int
    grace_period_days: int
    escalation_ladder: list[dict]
    business_day_adjustment: bool
    effective_from: date
    effective_to: Optional[date] = None

    @classmethod
    def from_dict(cls, data: dict) -> "DeadlineRule":
        return cls(
            jurisdiction_id=data["jurisdiction_id"],
            license_type=data["license_type"],
            renewal_window_days=data["renewal_window_days"],
            grace_period_days=data["grace_period_days"],
            escalation_ladder=data.get("escalation_ladder", []),
            business_day_adjustment=data.get("business_day_adjustment", False),
            effective_from=date.fromisoformat(data["effective_from"]),
            effective_to=date.fromisoformat(data["effective_to"]) if data.get("effective_to") else None,
        )


def compute_deadline(license_expires_on: date, rule: DeadlineRule, now: date) -> date:
    """Compute the deadline for a license renewal.

    Deterministic — no LLM involvement.
    """
    expiry = license_expires_on
    renewal_start = expiry - timedelta(days=rule.renewal_window_days)

    if now < renewal_start:
        return renewal_start
    if now <= expiry:
        return expiry
    if now <= expiry + timedelta(days=rule.grace_period_days):
        return expiry + timedelta(days=rule.grace_period_days)
    return expiry + timedelta(days=rule.grace_period_days)


def business_day_adjust(d: date, holidays: set[date] | None = None) -> date:
    """Shift date to next business day if it falls on a weekend or holiday."""
    if holidays is None:
        holidays = set()
    while d.weekday() >= 5:  # Saturday=5, Sunday=6
        d += timedelta(days=1)
    while d in holidays:
        d += timedelta(days=1)
    return d


def compute_escalation_level(days_before_deadline: int, ladder: list[dict]) -> int:
    """Determine escalation level based on days remaining before deadline.

    As the deadline approaches, escalation increases. Returns the level of the
    most urgent threshold that has been reached (days_before_deadline <= threshold).
    If days_before_deadline exceeds all thresholds, returns level 0.
    """
    level = 0
    for entry in sorted(ladder, key=lambda x: x.get("days_before", 0), reverse=True):
        if days_before_deadline <= entry.get("days_before", 0):
            level = max(level, entry.get("level", 0))
    return level


def assign_severity(finding_type: str, context: dict) -> str:
    """Deterministic severity assignment. Returns LOW|MEDIUM|HIGH|CRITICAL."""
    if finding_type == "EXPIRY":
        days_until_expiry = context.get("days_until_expiry", 999)
        if days_until_expiry < 0 and context.get("past_grace", False):
            return "CRITICAL"
        if days_until_expiry <= 7:
            return "HIGH"
        if days_until_expiry <= 30:
            return "MEDIUM"
        return "LOW"
    if finding_type == "CONTROL_FAILURE":
        risk_level = context.get("obligation_risk", "MEDIUM")
        return risk_level if risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL") else "MEDIUM"
    if finding_type == "GAP":
        return context.get("severity", "MEDIUM")
    if finding_type == "ANOMALY":
        amount = context.get("amount", 0)
        threshold = context.get("threshold", float("inf"))
        if amount > threshold * 2:
            return "HIGH"
        if amount > threshold:
            return "MEDIUM"
        return "LOW"
    return "MEDIUM"


def assess_coverage(control: dict, obligation: dict, evidence_list: list[dict]) -> str:
    """Assess control-to-obligation coverage. Returns FULL|PARTIAL|NONE."""
    if not control or control.get("status") != "ACTIVE":
        return "NONE"
    if not evidence_list:
        return "PARTIAL"
    # Check if evidence is current (within last assessment period)
    stale = any(e.get("stale", False) for e in evidence_list)
    if stale:
        return "PARTIAL"
    return "FULL"