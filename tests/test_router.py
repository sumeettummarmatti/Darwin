"""Router behaviour that matters with real providers (no network here)."""

from pathlib import Path

from core import config
from core.router.router import RoutingConfig, parse_json_object


def test_fenced_or_chatty_json_is_recovered():
    assert parse_json_object('```json\n{"verdict": "CLEAR"}\n```') == {"verdict": "CLEAR"}
    assert parse_json_object('Here you go: {"a": 1} hope it helps') == {"a": 1}


def test_groq_key_selects_the_groq_profile(monkeypatch):
    monkeypatch.delenv("SETU_MODEL_PROFILE", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    cfg = RoutingConfig(config.CONFIG_DIR / "routing.yaml")
    assert cfg.active_profile == "groq"
    assert cfg.provider(1).model == "openai/gpt-oss-20b" and cfg.provider(2).model == "openai/gpt-oss-120b"


def test_without_a_key_the_simulator_is_used(monkeypatch):
    monkeypatch.delenv("SETU_MODEL_PROFILE", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert RoutingConfig(config.CONFIG_DIR / "routing.yaml").active_profile == "sim"
