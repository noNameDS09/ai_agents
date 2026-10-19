"""Golden tests for the deterministic rules engine.

Tests deadline computation, escalation levels, severity assignment, and
coverage assessment against golden test data for CA, NY, TX MTL rules.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from compliance.services.rules_engine import (
    DeadlineRule,
    assign_severity,
    assess_coverage,
    business_day_adjust,
    compute_deadline,
    compute_escalation_level,
)

GOLDEN_DIR = Path(__file__).parent / "golden"


def load_golden(name: str) -> dict:
    with open(GOLDEN_DIR / name) as f:
        return json.load(f)


@pytest.mark.parametrize("golden_file", ["ca_mtl_rules.json", "ny_mtl_rules.json", "tx_mtl_rules.json"])
def test_deadline_computation(golden_file):
    golden = load_golden(golden_file)
    rule = DeadlineRule.from_dict(golden["rule"])
    for tc in golden["test_cases"]:
        now = date.fromisoformat(tc["now"])
        expires = date.fromisoformat(tc["expires"])
        expected = date.fromisoformat(tc["expected_deadline"])
        result = compute_deadline(expires, rule, now)
        assert result == expected, (
            f"{golden_file}: {tc['description']} — "
            f"expected {expected}, got {result}"
        )


def test_escalation_levels():
    ladder = [
        {"days_before": 60, "level": 0, "channels": ["email"]},
        {"days_before": 30, "level": 1, "channels": ["email", "slack"]},
        {"days_before": 14, "level": 2, "channels": ["email", "slack", "sms"]},
        {"days_before": 7, "level": 3, "channels": ["email", "slack", "sms", "phone"]},
    ]
    # Input is days before deadline (days remaining)
    # As deadline approaches, escalation increases
    assert compute_escalation_level(65, ladder) == 0  # far away (>60)
    assert compute_escalation_level(35, ladder) == 0  # 31-60 days
    assert compute_escalation_level(20, ladder) == 1  # 15-30 days
    assert compute_escalation_level(10, ladder) == 2  # 8-14 days
    assert compute_escalation_level(5, ladder) == 3   # < 7 days
    assert compute_escalation_level(0, ladder) == 3   # at deadline


def test_severity_assignment():
    assert assign_severity("EXPIRY", {"days_until_expiry": -5, "past_grace": True}) == "CRITICAL"
    assert assign_severity("EXPIRY", {"days_until_expiry": 3}) == "HIGH"
    assert assign_severity("EXPIRY", {"days_until_expiry": 20}) == "MEDIUM"
    assert assign_severity("EXPIRY", {"days_until_expiry": 60}) == "LOW"
    assert assign_severity("CONTROL_FAILURE", {"obligation_risk": "HIGH"}) == "HIGH"
    assert assign_severity("GAP", {"severity": "CRITICAL"}) == "CRITICAL"
    assert assign_severity("ANOMALY", {"amount": 150, "threshold": 100}) == "MEDIUM"
    assert assign_severity("ANOMALY", {"amount": 250, "threshold": 100}) == "HIGH"


def test_coverage_assessment():
    assert assess_coverage({"status": "ACTIVE"}, {}, [{"stale": False}]) == "FULL"
    assert assess_coverage({"status": "ACTIVE"}, {}, [{"stale": True}]) == "PARTIAL"
    assert assess_coverage({"status": "ACTIVE"}, {}, []) == "PARTIAL"
    assert assess_coverage({"status": "INACTIVE"}, {}, []) == "NONE"
    assert assess_coverage(None, {}, []) == "NONE"


def test_business_day_adjust():
    # Saturday June 13, 2026
    sat = date(2026, 6, 13)
    assert business_day_adjust(sat).weekday() < 5  # Monday
    # Monday June 15, 2026 (no adjustment needed)
    mon = date(2026, 6, 15)
    assert business_day_adjust(mon) == mon