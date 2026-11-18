"""SQLite-backed store for the system of record, workflow state, outbox and audit.

Decision D13 (PROGRESS.md): the week-1 spike chose our own durable state
machine over Temporal. State lives in one database alongside the HR record, so
cost and automation metrics come from the same source of truth as the data.
SQLite keeps ``make up`` dependency-free; the schema is plain SQL that ports to
Postgres unchanged.

All access goes through ``Store.tx()`` which serialises writers with a lock —
simple, correct, and fast enough for a single-tenant demo.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- ── system of record ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,            -- EMP-xxxx / CAND-xxxx / SRC-xxxx
    kind TEXT NOT NULL,             -- employee | candidate | sourced
    display_name TEXT NOT NULL,
    attrs TEXT NOT NULL,            -- non-PII attributes (grade, location, org unit…)
    processing_mode TEXT NOT NULL DEFAULT 'full',   -- full | pointer_only | suppressed
    lawful_basis TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS employment_spells (
    id TEXT PRIMARY KEY, person_id TEXT NOT NULL, start_date TEXT NOT NULL,
    end_date TEXT, employment_type TEXT NOT NULL, grade TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pii_fields (     -- PII as rows: purpose tags + retention clocks
    person_id TEXT NOT NULL, field TEXT NOT NULL, token TEXT NOT NULL,
    purposes TEXT NOT NULL, retention_until TEXT, statutory_hold_rule TEXT,
    deleted_at TEXT,
    PRIMARY KEY (person_id, field)
);
CREATE TABLE IF NOT EXISTS vault (token TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lifecycle_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL, event TEXT NOT NULL,
    payload TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS consent_records (
    id TEXT PRIMARY KEY, person_id TEXT NOT NULL, purpose TEXT NOT NULL,
    status TEXT NOT NULL, artefact TEXT NOT NULL, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sor_effects (         -- idempotency ledger for writes to our own record
    reference TEXT PRIMARY KEY, op TEXT NOT NULL, data TEXT NOT NULL, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suppression_list (
    identity_hash TEXT PRIMARY KEY, reason TEXT NOT NULL, at TEXT NOT NULL
);

-- ── workflow state ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workflow_runs (
    id TEXT PRIMARY KEY, workflow TEXT NOT NULL, version INTEGER NOT NULL,
    subject TEXT, inputs TEXT NOT NULL, facts TEXT NOT NULL, status TEXT NOT NULL,
    principal TEXT NOT NULL, channel TEXT NOT NULL, created_at TEXT NOT NULL,
    closed_at TEXT, cost_inr REAL NOT NULL DEFAULT 0, budget_inr REAL,
    policy_versions TEXT NOT NULL DEFAULT '[]', tags TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS step_runs (
    run_id TEXT NOT NULL, step_id TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL,
    outputs TEXT, attempts INTEGER NOT NULL DEFAULT 0, human_touch INTEGER NOT NULL DEFAULT 0,
    tier INTEGER NOT NULL DEFAULT 0, cost_inr REAL NOT NULL DEFAULT 0,
    scheduled_for TEXT, started_at TEXT, finished_at TEXT, error TEXT, note TEXT, gate TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, step_id)
);
CREATE TABLE IF NOT EXISTS outbox (
    idem_key TEXT PRIMARY KEY, run_id TEXT, step_id TEXT, connector TEXT NOT NULL,
    action TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0, result TEXT, last_error TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS human_queue (
    id TEXT PRIMARY KEY, run_id TEXT, step_id TEXT, kind TEXT NOT NULL,
    action TEXT, title TEXT NOT NULL, packet TEXT NOT NULL, question TEXT NOT NULL,
    approver_roles TEXT NOT NULL, approvals TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL, created_at TEXT NOT NULL, decided_at TEXT,
    decision TEXT, receipt_ids TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS receipts (
    id TEXT PRIMARY KEY, queue_id TEXT, action TEXT NOT NULL, subject TEXT,
    approver TEXT NOT NULL, decision TEXT NOT NULL, context_hash TEXT NOT NULL,
    context_snapshot TEXT NOT NULL, policy_versions TEXT NOT NULL, note TEXT,
    channel TEXT NOT NULL, decided_at TEXT NOT NULL, audit_seq INTEGER
);

-- ── governance ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, run_id TEXT, step_id TEXT,
    actor TEXT NOT NULL, on_behalf_of TEXT, action TEXT NOT NULL, kind TEXT NOT NULL,
    inputs TEXT NOT NULL, policy_versions TEXT NOT NULL, rule_ids TEXT NOT NULL,
    prompt_version TEXT, model_id TEXT, tier INTEGER NOT NULL DEFAULT 0,
    tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,
    inr REAL NOT NULL DEFAULT 0, latency_ms INTEGER NOT NULL DEFAULT 0,
    outcome TEXT NOT NULL, detail TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_run ON audit(run_id);
CREATE TABLE IF NOT EXISTS model_calls (
    id TEXT PRIMARY KEY, run_id TEXT, step_id TEXT, skill TEXT NOT NULL,
    tier INTEGER NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, region TEXT,
    prompt_version TEXT, source_record TEXT NOT NULL, outbound_payload TEXT NOT NULL,
    stripped_fields TEXT NOT NULL, response TEXT NOT NULL, tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL, inr REAL NOT NULL, escalation_reason TEXT, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kill_switches (
    scope TEXT NOT NULL, target TEXT NOT NULL, active INTEGER NOT NULL,
    reason TEXT, actor TEXT, at TEXT NOT NULL, PRIMARY KEY (scope, target)
);
CREATE TABLE IF NOT EXISTS breaker_state (
    name TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0,
    opened_until TEXT, last_change TEXT
);
CREATE TABLE IF NOT EXISTS objections (
    id TEXT PRIMARY KEY, run_id TEXT, step_id TEXT, gate TEXT NOT NULL, class TEXT NOT NULL,
    severity TEXT NOT NULL, claim TEXT NOT NULL, evidence TEXT NOT NULL,
    suggested_action TEXT, layer TEXT NOT NULL, resolution TEXT, upheld INTEGER,
    at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._depth = 0

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """A serialised transaction. Nested calls join the outer transaction."""
        with self._lock:
            outer = self._depth == 0
            if outer:
                self._conn.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield self._conn
            except BaseException:
                self._depth -= 1
                if outer:
                    self._conn.execute("ROLLBACK")
                raise
            else:
                self._depth -= 1
                if outer:
                    self._conn.execute("COMMIT")

    def query(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def loads(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    return json.loads(value)
