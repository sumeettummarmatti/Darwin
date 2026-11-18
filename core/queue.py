"""Human queue, context packets and approval receipts.

A queue item carries a **context packet**: the computed values, the clauses
applied (pack@version + rule IDs), the conflict, and the single question a
human must answer. "Please review" is not a packet.

Approving binds to the packet's ``context_hash``. The UI echoes the hash of
the packet it rendered; if the packet changed since, the approval is refused
as stale. The receipt stores the hash *and* the snapshot, so in a dispute TBO
can prove exactly what the approver was shown.
"""

from __future__ import annotations

import hashlib
from typing import Any

from core.audit import AuditChain, AuditEntry
from core.clock import Clock, new_id
from core.db import Store, dumps, loads
from core.reserved import ReservedRegistry
from core.types import Principal


class QueueError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def context_hash(packet: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(dumps(packet).encode()).hexdigest()


def decode_item(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["packet"] = loads(item["packet"], {})
    item["approver_roles"] = loads(item["approver_roles"], [])
    item["approvals"] = loads(item["approvals"], [])
    item["receipt_ids"] = loads(item["receipt_ids"], [])
    item["decision"] = loads(item["decision"], None) if item.get("decision") else None
    item["context_hash"] = context_hash(item["packet"])
    return item


class HumanQueue:
    def __init__(self, store: Store, clock: Clock, audit: AuditChain, registry: callable):
        self.store = store
        self.clock = clock
        self.audit = audit
        self._registry = registry          # () -> ReservedRegistry (hot-reloadable)

    @property
    def registry(self) -> ReservedRegistry:
        return self._registry()

    def create(self, *, kind: str, title: str, question: str, packet: dict[str, Any], approver_roles: list[str],
               run_id: str | None = None, step_id: str | None = None, action: str | None = None) -> dict[str, Any]:
        if not question or question.strip().lower() in ("please review", "review"):
            raise QueueError("a context packet must ask one specific question")
        item_id = new_id("hq")
        with self.store.tx() as conn:
            conn.execute(
                "INSERT INTO human_queue (id, run_id, step_id, kind, action, title, packet, question, approver_roles, "
                "status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (item_id, run_id, step_id, kind, action, title, dumps(packet), question, dumps(approver_roles),
                 "open", self.clock.now_iso()),
            )
        self.audit.append(AuditEntry(
            actor="kernel", action=f"queue.{kind}", kind="human", outcome="held", run_id=run_id, step_id=step_id,
            inputs={"queue_id": item_id, "action": action, "approver_roles": approver_roles},
            policy_versions=[c.get("pack") for c in packet.get("clauses", []) if c.get("pack")],
            rule_ids=[r for c in packet.get("clauses", []) for r in c.get("rule_ids", [])],
            detail={"question": question, "context_hash": context_hash(packet)},
        ))
        return self.get(item_id)

    def get(self, item_id: str) -> dict[str, Any]:
        row = self.store.one("SELECT * FROM human_queue WHERE id=?", (item_id,))
        if not row:
            raise QueueError(f"no queue item {item_id}", 404)
        return decode_item(row)

    def list(self, status: str | None = "open", limit: int = 200) -> list[dict[str, Any]]:
        if status:
            rows = self.store.query("SELECT * FROM human_queue WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit))
        else:
            rows = self.store.query("SELECT * FROM human_queue ORDER BY created_at DESC LIMIT ?", (limit,))
        return [decode_item(r) for r in rows]

    def open_for_step(self, run_id: str, step_id: str) -> dict[str, Any] | None:
        row = self.store.one("SELECT * FROM human_queue WHERE run_id=? AND step_id=? AND status='open'", (run_id, step_id))
        return decode_item(row) if row else None

    def update_packet(self, item_id: str, packet: dict[str, Any]) -> None:
        with self.store.tx() as conn:
            conn.execute("UPDATE human_queue SET packet=? WHERE id=?", (dumps(packet), item_id))

    def decide(self, item_id: str, approver: Principal, decision: str, *, context_hash_seen: str, note: str = "",
               values: dict[str, Any] | None = None, channel: str = "web", subject: str | None = None) -> dict[str, Any]:
        item = self.get(item_id)
        if item["status"] != "open":
            raise QueueError(f"{item_id} is already {item['status']}", 409)
        if approver.kind != "human":
            # The kernel, not the UI, refuses: an agent can never decide a queue item.
            self.audit.append(AuditEntry(actor=approver.label, action=f"queue.decide.{item.get('action') or item['kind']}",
                                         kind="reserved", outcome="refused", run_id=item["run_id"], step_id=item["step_id"],
                                         detail={"reason": "agents cannot decide human-queue items", "status": 403}))
            raise QueueError("403 RESERVED: agents cannot decide human-queue items", 403)
        if context_hash_seen != item["context_hash"]:
            raise QueueError("stale context: the packet changed after it was displayed — reload before deciding", 409)

        roles_required = item["approver_roles"]
        mode = "any_of"
        if item["kind"] == "reserved" and item.get("action"):
            entry = self.registry.entries.get(item["action"])
            if entry:
                mode = entry.mode
        if roles_required:
            if mode == "sequential":
                needed = roles_required[len(item["approvals"])]
                if needed not in approver.roles:
                    raise QueueError(f"next approval must come from role '{needed}'", 403)
            elif not set(roles_required) & set(approver.roles):
                raise QueueError(f"approver must hold one of {roles_required}", 403)

        receipt_id = new_id("rcpt")
        decided_at = self.clock.now_iso()
        policy_versions = [c.get("pack") for c in item["packet"].get("clauses", []) if c.get("pack")]
        seq = self.audit.append(AuditEntry(
            actor=approver.label, action=f"decide.{item.get('action') or item['kind']}", kind="human",
            outcome=decision, run_id=item["run_id"], step_id=item["step_id"],
            inputs={"queue_id": item_id, "values": values or {}},
            policy_versions=policy_versions,
            detail={"receipt_id": receipt_id, "context_hash": item["context_hash"], "note": note, "channel": channel,
                    "roles": approver.roles},
        ))
        with self.store.tx() as conn:
            conn.execute(
                "INSERT INTO receipts (id, queue_id, action, subject, approver, decision, context_hash, context_snapshot, "
                "policy_versions, note, channel, decided_at, audit_seq) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (receipt_id, item_id, item.get("action") or item["kind"], subject, dumps(approver.as_dict()), decision,
                 item["context_hash"], dumps(item["packet"]), dumps(policy_versions), note, channel, decided_at, seq),
            )
            approvals = item["approvals"] + [{"by": approver.id, "name": approver.name, "roles": approver.roles,
                                              "decision": decision, "receipt_id": receipt_id, "at": decided_at}]
            receipts = item["receipt_ids"] + [receipt_id]
            finished = (decision != "approve" or mode != "sequential" or len(approvals) >= len(roles_required))
            conn.execute(
                "UPDATE human_queue SET approvals=?, receipt_ids=?, status=?, decided_at=?, decision=? WHERE id=?",
                (dumps(approvals), dumps(receipts), "decided" if finished else "open",
                 decided_at if finished else None,
                 dumps({"decision": decision, "values": values or {}, "note": note}) if finished else None, item_id),
            )
        return self.get(item_id)

    def receipts(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.store.query("SELECT * FROM receipts ORDER BY decided_at DESC LIMIT ?", (limit,))
        for r in rows:
            r["approver"] = loads(r["approver"], {})
            r["context_snapshot"] = loads(r["context_snapshot"], {})
            r["policy_versions"] = loads(r["policy_versions"], [])
        return rows

    def verify_receipt(self, receipt_id: str) -> dict[str, Any]:
        row = self.store.one("SELECT * FROM receipts WHERE id=?", (receipt_id,))
        if not row:
            raise QueueError("no such receipt", 404)
        recomputed = context_hash(loads(row["context_snapshot"], {}))
        return {"receipt_id": receipt_id, "stored_hash": row["context_hash"], "recomputed_hash": recomputed,
                "matches": recomputed == row["context_hash"]}
