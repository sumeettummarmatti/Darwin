"""The policy language: safe by construction, and packs refuse to load untested or biased."""

import pytest

from core.rules.expr import Expression, ExpressionError
from core.rules.packs import PackLoadError, parse_pack


@pytest.mark.parametrize("source", [
    "__import__('os').system('true')",
    "().__class__.__bases__",
    "[x for x in range(3)]",
    "lambda: 1",
    "open('/etc/passwd')",
    "facts.__dict__",
])
def test_expressions_reject_anything_outside_the_whitelist(source):
    with pytest.raises(ExpressionError):
        Expression(source).evaluate({"facts": {}})


def test_dotted_access_is_dictionary_lookup_only():
    assert Expression("steps.notice.days * 2").evaluate({"steps": {"notice": {"days": 30}}}) == 60
    with pytest.raises(ExpressionError):
        Expression("steps.notice.days").evaluate({"steps": "not a mapping"})


def test_date_functions():
    e = Expression("completed_months('2022-09-15', '2026-11-30')")
    assert e.evaluate({}) == 50


BASE = {"pack": "demo", "version": 1, "effective_from": "2026-01-01",
        "rules": [{"id": "R1", "when": "grade == 'L1'", "then": {"days": 30}}, {"id": "R2", "then": {"days": 60}}]}


def test_a_pack_with_no_tests_does_not_load():
    with pytest.raises(PackLoadError, match="no tests"):
        parse_pack(dict(BASE))


def test_a_pack_with_a_failing_test_does_not_load():
    with pytest.raises(PackLoadError, match="failing"):
        parse_pack({**BASE, "tests": [{"given": {"grade": "L1"}, "expect": {"days": 45}}]})


def test_a_pack_referencing_a_prohibited_criterion_does_not_load():
    raw = {**BASE, "prohibited_criteria": ["college_tier"],
           "derive": [{"id": "D1", "name": "bonus", "expr": "10 if college_tier == 1 else 0"}],
           "tests": [{"given": {"grade": "L1", "college_tier": 1}, "expect": {"days": 30}}]}
    with pytest.raises(PackLoadError, match="prohibited"):
        parse_pack(raw)


def test_guards_fail_closed():
    raw = {**BASE, "guards": [{"id": "G1", "assert": "days >= 45", "error": "below floor"}],
           "tests": [{"given": {"grade": "L1"}, "expect_error": "below floor"}]}
    pack = parse_pack(raw)
    decision = pack.evaluate({"grade": "L1"})
    assert not decision.ok and decision.error_rule == "G1"
