"""Stand-ins for TBO's mock IT / Admin / Finance APIs.

TBO will hand every team the same starter kit; until its contracts arrive
(PROGRESS.md Q3) these mocks implement the systems the brief names — ticketing,
asset allocation, access cards, email + directory, payroll setup — plus an ATS,
a sourcing mock and a mail mock (no real sends, ever).

Deliberately realistic in the ways that matter for the demo:

* **Not idempotent.** Calling ``allocate`` twice with the same reference gives
  two laptops, exactly like a naive real system. Duplicate prevention is the
  kernel's job (outbox + read-back), and the tests prove it.
* **Chaos modes** per system: ``error_500``, ``timeout_after_commit``,
  ``ack_no_commit`` and ``down``. These drive the retry-storm demo and the
  chaos tests.

The mocks keep their own database: they are "external", not part of our record.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.connectors_sdk import TransportError

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY, system TEXT NOT NULL, kind TEXT NOT NULL, reference TEXT,
    data TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS records_ref ON records(system, reference);
CREATE TABLE IF NOT EXISTS inventory (
    serial TEXT PRIMARY KEY, asset_class TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chaos (
    system TEXT PRIMARY KEY, mode TEXT NOT NULL, remaining INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS calls (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, system TEXT, op TEXT, outcome TEXT, at TEXT
);
"""

CHAOS_MODES = ("error_500", "timeout_after_commit", "ack_no_commit", "down")
READ_OPS = {"allocations_for", "returns_for", "cards_for", "signals", "applicants"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class TboMocks:
    def __init__(self, path: Path | str):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._ops: dict[tuple[str, str], Callable[[dict[str, Any]], dict[str, Any]]] = {
            ("tickets", "open_ticket"): self._open_ticket,
            ("tickets", "update_ticket"): self._update_ticket,
            ("tickets", "comment"): self._comment,
            ("assets", "allocate"): self._allocate,
            ("assets", "release"): self._release,
            ("assets", "recover"): self._recover,
            ("assets", "allocations_for"): self._allocations_for,
            ("assets", "returns_for"): self._returns_for,
            ("access", "issue_card"): self._issue_card,
            ("access", "revoke_card"): self._revoke_card,
            ("access", "cards_for"): self._cards_for,
            ("directory", "create_account"): self._create_account,
            ("directory", "suspend_account"): self._suspend_account,
            ("payroll", "setup_employee"): self._payroll_setup,
            ("payroll", "prepare_settlement"): self._prepare_settlement,
            ("payroll", "deactivate"): self._payroll_deactivate,
            ("mail", "send"): self._send_mail,
            ("calendar", "create_event"): self._create_event,
            ("esign", "send_envelope"): self._send_envelope,
        }

    # ── plumbing ──────────────────────────────────────────────────────────────

    def _exec(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _rows(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        with self._lock:
            out = []
            for r in self._conn.execute(sql, params).fetchall():
                d = dict(r)
                if "data" in d:
                    d["data"] = json.loads(d["data"])
                out.append(d)
            return out

    def _insert(self, system: str, kind: str, data: dict[str, Any], reference: str | None, status: str = "open") -> dict[str, Any]:
        rid = f"{system[:3].upper()}-{secrets.token_hex(3).upper()}"
        self._exec(
            "INSERT INTO records(id, system, kind, reference, data, status, created_at) VALUES (?,?,?,?,?,?,?)",
            (rid, system, kind, reference, json.dumps(data), status, _now()),
        )
        return {"id": rid, "kind": kind, "reference": reference, "status": status, "data": data}

    def handle(self, system: str, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Entry point used by the in-process transport and the HTTP router."""
        if op == "get_by_reference":
            return {"records": self.by_reference(system, payload["reference"])}
        handler = self._ops.get((system, op))
        if handler is None:
            raise TransportError(f"unknown operation {system}.{op}", status=404)
        # Reads only suffer outages; write-only failure modes (timeout after commit,
        # 200 without commit) are kept for the writes they are meant to exercise.
        mode = self._take_chaos(system, read_only=op in READ_OPS)
        if mode in ("error_500", "down"):
            self._log(system, op, "500")
            raise TransportError(f"{system} returned 500 Internal Server Error", status=500)
        if mode == "ack_no_commit":
            self._log(system, op, "ack_no_commit")
            return {"id": f"{system[:3].upper()}-GHOST", "status": "accepted"}
        with self._lock:
            result = handler(payload)
        if mode == "timeout_after_commit":
            self._log(system, op, "timeout_after_commit")
            raise TransportError(f"{system} timed out (the write may have landed)", status=504, timeout=True)
        self._log(system, op, "ok")
        return result

    def _log(self, system: str, op: str, outcome: str) -> None:
        self._exec("INSERT INTO calls(system, op, outcome, at) VALUES (?,?,?,?)", (system, op, outcome, _now()))

    # ── chaos control ─────────────────────────────────────────────────────────

    def set_chaos(self, system: str, mode: str, count: int = 1) -> None:
        if mode not in CHAOS_MODES:
            raise ValueError(f"unknown chaos mode {mode}")
        self._exec(
            "INSERT INTO chaos(system, mode, remaining) VALUES (?,?,?) "
            "ON CONFLICT(system) DO UPDATE SET mode=excluded.mode, remaining=excluded.remaining",
            (system, mode, -1 if mode == "down" else count),
        )

    def clear_chaos(self, system: str | None = None) -> None:
        if system:
            self._exec("DELETE FROM chaos WHERE system=?", (system,))
        else:
            self._exec("DELETE FROM chaos")

    def chaos_state(self) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM chaos")

    def _take_chaos(self, system: str, read_only: bool = False) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT mode, remaining FROM chaos WHERE system=?", (system,)).fetchone()
            if not row:
                return None
            if read_only and row["mode"] not in ("error_500", "down"):
                return None
            if row["remaining"] > 0:
                if row["remaining"] == 1:
                    self._conn.execute("DELETE FROM chaos WHERE system=?", (system,))
                else:
                    self._conn.execute("UPDATE chaos SET remaining=remaining-1 WHERE system=?", (system,))
            return row["mode"]

    # ── inspection (tests, payload viewer, "exactly one laptop") ──────────────

    def by_reference(self, system: str, reference: str) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM records WHERE system=? AND reference=? ORDER BY created_at", (system, reference))

    def records(self, system: str | None = None, kind: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        sql, params, where = "SELECT * FROM records", [], []
        if system:
            where.append("system=?")
            params.append(system)
        if kind:
            where.append("kind=?")
            params.append(kind)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return self._rows(sql, params)

    def call_log(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM calls ORDER BY seq DESC LIMIT ?", (limit,))

    # ── seed ──────────────────────────────────────────────────────────────────

    def seed(self, prior_allocations: list[dict[str, Any]] | None = None) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM records")
            self._conn.execute("DELETE FROM inventory")
            self._conn.execute("DELETE FROM chaos")
            self._conn.execute("DELETE FROM calls")
            for cls, count in (("A", 15), ("B", 30), ("C", 10)):
                for n in range(count):
                    self._conn.execute("INSERT INTO inventory VALUES (?,?,?)", (f"LT-{cls}{n:03d}", cls, "in_stock"))
        for prior in prior_allocations or []:
            alloc = self._insert("assets", "allocation", prior["allocation"], prior.get("reference"), status="open")
            if prior.get("returned_on"):
                self._insert("assets", "return", {"allocation_id": alloc["id"], "returned_on": prior["returned_on"],
                                                  "holder_token": prior["allocation"]["holder_token"]}, None, status="closed")

    # ── tickets ───────────────────────────────────────────────────────────────

    def _open_ticket(self, p: dict[str, Any]) -> dict[str, Any]:
        rec = self._insert("tickets", "ticket", {k: p.get(k) for k in ("queue", "title", "body", "priority", "due")}, p.get("reference"))
        return {"ticket_id": rec["id"], "status": "open"}

    def _update_ticket(self, p: dict[str, Any]) -> dict[str, Any]:
        self._exec("UPDATE records SET status=? WHERE id=?", (p["status"], p["ticket_id"]))
        return {"ticket_id": p["ticket_id"], "status": p["status"]}

    def _comment(self, p: dict[str, Any]) -> dict[str, Any]:
        rec = self._insert("tickets", "comment", {"ticket_id": p["ticket_id"], "text": p["text"]}, p.get("reference"), status="closed")
        return {"comment_id": rec["id"]}

    # ── assets ────────────────────────────────────────────────────────────────

    def _allocate(self, p: dict[str, Any]) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT serial FROM inventory WHERE asset_class=? AND status='in_stock' ORDER BY serial LIMIT 1",
            (p["asset_class"],),
        ).fetchone()
        if not row:
            raise TransportError(f"no class {p['asset_class']} laptops in stock", status=409)
        self._conn.execute("UPDATE inventory SET status='allocated' WHERE serial=?", (row["serial"],))
        data = {"serial": row["serial"], "asset_class": p["asset_class"], "holder_token": p["holder_token"],
                "holder_ref": p.get("holder_ref"), "software": p.get("software", [])}
        rec = self._insert("assets", "allocation", data, p.get("reference"))
        return {"allocation_id": rec["id"], "serial": row["serial"], "status": "open"}

    def _release(self, p: dict[str, Any]) -> dict[str, Any]:
        rows = self._rows("SELECT * FROM records WHERE id=?", (p["allocation_id"],))
        if rows:
            self._conn.execute("UPDATE records SET status='closed' WHERE id=?", (p["allocation_id"],))
            self._conn.execute("UPDATE inventory SET status='in_stock' WHERE serial=?", (rows[0]["data"].get("serial"),))
        return {"allocation_id": p["allocation_id"], "status": "closed"}

    def _recover(self, p: dict[str, Any]) -> dict[str, Any]:
        rec = self._insert("assets", "recovery", {"holder_token": p["holder_token"], "due": p.get("due")}, p.get("reference"))
        return {"recovery_id": rec["id"], "status": "open"}

    def _allocations_for(self, p: dict[str, Any]) -> dict[str, Any]:
        rows = [r for r in self._rows("SELECT * FROM records WHERE system='assets' AND kind='allocation'")
                if r["data"].get("holder_token") == p["holder_token"]]
        return {"allocations": rows}

    def _returns_for(self, p: dict[str, Any]) -> dict[str, Any]:
        rows = [r for r in self._rows("SELECT * FROM records WHERE system='assets' AND kind='return'")
                if r["data"].get("allocation_id") == p["allocation_id"]]
        return {"returns": rows}

    # ── access cards ──────────────────────────────────────────────────────────

    def _issue_card(self, p: dict[str, Any]) -> dict[str, Any]:
        rec = self._insert("access", "card", {"holder_token": p["holder_token"], "zones": p.get("zones", []),
                                              "valid_from": p.get("valid_from")}, p.get("reference"), status="active")
        return {"card_id": rec["id"], "status": "active"}

    def _revoke_card(self, p: dict[str, Any]) -> dict[str, Any]:
        cards = [r for r in self._rows("SELECT * FROM records WHERE system='access' AND kind='card' AND status='active'")
                 if r["data"].get("holder_token") == p["holder_token"]]
        for card in cards:
            self._conn.execute("UPDATE records SET status='revoked' WHERE id=?", (card["id"],))
        rec = self._insert("access", "revocation", {"holder_token": p["holder_token"], "cards": [c["id"] for c in cards],
                                                    "effective_at": p.get("effective_at")}, p.get("reference"), status="closed")
        return {"revocation_id": rec["id"], "revoked": [c["id"] for c in cards]}

    def _cards_for(self, p: dict[str, Any]) -> dict[str, Any]:
        rows = [r for r in self._rows("SELECT * FROM records WHERE system='access' AND kind='card'")
                if r["data"].get("holder_token") == p["holder_token"]]
        return {"cards": rows}

    # ── directory / email ─────────────────────────────────────────────────────

    def _create_account(self, p: dict[str, Any]) -> dict[str, Any]:
        email = f"{p['email_local']}@tbo-synthetic.example"
        rec = self._insert("directory", "account", {"email": email, "display_name": p["display_name"],
                                                    "manager_id": p.get("manager_id"), "buddy_id": p.get("buddy_id"),
                                                    "org_unit": p.get("org_unit")}, p.get("reference"), status="active")
        return {"account_id": rec["id"], "email": email}

    def _suspend_account(self, p: dict[str, Any]) -> dict[str, Any]:
        rec = self._insert("directory", "suspension", {"employee_ref": p["employee_ref"], "effective_at": p.get("effective_at")},
                           p.get("reference"), status="closed")
        return {"suspension_id": rec["id"], "status": "suspended"}

    # ── payroll ───────────────────────────────────────────────────────────────

    def _payroll_setup(self, p: dict[str, Any]) -> dict[str, Any]:
        rec = self._insert("payroll", "employee", {k: p.get(k) for k in ("employee_ref", "pan_token", "bank_token", "band", "start_date")},
                           p.get("reference"), status="active")
        return {"payroll_id": rec["id"], "status": "active"}

    def _prepare_settlement(self, p: dict[str, Any]) -> dict[str, Any]:
        rec = self._insert("payroll", "settlement_draft", dict(p), p.get("reference"), status="draft")
        return {"settlement_id": rec["id"], "status": "draft"}

    def _payroll_deactivate(self, p: dict[str, Any]) -> dict[str, Any]:
        rec = self._insert("payroll", "deactivation", dict(p), p.get("reference"), status="closed")
        return {"deactivation_id": rec["id"]}

    # ── mail (captured, never sent) and spares ────────────────────────────────

    def _send_mail(self, p: dict[str, Any]) -> dict[str, Any]:
        rec = self._insert("mail", "message", {k: p.get(k) for k in ("to", "subject", "body", "campaign")}, p.get("reference"), status="captured")
        return {"message_id": rec["id"], "status": "captured"}

    def _create_event(self, p: dict[str, Any]) -> dict[str, Any]:
        rec = self._insert("calendar", "event", dict(p), p.get("reference"))
        return {"event_id": rec["id"]}

    def _send_envelope(self, p: dict[str, Any]) -> dict[str, Any]:
        rec = self._insert("esign", "envelope", dict(p), p.get("reference"))
        return {"envelope_id": rec["id"]}


class InProcessTransport:
    """Calls the mocks directly. The default: no ports, no setup."""

    def __init__(self, mocks: TboMocks):
        self.mocks = mocks

    def call(self, system: str, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.mocks.handle(system, op, payload)


class HttpTransport:
    """Calls a mock (or, later, TBO's real mock) over HTTP. Lives here, not in a skill."""

    def __init__(self, base_url: str, timeout_s: float = 5.0):
        import httpx  # imported lazily so the in-process path has no network client at all

        self._client = httpx.Client(base_url=base_url, timeout=timeout_s)

    def call(self, system: str, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        try:
            resp = self._client.post(f"/mocks/{system}/{op}", json=payload)
        except httpx.TimeoutException as exc:
            raise TransportError(str(exc), status=504, timeout=True) from exc
        if resp.status_code >= 400:
            raise TransportError(resp.text, status=resp.status_code, timeout=resp.status_code == 504)
        return resp.json()
