"""Kill switch (four scopes) and circuit breakers.

Scopes: ``global``, ``workflow:<name>``, ``skill:<name>``, ``connector:<name>``.
Flipping one is a database row — no code change, no restart. Paused work is
parked in the human queue with its context, never dropped.

Two automatic breakers:

* **Connector breaker** — N consecutive transport failures open the breaker for
  a cooldown; the outbox keeps the intent and drains when it half-opens.
* **Workflow breaker** — if a workflow's escalation rate inside a window crosses
  the threshold in ``policies/circuit_breakers``, the kernel flips that
  workflow's kill switch itself, before a human notices.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from core.audit import AuditChain, AuditEntry
from core.clock import Clock, parse_ts
from core.db import Store

SCOPES = ("global", "workflow", "skill", "connector")


class KillSwitch:
    def __init__(self, store: Store, clock: Clock, audit: AuditChain):
        self.store = store
        self.clock = clock
        self.audit = audit

    def set(self, scope: str, target: str, active: bool, actor: str, reason: str = "") -> None:
        if scope not in SCOPES:
            raise ValueError(f"unknown scope {scope}")
        target = target or "*"
        with self.store.tx() as conn:
            conn.execute(
                "INSERT INTO kill_switches(scope, target, active, reason, actor, at) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(scope, target) DO UPDATE SET active=excluded.active, reason=excluded.reason, "
                "actor=excluded.actor, at=excluded.at",
                (scope, target, int(active), reason, actor, self.clock.now_iso()),
            )
        self.audit.append(AuditEntry(
            actor=actor, action=f"killswitch.{'engage' if active else 'release'}", kind="governance",
            outcome="ok", inputs={"scope": scope, "target": target}, detail={"reason": reason},
        ))

    def active(self) -> list[dict[str, Any]]:
        return self.store.query("SELECT * FROM kill_switches WHERE active=1 ORDER BY at DESC")

    def all(self) -> list[dict[str, Any]]:
        return self.store.query("SELECT * FROM kill_switches ORDER BY at DESC")

    def blocking(self, *, workflow: str | None = None, skill: str | None = None, connector: str | None = None) -> dict[str, Any] | None:
        """Return the switch that blocks this work, or None."""
        candidates = [("global", "*")]
        if workflow:
            candidates.append(("workflow", workflow))
        if skill:
            candidates.append(("skill", skill))
        if connector:
            candidates.append(("connector", connector))
        for scope, target in candidates:
            row = self.store.one("SELECT * FROM kill_switches WHERE scope=? AND target=? AND active=1", (scope, target))
            if row:
                return row
        return None


class ConnectorBreaker:
    def __init__(self, store: Store, clock: Clock, audit: AuditChain, threshold: int = 5, cooldown_s: int = 20):
        self.store = store
        self.clock = clock
        self.audit = audit
        self.threshold = threshold
        self.cooldown_s = cooldown_s

    def state(self, name: str) -> dict[str, Any]:
        row = self.store.one("SELECT * FROM breaker_state WHERE name=?", (name,))
        if not row:
            return {"name": name, "state": "closed", "failures": 0, "opened_until": None}
        if row["opened_until"] and parse_ts(row["opened_until"]) > self.clock.now():
            return {**row, "state": "open"}
        if row["opened_until"]:
            return {**row, "state": "half_open"}
        return {**row, "state": "closed"}

    def allows(self, name: str) -> bool:
        return self.state(name)["state"] != "open"

    def record_success(self, name: str) -> None:
        before = self.state(name)["state"]
        with self.store.tx() as conn:
            conn.execute(
                "INSERT INTO breaker_state(name, failures, opened_until, last_change) VALUES (?,0,NULL,?) "
                "ON CONFLICT(name) DO UPDATE SET failures=0, opened_until=NULL, last_change=excluded.last_change",
                (name, self.clock.now_iso()),
            )
        if before != "closed":
            self.audit.append(AuditEntry(actor="kernel", action=f"breaker.close.{name}", kind="system", outcome="ok",
                                         detail={"connector": name, "from": before}))

    def record_failure(self, name: str) -> bool:
        """Count a failure. Returns True if this failure opened the breaker."""
        current = self.state(name)
        failures = int(current.get("failures") or 0) + 1
        opened_until = None
        opened = False
        if failures >= self.threshold or current["state"] == "half_open":
            opened_until = (self.clock.now() + timedelta(seconds=self.cooldown_s)).isoformat()
            opened = True
        with self.store.tx() as conn:
            conn.execute(
                "INSERT INTO breaker_state(name, failures, opened_until, last_change) VALUES (?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET failures=excluded.failures, opened_until=excluded.opened_until, "
                "last_change=excluded.last_change",
                (name, failures, opened_until, self.clock.now_iso()),
            )
        if opened:
            self.audit.append(AuditEntry(actor="kernel", action=f"breaker.open.{name}", kind="system", outcome="opened",
                                         detail={"connector": name, "failures": failures, "cooldown_s": self.cooldown_s}))
        return opened

    def all(self) -> list[dict[str, Any]]:
        return [self.state(r["name"]) for r in self.store.query("SELECT name FROM breaker_state")]
