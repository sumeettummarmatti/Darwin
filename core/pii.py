"""PII tokenisation proxy and vault.

Every model call passes through ``PiiProxy.minimise`` first. It:

1. **Refuses outright** if the subject is ``pointer_only`` or ``suppressed`` —
   a person with no lawful basis is never sent to a model, not even to check
   relevance (CLAUDE.md invariant 8).
2. **Strips every field the skill did not declare** in its manifest ``inputs``.
3. **Strips prohibited criteria** (age, gender, caste, college tier, …) even if
   a manifest declares them.
4. **Tokenises** by field class from the DPDP pack: names → ``«PERSON_1»``,
   PAN / bank / Aadhaar → ``«VAULT_n»`` placeholders. Raw secrets never leave.
5. Scrubs identifiers out of free text with pattern rules.

The result records what was stripped and why, which is exactly what the
payload viewer shows next to the source record.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from core.db import Store, dumps, loads
from core.rules.packs import PolicyPack


class PointerOnlyViolation(Exception):
    """A model call, score, rank or enrichment was attempted on a pointer_only subject."""


class UndeclaredInput(Exception):
    """A skill tried to read a field it did not declare in its manifest."""


class PurposeViolation(Exception):
    """A read whose declared purpose is not on the field's purpose tags."""


# Patterns for identifiers that can hide in free text. Synthetic-format aware.
_TEXT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PAN", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("AADHAAR", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)")),
    ("BANK", re.compile(r"\bSYN-\d{6,}\b")),
]


@dataclass
class MinimisedPayload:
    payload: dict[str, Any]
    stripped: list[dict[str, str]] = field(default_factory=list)
    tokens: dict[str, str] = field(default_factory=dict)      # «PERSON_1» -> raw (never leaves the kernel)

    def rehydrate(self, text: Any) -> Any:
        """Swap pseudonyms back for display to an authorised human. Never sent anywhere."""
        if isinstance(text, str):
            for token, raw in self.tokens.items():
                if token.startswith("«PERSON") or token.startswith("«EMAIL"):
                    text = text.replace(token, raw)
            return text
        if isinstance(text, dict):
            return {k: self.rehydrate(v) for k, v in text.items()}
        if isinstance(text, list):
            return [self.rehydrate(v) for v in text]
        return text


class Vault:
    """Holds raw PII. Tokens are opaque; reads are purpose-checked.

    Tokenisation is **deterministic** (keyed HMAC of field + value): the same
    PAN always yields the same token. That lets the kernel notice that a new
    hire and a two-year-old contractor record are one person — without any
    component outside the vault ever seeing the PAN.
    """

    def __init__(self, store: Store):
        self.store = store
        self._key = os.environ.get("SETU_VAULT_KEY", "setu-demo-vault-key-not-for-production").encode()

    def token_of(self, field_name: str, value: str) -> str:
        digest = hmac.new(self._key, f"{field_name}:{value}".encode(), hashlib.sha256).hexdigest()
        return f"tok_{digest[:12]}"

    def put(self, person_id: str, field_name: str, value: str, purposes: list[str],
            retention_until: str | None = None, statutory_hold_rule: str | None = None) -> str:
        token = self.token_of(field_name, value)
        with self.store.tx() as conn:
            conn.execute("INSERT OR REPLACE INTO vault(token, value) VALUES (?, ?)", (token, value))
            conn.execute(
                "INSERT INTO pii_fields(person_id, field, token, purposes, retention_until, statutory_hold_rule) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(person_id, field) DO UPDATE SET token=excluded.token, "
                "purposes=excluded.purposes, deleted_at=NULL",
                (person_id, field_name, token, dumps(purposes), retention_until, statutory_hold_rule),
            )
        return token

    def token_for(self, person_id: str, field_name: str) -> str | None:
        row = self.store.one("SELECT token FROM pii_fields WHERE person_id=? AND field=? AND deleted_at IS NULL", (person_id, field_name))
        return row["token"] if row else None

    def fields_for(self, person_id: str) -> list[dict[str, Any]]:
        rows = self.store.query("SELECT * FROM pii_fields WHERE person_id=? ORDER BY field", (person_id,))
        for r in rows:
            r["purposes"] = loads(r["purposes"], [])
        return rows

    def read(self, person_id: str, field_name: str, purpose: str) -> str:
        row = self.store.one("SELECT * FROM pii_fields WHERE person_id=? AND field=?", (person_id, field_name))
        if row is None or row["deleted_at"]:
            raise PurposeViolation(f"{field_name} for {person_id} does not exist or was deleted")
        purposes = loads(row["purposes"], [])
        if purpose not in purposes:
            raise PurposeViolation(f"purpose '{purpose}' is not on {field_name}'s tags {purposes}")
        value = self.store.one("SELECT value FROM vault WHERE token=?", (row["token"],))
        return value["value"] if value else ""

    def raw_values_for(self, person_id: str) -> set[str]:
        """Used only by Prativaad's pii_overreach check, inside the kernel."""
        rows = self.store.query(
            "SELECT v.value FROM pii_fields f JOIN vault v ON v.token=f.token WHERE f.person_id=? AND f.deleted_at IS NULL",
            (person_id,),
        )
        return {r["value"] for r in rows if r["value"]}

    def erase(self, person_id: str, field_name: str) -> None:
        with self.store.tx() as conn:
            row = conn.execute("SELECT token FROM pii_fields WHERE person_id=? AND field=?", (person_id, field_name)).fetchone()
            if row:
                conn.execute("UPDATE pii_fields SET deleted_at=datetime('now') WHERE person_id=? AND field=?", (person_id, field_name))
                still_used = conn.execute("SELECT 1 FROM pii_fields WHERE token=? AND deleted_at IS NULL", (row["token"],)).fetchone()
                if not still_used:
                    conn.execute("DELETE FROM vault WHERE token=?", (row["token"],))


class PiiProxy:
    def __init__(self, dpdp_pack: Callable[[], PolicyPack], prohibited: Callable[[], list[str]]):
        self._dpdp = dpdp_pack
        self._prohibited = prohibited

    def classify(self, field_name: str) -> dict[str, Any]:
        leaf = field_name.rsplit(".", 1)[-1]
        decision = self._dpdp().evaluate({"field": leaf})
        if not decision.ok:
            return {"class": "attribute", "purposes": []}
        return decision.outputs

    def minimise(self, source: dict[str, Any], declared: list[str], subject: dict[str, Any] | None = None,
                 extra_names: list[str] | None = None) -> MinimisedPayload:
        if subject and subject.get("processing_mode") in ("pointer_only", "suppressed"):
            raise PointerOnlyViolation(
                f"{subject.get('id')} is {subject.get('processing_mode')}: no lawful basis to send anything about this person to a model"
            )
        prohibited = set(self._prohibited())
        result = MinimisedPayload(payload={})
        counters: dict[str, int] = {}
        known_names: dict[str, str] = {}

        def token(kind: str, raw: str) -> str:
            for existing, value in result.tokens.items():
                if value == raw and existing.startswith(f"«{kind}"):
                    return existing
            counters[kind] = counters.get(kind, 0) + 1
            tok = f"«{kind}_{counters[kind]}»"
            result.tokens[tok] = raw
            return tok

        declared_set = set(declared)
        for key, value in source.items():
            leaf = key.rsplit(".", 1)[-1]
            if key not in declared_set:
                result.stripped.append({"field": key, "reason": "undeclared in skill manifest"})
                continue
            if leaf in prohibited:
                result.stripped.append({"field": key, "reason": "prohibited criterion"})
                continue
            klass = self.classify(key).get("class", "attribute")
            if value is None:
                result.payload[key] = None
            elif klass == "identifier":
                tok = token("PERSON", str(value))
                known_names[str(value)] = tok
                result.payload[key] = tok
            elif klass == "contact":
                result.payload[key] = token("EMAIL", str(value))
            elif klass == "secret":
                result.payload[key] = token("VAULT", str(value))
                result.stripped.append({"field": key, "reason": "secret — replaced by vault placeholder, raw never sent"})
            else:
                result.payload[key] = value

        # Names the caller knows will appear in free text (e.g. candidates in résumés).
        for name in extra_names or []:
            if name and name not in known_names:
                known_names[name] = token("PERSON", name)

        # Second pass: scrub free text — including nested lists and objects — of
        # identifiers and known names.
        def scrub(value: Any) -> Any:
            if isinstance(value, str):
                return value if value.startswith("«") else self.scrub_text(value, known_names, token)
            if isinstance(value, dict):
                return {k: (None if k in prohibited else scrub(v)) for k, v in value.items() if k not in prohibited}
            if isinstance(value, list):
                return [scrub(v) for v in value]
            return value

        for key, value in list(result.payload.items()):
            result.payload[key] = scrub(value)
        return result

    def scrub_text(self, text: str, known_names: dict[str, str], token: Callable[[str, str], str]) -> str:
        # Structured identifiers first (an email containing a name must go whole), then names.
        for kind, pattern in _TEXT_PATTERNS:
            text = pattern.sub(lambda m, k=kind: token(k, m.group(0)), text)
        for name, tok in sorted(known_names.items(), key=lambda kv: -len(kv[0])):
            text = re.sub(re.escape(name), tok, text, flags=re.IGNORECASE)
            for part in name.split(" "):
                if len(part) > 2:
                    text = re.sub(rf"\b{re.escape(part)}\b", tok, text, flags=re.IGNORECASE)
        return text
