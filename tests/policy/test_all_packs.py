"""Compliance CI: every shipped pack loads, and every pack's own tests pass."""

from pathlib import Path

import pytest
import yaml

from core.reserved import load_registry_file
from core.rules.packs import load_pack_file

POLICIES = sorted(p for p in (Path(__file__).resolve().parents[2] / "policies").glob("*.yaml"))


@pytest.mark.parametrize("path", POLICIES, ids=lambda p: p.name)
def test_pack_loads_and_its_tests_pass(path):
    raw = yaml.safe_load(path.read_text())
    if raw.get("registry") == "reserved_decisions":
        registry = load_registry_file(path)
        assert all(t["passed"] for t in registry.run_tests())
    else:
        pack = load_pack_file(path)
        results = pack.run_tests()
        assert results, f"{path.name} ships no tests"
        assert all(r["passed"] for r in results), [r for r in results if not r["passed"]]


def test_statutory_floor_violation_fails():
    pack = load_pack_file(next(p for p in POLICIES if p.name.startswith("notice_period")))
    d = pack.evaluate({"grade": "L4", "employment_type": "fixed_term", "contract_notice_days": 10, "state": "IN-KA"})
    assert not d.ok and "statutory floor" in d.error


def test_gratuity_is_decided_by_rule_not_model():
    pack = load_pack_file(next(p for p in POLICIES if p.name.startswith("settlement")))
    d = pack.evaluate({"date_of_joining": "2022-09-15", "last_working_day": "2026-11-30", "basic_monthly": 92000})
    assert d.outputs["gratuity_eligible"] is False and d.outputs["gratuity_amount"] == 0
    assert "ST-003" in d.rule_ids
