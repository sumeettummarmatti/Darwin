"""Shared fixtures. Every test gets a fresh, seeded kernel in its own temp directory."""

from __future__ import annotations

import pytest

from core.kernel import Kernel
from tools.seed import seed


@pytest.fixture(autouse=True)
def _offline_models(monkeypatch):
    """Tests never call a real provider, even if a GROQ_API_KEY sits in .env."""
    monkeypatch.setenv("SETU_MODEL_PROFILE", "sim")


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    monkeypatch.setenv("SETU_VAR", str(tmp_path))
    k = Kernel(tmp_path / "setu.db", tmp_path / "mocks.db")
    seed(k)
    yield k
    k.store.close()


def settle(k: Kernel, rounds: int = 30) -> None:
    """Tick the orchestrator until nothing moves (no background thread in tests)."""
    for _ in range(rounds):
        if k.orchestrator.tick() == 0:
            return


def decide_open(k: Kernel, *, kind: str | None = None, action: str | None = None, user: str, decision: str = "approve",
                values: dict | None = None, run_id: str | None = None) -> dict:
    items = [i for i in k.queue.list("open") if (kind is None or i["kind"] == kind) and (action is None or i["action"] == action)
             and (run_id is None or i["run_id"] == run_id)]
    assert items, f"no open queue item kind={kind} action={action}"
    item = items[0]
    return k.decide(item["id"], user, decision, context_hash=item["context_hash"], values=values or {})
