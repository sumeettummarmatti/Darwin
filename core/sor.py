"""System of record: people, employment spells, PII rows, lifecycle events.

PII is stored as rows (``pii_fields``) with purpose tags and retention clocks;
raw values live only in the vault. Templates and skills see *tokens*
(``subject.pan_token``), never raw identifiers.
"""

from __future__ import annotations

from typing import Any, Callable

from core.audit import AuditChain
from core.clock import Clock
from core.db import Store, dumps, loads
from core.pii import Vault
from core.rules.packs import PolicyPack


class SystemOfRecord:
    def __init__(self, store: Store, clock: Clock, audit: AuditChain, vault: Vault, dpdp: Callable[[], PolicyPack]):
        self.store = store
        self.clock = clock
        self.audit = audit
        self.vault = vault
        self._dpdp = dpdp

    # ── people ────────────────────────────────────────────────────────────────

    def create_person(self, person_id: str, kind: str, display_name: str, attrs: dict[str, Any], *,
                      pii: dict[str, str] | None = None, processing_mode: str = "full", lawful_basis: str | None = None,
                      actor: str = "system:seed") -> None:
        with self.store.tx() as conn:
            conn.execute(
                "INSERT INTO people (id, kind, display_name, attrs, processing_mode, lawful_basis, created_at) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, display_name=excluded.display_name, attrs=excluded.attrs, "
                "processing_mode=excluded.processing_mode, lawful_basis=excluded.lawful_basis",
                (person_id, kind, display_name, dumps(attrs), processing_mode, lawful_basis, self.clock.now_iso()),
            )
        for field_name, value in (pii or {}).items():
            meta = self._dpdp().evaluate({"field": field_name}).outputs
            self.vault.put(person_id, field_name, value, list(meta.get("purposes") or []))
        self.event(person_id, f"{kind}.created", {"processing_mode": processing_mode, "lawful_basis": lawful_basis}, actor)

    def add_spell(self, spell_id: str, person_id: str, start: str, employment_type: str, grade: str, end: str | None = None) -> None:
        with self.store.tx() as conn:
            conn.execute("INSERT OR REPLACE INTO employment_spells (id, person_id, start_date, end_date, employment_type, grade) "
                         "VALUES (?,?,?,?,?,?)", (spell_id, person_id, start, end, employment_type, grade))

    def person(self, person_id: str) -> dict[str, Any] | None:
        row = self.store.one("SELECT * FROM people WHERE id=?", (person_id,))
        if not row:
            return None
        row["attrs"] = loads(row["attrs"], {})
        return row

    def people(self, kind: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        if kind:
            rows = self.store.query("SELECT * FROM people WHERE kind=? ORDER BY id LIMIT ?", (kind, limit))
        else:
            rows = self.store.query("SELECT * FROM people ORDER BY id LIMIT ?", (limit,))
        for r in rows:
            r["attrs"] = loads(r["attrs"], {})
        return rows

    def update_attrs(self, person_id: str, changes: dict[str, Any], actor: str, reason: str) -> None:
        person = self.person(person_id)
        if person is None:
            raise KeyError(person_id)
        attrs = {**person["attrs"], **changes}
        with self.store.tx() as conn:
            conn.execute("UPDATE people SET attrs=? WHERE id=?", (dumps(attrs), person_id))
        self.event(person_id, "record.corrected", {"changes": changes, "reason": reason}, actor)

    def set_mode(self, person_id: str, mode: str, basis: str | None, actor: str, reason: str) -> None:
        with self.store.tx() as conn:
            conn.execute("UPDATE people SET processing_mode=?, lawful_basis=COALESCE(?, lawful_basis) WHERE id=?", (mode, basis, person_id))
        self.event(person_id, "processing_mode.changed", {"mode": mode, "basis": basis, "reason": reason}, actor)

    def spells(self, person_id: str) -> list[dict[str, Any]]:
        return self.store.query("SELECT * FROM employment_spells WHERE person_id=? ORDER BY start_date", (person_id,))

    def event(self, person_id: str, event: str, payload: dict[str, Any], actor: str) -> None:
        with self.store.tx() as conn:
            conn.execute("INSERT INTO lifecycle_events (person_id, event, payload, actor, at) VALUES (?,?,?,?,?)",
                         (person_id, event, dumps(payload), actor, self.clock.now_iso()))

    def events(self, person_id: str) -> list[dict[str, Any]]:
        rows = self.store.query("SELECT * FROM lifecycle_events WHERE person_id=? ORDER BY seq", (person_id,))
        for r in rows:
            r["payload"] = loads(r["payload"], {})
        return rows

    # ── views for templates and skills ────────────────────────────────────────

    def subject_view(self, person_id: str) -> dict[str, Any]:
        person = self.person(person_id)
        if person is None:
            return {"id": person_id, "missing": True}
        view = {"id": person["id"], "kind": person["kind"], "display_name": person["display_name"],
                "processing_mode": person["processing_mode"], "lawful_basis": person["lawful_basis"], **person["attrs"]}
        for f in self.vault.fields_for(person_id):
            if not f["deleted_at"]:
                view[f"{f['field']}_token"] = f["token"]
        return view

    def source_record(self, scope: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
        """Flat, dotted view of everything a skill *could* declare. The proxy and
        ``SkillContext.input`` then expose only what the manifest declares."""
        flat: dict[str, Any] = {}
        for key, value in (scope.get("subject") or {}).items():
            flat[f"subject.{key}"] = value
        for step_id, outputs in (scope.get("steps") or {}).items():
            for key, value in (outputs or {}).items():
                flat[f"steps.{step_id}.{key}"] = value
        for key, value in (scope.get("facts") or {}).items():
            flat[f"facts.{key}"] = value
        for key, value in (scope.get("inputs") or {}).items():
            flat[f"inputs.{key}"] = value
        for key, value in (args or {}).items():
            flat[f"args.{key}"] = value
        flat["today"] = scope.get("today")
        return flat

    def masked(self, source: dict[str, Any], declared: list[str]) -> dict[str, Any]:
        """What the payload viewer shows as 'the source record': declared fields in
        full (the kernel holds them), plus the names of everything withheld."""
        shown = {k: v for k, v in source.items() if k in declared}
        shown["…withheld"] = sorted(k for k in source if k not in declared)[:40]
        return shown
