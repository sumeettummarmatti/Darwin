"""Devil's Advocate against planted defects. Guards the honest number, in both directions."""

from bench.fault_corpus import run_corpus


def test_rules_layer_catches_planted_defects_without_false_alarms(kernel):
    result = run_corpus(kernel)
    assert result["catch_rate_rules"] >= 0.85
    assert result["false_alarm_rate"] == 0
    # Judgement-only defects are exactly what the deterministic layer cannot see.
    assert all(not r["caught_by_rules"] for r in result["rows"] if r["judgement"])
