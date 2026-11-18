"""Policy packs: versioned, effective-dated, tested rule sets.

One format for every rule in the platform — notice periods, gratuity, leave,
entitlements, DPDP field purposes, the lawful-basis gate, the no-raid guard,
ICP scoring. A pack is evaluated in three phases:

1. ``rules``  — first match wins; its ``then`` block becomes outputs.
2. ``derive`` — named values computed in order, each with its own rule ID.
3. ``guards`` — assertions; a failing guard is a hard error (fail closed).

A pack **refuses to load** if it has no ``tests:``, if any test fails, or if an
expression references a field listed in ``prohibited_criteria``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from core.rules.expr import Expression, ExpressionError


class PackLoadError(Exception):
    """A pack is malformed, untested, failing its tests, or references a prohibited field."""


class PolicyViolation(Exception):
    """A guard failed while evaluating a pack. Carries the rule ID for the audit entry."""

    def __init__(self, pack_ref: str, rule_id: str, message: str):
        super().__init__(f"{pack_ref} {rule_id}: {message}")
        self.pack_ref = pack_ref
        self.rule_id = rule_id
        self.message = message


@dataclass
class Decision:
    """The result of evaluating a pack against a set of facts."""

    pack_ref: str                      # e.g. "notice_period.in@v4"
    outputs: dict[str, Any]
    rule_ids: list[str]
    error: str | None = None
    error_rule: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "pack": self.pack_ref,
            "outputs": self.outputs,
            "rule_ids": self.rule_ids,
            "ok": self.ok,
            "error": self.error,
            "error_rule": self.error_rule,
        }


@dataclass
class _Rule:
    id: str
    when: Expression | None
    then: dict[str, Expression]


@dataclass
class _Derive:
    id: str
    name: str
    expr: Expression
    when: Expression | None = None


@dataclass
class _Guard:
    id: str
    check: Expression
    error: str
    when: Expression | None = None


@dataclass
class PolicyPack:
    name: str
    version: int
    jurisdiction: str | None
    effective_from: date
    raw: dict[str, Any]
    source_path: str
    rules: list[_Rule] = field(default_factory=list)
    derive: list[_Derive] = field(default_factory=list)
    guards: list[_Guard] = field(default_factory=list)
    tables: dict[str, Any] = field(default_factory=dict)
    defaults: dict[str, Any] = field(default_factory=dict)

    @property
    def ref(self) -> str:
        suffix = f".{self.jurisdiction.lower()}" if self.jurisdiction else ""
        return f"{self.name}{suffix}@v{self.version}"

    @property
    def content_hash(self) -> str:
        canonical = json.dumps(self.raw, sort_keys=True, default=str).encode()
        return "sha256:" + hashlib.sha256(canonical).hexdigest()[:16]

    @property
    def prohibited(self) -> list[str]:
        return list(self.raw.get("prohibited_criteria") or [])

    @property
    def clauses(self) -> list[dict[str, Any]]:
        return list(self.raw.get("clauses") or [])

    # ── evaluation ────────────────────────────────────────────────────────────

    def _functions(self) -> dict[str, Any]:
        def lookup(table: str, key: Any, default: Any = "__missing__") -> Any:
            data = self.tables.get(table)
            if data is None:
                raise ExpressionError(f"unknown table '{table}' in {self.ref}")
            if key in data:
                return data[key]
            if "default" in data:
                return data["default"]
            if default != "__missing__":
                return default
            raise ExpressionError(f"'{key}' not in table '{table}' and no default")

        def in_table(table: str, key: Any) -> bool:
            return key in (self.tables.get(table) or {})

        return {"lookup": lookup, "in_table": in_table}

    def evaluate(self, given: dict[str, Any]) -> Decision:
        facts: dict[str, Any] = {**self.defaults, **given}
        outputs: dict[str, Any] = {}
        fired: list[str] = []
        funcs = self._functions()
        try:
            if self.rules:
                for rule in self.rules:
                    if rule.when is None or rule.when.evaluate(facts, funcs):
                        for key, expr in rule.then.items():
                            outputs[key] = expr.evaluate({**facts, **outputs}, funcs)
                        fired.append(rule.id)
                        break
                else:
                    return Decision(self.ref, outputs, fired, "no rule matched these facts", None)
            for step in self.derive:
                scope = {**facts, **outputs}
                if step.when is not None and not step.when.evaluate(scope, funcs):
                    continue
                outputs[step.name] = step.expr.evaluate(scope, funcs)
                fired.append(step.id)
            for guard in self.guards:
                scope = {**facts, **outputs}
                if guard.when is not None and not guard.when.evaluate(scope, funcs):
                    continue
                if not guard.check.evaluate(scope, funcs):
                    return Decision(self.ref, outputs, fired + [guard.id], guard.error, guard.id)
                fired.append(guard.id)
        except ExpressionError as exc:
            return Decision(self.ref, outputs, fired, f"evaluation error: {exc}", None)
        return Decision(self.ref, outputs, fired)

    def resolve(self, given: dict[str, Any]) -> Decision:
        """Like ``evaluate`` but raises on a guard failure — for callers that must act."""
        decision = self.evaluate(given)
        if not decision.ok:
            raise PolicyViolation(self.ref, decision.error_rule or "-", decision.error or "")
        return decision

    # ── tests shipped inside the pack ─────────────────────────────────────────

    def run_tests(self) -> list[dict[str, Any]]:
        results = []
        for index, case in enumerate(self.raw.get("tests") or []):
            name = case.get("name") or f"case {index + 1}"
            decision = self.evaluate(case.get("given") or {})
            passed, reason = True, ""
            if "expect_error" in case:
                expected = str(case["expect_error"]).lower()
                if decision.ok or expected not in (decision.error or "").lower():
                    passed, reason = False, f"expected error '{case['expect_error']}', got {decision.error or decision.outputs}"
            else:
                if not decision.ok:
                    passed, reason = False, f"unexpected error: {decision.error}"
                else:
                    for key, want in (case.get("expect") or {}).items():
                        got = decision.outputs.get(key)
                        if isinstance(want, float) and isinstance(got, (int, float)):
                            ok = abs(got - want) < 0.01
                        else:
                            ok = got == want
                        if not ok:
                            passed, reason = False, f"{key}: expected {want!r}, got {got!r}"
                            break
            results.append({"name": name, "passed": passed, "reason": reason, "rule_ids": decision.rule_ids})
        return results


def _expr(value: Any, where: str) -> Expression:
    try:
        return Expression(value)
    except ExpressionError as exc:
        raise PackLoadError(f"{where}: {exc}") from exc


def parse_pack(raw: dict[str, Any], source_path: str = "<memory>", *, require_tests: bool = True) -> PolicyPack:
    """Build a PolicyPack from YAML data, validating it fully. Raises PackLoadError."""
    for key in ("pack", "version", "effective_from"):
        if key not in raw:
            raise PackLoadError(f"{source_path}: missing required key '{key}'")
    effective = raw["effective_from"]
    if isinstance(effective, str):
        effective = date.fromisoformat(effective)
    pack = PolicyPack(
        name=str(raw["pack"]),
        version=int(raw["version"]),
        jurisdiction=raw.get("jurisdiction"),
        effective_from=effective,
        raw=raw,
        source_path=source_path,
        tables=dict(raw.get("tables") or {}),
        defaults=dict(raw.get("defaults") or {}),
    )
    where = f"{source_path} ({pack.name})"
    seen_ids: set[str] = set()

    def claim_id(rule_id: str) -> str:
        if not rule_id:
            raise PackLoadError(f"{where}: every rule needs an id")
        if rule_id in seen_ids:
            raise PackLoadError(f"{where}: duplicate rule id {rule_id}")
        seen_ids.add(rule_id)
        return rule_id

    for item in raw.get("rules") or []:
        pack.rules.append(_Rule(
            id=claim_id(item.get("id", "")),
            when=_expr(item["when"], where) if "when" in item else None,
            then={k: _expr(v, f"{where} {item.get('id')}") for k, v in (item.get("then") or {}).items()},
        ))
    for item in raw.get("derive") or []:
        pack.derive.append(_Derive(
            id=claim_id(item.get("id", "")),
            name=item["name"],
            expr=_expr(item["expr"], where),
            when=_expr(item["when"], where) if "when" in item else None,
        ))
    for item in raw.get("guards") or []:
        pack.guards.append(_Guard(
            id=claim_id(item.get("id", "")),
            check=_expr(item["assert"], where),
            error=item.get("error", "guard failed"),
            when=_expr(item["when"], where) if "when" in item else None,
        ))

    # Prohibited criteria: no expression may read them. Fails at load, not at run.
    prohibited = set(pack.prohibited)
    if prohibited:
        expressions: list[Expression] = []
        for r in pack.rules:
            expressions += ([r.when] if r.when else []) + list(r.then.values())
        for d in pack.derive:
            expressions += [d.expr] + ([d.when] if d.when else [])
        for g in pack.guards:
            expressions += [g.check] + ([g.when] if g.when else [])
        for e in expressions:
            leaked = e.names() & prohibited
            if leaked:
                raise PackLoadError(f"{where}: expression {e.source!r} references prohibited criteria {sorted(leaked)}")

    if require_tests:
        if not raw.get("tests"):
            raise PackLoadError(f"{where}: pack has no tests — refusing to load")
        failures = [r for r in pack.run_tests() if not r["passed"]]
        if failures:
            detail = "; ".join(f"{f['name']}: {f['reason']}" for f in failures)
            raise PackLoadError(f"{where}: {len(failures)} pack test(s) failing — {detail}")
    return pack


def load_pack_file(path: Path) -> PolicyPack:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise PackLoadError(f"{path}: not a mapping")
    return parse_pack(raw, str(path))
