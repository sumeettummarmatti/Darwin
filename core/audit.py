"""The audit chain: append-only, hash-linked, one entry per kernel step.

Each entry stores the hash of the previous one, so editing or deleting any row
breaks verification from that point on. Explanations ("why did this happen?")
are built from these rows — never by asking a model to reconstruct events.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from core.clock import Clock
from core.db import Store, dumps, loads

GENESIS = "sha256:genesis"

# Columns that participate in the hash, in a fixed order.
_HASHED = (
    "at", "run_id", "step_id", "actor", "on_behalf_of", "action", "kind", "inputs",
    "policy_versions", "rule_ids", "prompt_version", "model_id", "tier", "tokens_in",
    "tokens_out", "inr", "latency_ms", "outcome", "detail",
)


@dataclass
class AuditEntry:
    actor: str                                   # "agent:onboarding.plan@v3" | "human:USR-114" | "kernel"
    action: str                                  # what was attempted
    kind: str                                    # step | policy | reserved | connector | model | prativaad | human | system
    outcome: str                                 # ok | refused | held | failed | retried | objected | cleared | …
    run_id: str | None = None
    step_id: str | None = None
    on_behalf_of: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    policy_versions: list[str] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    prompt_version: str | None = None
    model_id: str | None = None
    tier: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    inr: float = 0.0
    latency_ms: int = 0
    detail: dict[str, Any] = field(default_factory=dict)


def _digest(prev_hash: str, row: dict[str, Any]) -> str:
    material = prev_hash + "|" + dumps({k: row.get(k) for k in _HASHED})
    return "sha256:" + hashlib.sha256(material.encode()).hexdigest()


class AuditChain:
    def __init__(self, store: Store, clock: Clock):
        self.store = store
        self.clock = clock

    def append(self, entry: AuditEntry) -> int:
        row = {
            "at": self.clock.now_iso(),
            "run_id": entry.run_id,
            "step_id": entry.step_id,
            "actor": entry.actor,
            "on_behalf_of": entry.on_behalf_of,
            "action": entry.action,
            "kind": entry.kind,
            "inputs": dumps(entry.inputs),
            "policy_versions": dumps(entry.policy_versions),
            "rule_ids": dumps(entry.rule_ids),
            "prompt_version": entry.prompt_version,
            "model_id": entry.model_id,
            "tier": entry.tier,
            "tokens_in": entry.tokens_in,
            "tokens_out": entry.tokens_out,
            "inr": round(entry.inr, 6),
            "latency_ms": entry.latency_ms,
            "outcome": entry.outcome,
            "detail": dumps(entry.detail),
        }
        with self.store.tx() as conn:
            last = conn.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
            prev = last["hash"] if last else GENESIS
            row["prev_hash"] = prev
            row["hash"] = _digest(prev, row)
            cols = ", ".join(row.keys())
            marks = ", ".join("?" for _ in row)
            cur = conn.execute(f"INSERT INTO audit ({cols}) VALUES ({marks})", list(row.values()))
            return int(cur.lastrowid)

    def verify(self) -> dict[str, Any]:
        """Walk the chain. Returns {ok, checked, broken_at, reason}."""
        prev = GENESIS
        checked = 0
        for row in self.store.query("SELECT * FROM audit ORDER BY seq"):
            if row["prev_hash"] != prev:
                return {"ok": False, "checked": checked, "broken_at": row["seq"], "reason": "prev_hash does not match the previous entry (row deleted or reordered)"}
            if _digest(prev, row) != row["hash"]:
                return {"ok": False, "checked": checked, "broken_at": row["seq"], "reason": "entry content does not match its hash (row edited)"}
            prev = row["hash"]
            checked += 1
        return {"ok": True, "checked": checked, "broken_at": None, "reason": None, "head": prev}

    def for_run(self, run_id: str) -> list[dict[str, Any]]:
        return [decode(r) for r in self.store.query("SELECT * FROM audit WHERE run_id=? ORDER BY seq", (run_id,))]

    def recent(self, limit: int = 200, kind: str | None = None, outcome: str | None = None) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM audit", []
        clauses = []
        if kind:
            clauses.append("kind=?")
            params.append(kind)
        if outcome:
            clauses.append("outcome=?")
            params.append(outcome)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY seq DESC LIMIT ?"
        params.append(limit)
        return [decode(r) for r in self.store.query(sql, params)]


def decode(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("inputs", "policy_versions", "rule_ids", "detail"):
        out[key] = loads(out.get(key), {} if key in ("inputs", "detail") else [])
    return out
