"""The kernel's own system of record, exposed as a connector-addressable system.

Writes to our own record (booking leave, starting retention clocks, recording
a lifecycle event, upgrading a sourced pointer after consent) go through the
**same governed executor** as calls to TBO's systems: idempotency key, outbox,
read-back verification, audit entry. There is no back door, even for us.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.connectors_sdk import TransportError
from core.db import dumps, loads

if TYPE_CHECKING:
    from core.kernel import Kernel

class SorService:
    def __init__(self, kernel: "Kernel"):
        self.k = kernel

    def handle(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        if op == "get_by_reference":
            row = self.k.store.one("SELECT * FROM sor_effects WHERE reference=?", (payload["reference"],))
            if not row:
                return {"records": []}
            return {"records": [{"id": row["reference"], "kind": row["op"], "reference": row["reference"],
                                 "status": "done", "data": loads(row["data"], {})}]}
        handler = getattr(self, f"_op_{op}", None)
        if handler is None:
            raise TransportError(f"unknown sor operation {op}", status=404)
        reference = payload.get("reference")
        if reference and self.k.store.one("SELECT 1 AS x FROM sor_effects WHERE reference=?", (reference,)):
            # Our own record *is* idempotent on the reference.
            return {"status": "already_applied"}
        result = handler(payload)
        if reference:
            with self.k.store.tx() as conn:
                conn.execute("INSERT INTO sor_effects (reference, op, data, at) VALUES (?,?,?,?)",
                             (reference, op, dumps(result), self.k.clock.now_iso()))
        return result

    # ── operations ────────────────────────────────────────────────────────────

    def _op_record_event(self, p: dict[str, Any]) -> dict[str, Any]:
        self.k.sor.event(p["person_id"], p["event"], p.get("payload") or {}, p.get("actor", "kernel"))
        return {"event": p["event"]}

    def _op_start_retention(self, p: dict[str, Any]) -> dict[str, Any]:
        scheduled = self.k.dpdp.start_retention(p["person_id"], p["from_date"], p.get("actor", "kernel"))
        return {"fields": len(scheduled), "held": [s["field"] for s in scheduled if s["statutory_hold_rule"]]}

    def _op_record_leave(self, p: dict[str, Any]) -> dict[str, Any]:
        person = self.k.sor.person(p["person_id"])
        balances = dict((person or {}).get("attrs", {}).get("leave_balance") or {})
        leave_type = p["leave_type"]
        balances[leave_type] = round(float(balances.get(leave_type, 0)) - float(p["days"]), 1)
        self.k.sor.update_attrs(p["person_id"], {"leave_balance": balances}, p.get("actor", "kernel"),
                                f"{p['days']} day(s) {leave_type} leave booked from {p.get('start')}")
        return {"leave_type": leave_type, "balance_after": balances[leave_type]}

    def _op_mark_exited(self, p: dict[str, Any]) -> dict[str, Any]:
        self.k.sor.update_attrs(p["person_id"], {"status": "exited", "last_working_day": p["last_working_day"]},
                                p.get("actor", "kernel"), "exit completed")
        with self.k.store.tx() as conn:
            conn.execute("UPDATE employment_spells SET end_date=? WHERE person_id=? AND end_date IS NULL",
                         (p["last_working_day"], p["person_id"]))
        return {"status": "exited"}

    def _op_register_pointer(self, p: dict[str, Any]) -> dict[str, Any]:
        """Store a person with no lawful basis as a pointer: public link and nothing derived.

        The fields kept are exactly those the caller passes from the sourcing_basis
        pack's pointer definition; a suppressed identity is never stored again."""
        if self.k.dpdp.is_suppressed(p["public_url"]):
            return {"status": "suppressed", "stored": False}
        identity = self.k.dpdp.identity_hash(p["public_url"])
        person_id = "SRC-" + identity.split(":")[1][:8].upper()
        allowed = set(p.get("store_fields") or [])
        attrs = {k: v for k, v in (p.get("pointer") or {}).items() if k in allowed}
        attrs["identity_hash"] = identity
        self.k.sor.create_person(person_id, "sourced", f"Pointer · {p['pointer'].get('source_id', 'public source')}", attrs,
                                 processing_mode="pointer_only", lawful_basis="none", actor=p.get("actor", "kernel"))
        return {"status": "stored", "person_id": person_id, "fields": sorted(attrs)}

    def _op_register_applicant(self, p: dict[str, Any]) -> dict[str, Any]:
        """An applicant gave us their data for a role: store them with that basis."""
        self.k.sor.create_person(p["candidate_id"], "candidate", p["display_name"], dict(p.get("attrs") or {}),
                                 processing_mode="full", lawful_basis=p.get("basis", "voluntary_provision"),
                                 actor=p.get("actor", "kernel"))
        return {"status": "stored", "person_id": p["candidate_id"]}

    def _op_upgrade_pointer(self, p: dict[str, Any]) -> dict[str, Any]:
        self.k.sor.set_mode(p["person_id"], "full", p.get("basis", "itemised_consent"), p.get("actor", "kernel"),
                            "reply with explicit interest — consent artefact recorded")
        consent_id = self.k.dpdp.record_consent(p["person_id"], p.get("purpose", "recruitment:talent_pool"),
                                                {"source": "reply", "campaign": p.get("campaign"), "notice_version": p.get("notice_version")},
                                                p.get("actor", "kernel"))
        return {"mode": "full", "consent_id": consent_id}

    def _op_suppress_and_delete(self, p: dict[str, Any]) -> dict[str, Any]:
        identity = self.k.dpdp.suppress(p["public_url"], "objection to contact", p.get("actor", "kernel"))
        self.k.dpdp.delete_person(p["person_id"], p.get("actor", "kernel"), "objection ⇒ permanent suppression + pointer deleted")
        return {"suppressed": identity, "deleted": p["person_id"]}


class RoutedTransport:
    """Sends system 'sor' to our own record and everything else to the TBO mocks."""

    def __init__(self, mocks_transport: Any, sor: SorService):
        self.mocks = mocks_transport
        self.sor = sor

    def call(self, system: str, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        if system == "sor":
            return self.sor.handle(op, payload)
        return self.mocks.call(system, op, payload)
