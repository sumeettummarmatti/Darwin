"""DPDP Act mechanics: retention clocks, statutory holds, data-subject requests,
consent artefacts and the suppression list.

Retention periods and holds come from the ``dpdp`` policy pack — never from code.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any, Callable

from core.audit import AuditChain, AuditEntry
from core.clock import Clock, new_id
from core.db import Store, dumps, loads
from core.pii import Vault
from core.rules.packs import PolicyPack
from core.sor import SystemOfRecord


class Dpdp:
    def __init__(self, store: Store, clock: Clock, audit: AuditChain, vault: Vault, sor: SystemOfRecord,
                 dpdp: Callable[[], PolicyPack]):
        self.store = store
        self.clock = clock
        self.audit = audit
        self.vault = vault
        self.sor = sor
        self._dpdp = dpdp

    # ── retention ─────────────────────────────────────────────────────────────

    def start_retention(self, person_id: str, event_date: str, actor: str) -> list[dict[str, Any]]:
        """Start every PII field's retention clock from a lifecycle event (exit)."""
        pack = self._dpdp()
        scheduled = []
        for f in self.vault.fields_for(person_id):
            if f["deleted_at"]:
                continue
            meta = pack.evaluate({"field": f["field"]}).outputs
            days = int(meta.get("retention_days_after_exit", 0))
            until = (date.fromisoformat(event_date[:10]) + timedelta(days=days)).isoformat()
            hold = meta.get("statutory_hold_rule")
            with self.store.tx() as conn:
                conn.execute("UPDATE pii_fields SET retention_until=?, statutory_hold_rule=? WHERE person_id=? AND field=?",
                             (until, hold, person_id, f["field"]))
            scheduled.append({"field": f["field"], "retention_until": until, "statutory_hold_rule": hold})
        self.audit.append(AuditEntry(actor=actor, action="dpdp.retention.start", kind="governance", outcome="ok",
                                     policy_versions=[pack.ref], inputs={"person": person_id, "from": event_date},
                                     detail={"fields": scheduled}))
        self.sor.event(person_id, "dpdp.retention_started", {"from": event_date, "fields": len(scheduled)}, actor)
        return scheduled

    def sweep(self, *, execute: bool = True) -> dict[str, Any]:
        """Delete fields whose retention ran out; hold back statutory fields with the rule cited."""
        today = self.clock.today()
        pack = self._dpdp()
        deleted, held = [], []
        for row in self.store.query("SELECT * FROM pii_fields WHERE deleted_at IS NULL AND retention_until IS NOT NULL AND retention_until <= ?", (today,)):
            if row["statutory_hold_rule"]:
                held.append({"person": row["person_id"], "field": row["field"], "rule": row["statutory_hold_rule"]})
                continue
            if execute:
                self.vault.erase(row["person_id"], row["field"])
            deleted.append({"person": row["person_id"], "field": row["field"], "retention_until": row["retention_until"]})
        self.audit.append(AuditEntry(actor="kernel:retention", action="dpdp.retention.sweep", kind="governance", outcome="ok",
                                     policy_versions=[pack.ref], inputs={"as_of": today},
                                     detail={"deleted": deleted, "held": held}))
        return {"as_of": today, "deleted": deleted, "held": held}

    def schedule(self) -> list[dict[str, Any]]:
        rows = self.store.query("SELECT p.person_id, p.field, p.retention_until, p.statutory_hold_rule, p.deleted_at, pe.display_name "
                                "FROM pii_fields p LEFT JOIN people pe ON pe.id=p.person_id WHERE p.retention_until IS NOT NULL "
                                "ORDER BY p.retention_until")
        return rows

    # ── data-subject requests ─────────────────────────────────────────────────

    def access(self, person_id: str, actor: str) -> dict[str, Any]:
        person = self.sor.person(person_id)
        if person is None:
            raise KeyError(person_id)
        fields = [{"field": f["field"], "purposes": f["purposes"], "retention_until": f["retention_until"],
                   "statutory_hold_rule": f["statutory_hold_rule"], "deleted": bool(f["deleted_at"])}
                  for f in self.vault.fields_for(person_id)]
        runs = self.store.query("SELECT id, workflow, status, created_at, closed_at FROM workflow_runs WHERE subject=? ORDER BY created_at", (person_id,))
        decisions = self.store.query("SELECT id, action, decision, decided_at, note FROM receipts WHERE subject=? ORDER BY decided_at", (person_id,))
        model_calls = self.store.query(
            "SELECT m.skill, m.model, m.tier, m.at FROM model_calls m JOIN workflow_runs r ON r.id=m.run_id WHERE r.subject=? ORDER BY m.at",
            (person_id,))
        bundle = {
            "subject": {"id": person["id"], "display_name": person["display_name"], "kind": person["kind"],
                        "processing_mode": person["processing_mode"], "lawful_basis": person["lawful_basis"]},
            "attributes": person["attrs"],
            "personal_data_fields": fields,
            "processing_activities": runs,
            "decisions_about_you": decisions,
            "automated_processing": [{**m, "note": "model saw tokenised fields only"} for m in model_calls],
            "lifecycle": self.sor.events(person_id),
            "generated_at": self.clock.now_iso(),
        }
        self.audit.append(AuditEntry(actor=actor, action="dpdp.dsr.access", kind="governance", outcome="ok",
                                     inputs={"person": person_id}, detail={"sections": list(bundle.keys())}))
        return bundle

    def correct(self, person_id: str, changes: dict[str, Any], actor: str, reason: str) -> dict[str, Any]:
        self.sor.update_attrs(person_id, changes, actor, reason)
        seq = self.audit.append(AuditEntry(actor=actor, action="dpdp.dsr.correct", kind="governance", outcome="ok",
                                           inputs={"person": person_id, "fields": sorted(changes)}, detail={"reason": reason}))
        return {"ok": True, "audit_seq": seq}

    def erase(self, person_id: str, field_name: str, actor: str) -> dict[str, Any]:
        row = self.store.one("SELECT * FROM pii_fields WHERE person_id=? AND field=?", (person_id, field_name))
        if row is None:
            raise KeyError(field_name)
        meta = self._dpdp().evaluate({"field": field_name}).outputs
        hold = row["statutory_hold_rule"] or meta.get("statutory_hold_rule")
        if hold:
            self.audit.append(AuditEntry(actor=actor, action="dpdp.dsr.erase", kind="governance", outcome="refused",
                                         policy_versions=[self._dpdp().ref], inputs={"person": person_id, "field": field_name},
                                         detail={"reason": f"statutory hold: {hold}"}))
            return {"ok": False, "reason": f"held under {hold}", "rule": hold}
        self.vault.erase(person_id, field_name)
        self.audit.append(AuditEntry(actor=actor, action="dpdp.dsr.erase", kind="governance", outcome="ok",
                                     inputs={"person": person_id, "field": field_name}))
        return {"ok": True}

    # ── consent and suppression (PARAKH) ──────────────────────────────────────

    @staticmethod
    def identity_hash(public_url: str) -> str:
        return "sha256:" + hashlib.sha256(public_url.strip().lower().encode()).hexdigest()[:24]

    def record_consent(self, person_id: str, purpose: str, artefact: dict[str, Any], actor: str) -> str:
        consent_id = new_id("consent")
        with self.store.tx() as conn:
            conn.execute("INSERT INTO consent_records (id, person_id, purpose, status, artefact, at) VALUES (?,?,?,?,?,?)",
                         (consent_id, person_id, purpose, "granted", dumps(artefact), self.clock.now_iso()))
        self.audit.append(AuditEntry(actor=actor, action="dpdp.consent.record", kind="governance", outcome="ok",
                                     inputs={"person": person_id, "purpose": purpose}, detail={"consent_id": consent_id}))
        return consent_id

    def consents(self, person_id: str | None = None) -> list[dict[str, Any]]:
        if person_id:
            rows = self.store.query("SELECT * FROM consent_records WHERE person_id=? ORDER BY at", (person_id,))
        else:
            rows = self.store.query("SELECT * FROM consent_records ORDER BY at DESC")
        for r in rows:
            r["artefact"] = loads(r["artefact"], {})
        return rows

    def suppress(self, public_url: str, reason: str, actor: str) -> str:
        identity = self.identity_hash(public_url)
        with self.store.tx() as conn:
            conn.execute("INSERT OR IGNORE INTO suppression_list (identity_hash, reason, at) VALUES (?,?,?)",
                         (identity, reason, self.clock.now_iso()))
        self.audit.append(AuditEntry(actor=actor, action="dpdp.suppress", kind="governance", outcome="ok",
                                     inputs={"identity_hash": identity}, detail={"reason": reason}))
        return identity

    def is_suppressed(self, public_url: str) -> bool:
        return self.store.one("SELECT 1 AS x FROM suppression_list WHERE identity_hash=?", (self.identity_hash(public_url),)) is not None

    def delete_person(self, person_id: str, actor: str, reason: str) -> None:
        """Hard-delete a pointer (objection ⇒ suppression + delete, in one transaction)."""
        with self.store.tx() as conn:
            tokens = [f["token"] for f in conn.execute("SELECT token FROM pii_fields WHERE person_id=?", (person_id,)).fetchall()]
            conn.execute("DELETE FROM pii_fields WHERE person_id=?", (person_id,))
            for token in tokens:
                if not conn.execute("SELECT 1 FROM pii_fields WHERE token=?", (token,)).fetchone():
                    conn.execute("DELETE FROM vault WHERE token=?", (token,))
            conn.execute("DELETE FROM lifecycle_events WHERE person_id=?", (person_id,))
            conn.execute("DELETE FROM people WHERE id=?", (person_id,))
        self.audit.append(AuditEntry(actor=actor, action="dpdp.pointer.delete", kind="governance", outcome="ok",
                                     inputs={"person": person_id}, detail={"reason": reason}))
