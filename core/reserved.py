"""The reserved-decision registry — configuration HR can change, enforced by the kernel.

Three outcomes for any proposed action:

* ``permit``      — not reserved; continue down the governed flow.
* ``refuse``      — an agent attempted a reserved action or a ``may_never`` verb
                    (403 RESERVED), or a human lacks an approver role.
* ``route_only``  — POSH / grievance / whistleblower. The agent may not even
                    summarise; the matter goes to the named human, untouched.

A workflow step marked ``reserved: true`` never reaches this check as an agent
action: the orchestrator turns it into a human task. This module is what makes
the *other* path — an agent emitting the verb anyway — fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class RegistryLoadError(Exception):
    pass


@dataclass
class ReservedEntry:
    action: str
    approver_role: list[str]
    mode: str = "any_of"          # any_of | sequential (every role, in order)
    note: str = ""


@dataclass
class Classification:
    outcome: str                  # permit | refuse | route_only
    reason: str
    entry: ReservedEntry | None = None
    verb: str | None = None


@dataclass
class ReservedRegistry:
    version: int
    entries: dict[str, ReservedEntry]
    route_only: dict[str, str]                 # action -> role the matter is handed to
    may: list[str]
    may_never: list[str]
    source_path: str = "<memory>"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"reserved_decisions@v{self.version}"

    def verb_of(self, action: str) -> str | None:
        """Return the reserved verb an action name carries, if any.

        ``exit.accept_resignation`` → ``accept``; ``payroll.sign_off`` → ``sign_off``;
        ``hire.reject_candidate`` → ``reject_candidate``.
        """
        segment = action.rsplit(".", 1)[-1]
        for verb in sorted(self.may_never, key=len, reverse=True):
            if segment == verb or segment.startswith(verb + "_"):
                return verb
        return None

    def classify(self, action: str, principal_kind: str, principal_roles: list[str] | None = None) -> Classification:
        if action in self.route_only:
            return Classification("route_only", f"{action} is route-only: hand to {self.route_only[action]}, decide nothing")
        entry = self.entries.get(action)
        verb = self.verb_of(action)
        if principal_kind == "agent":
            if entry is not None:
                return Classification("refuse", f"{action} is a reserved decision; agents cannot complete it", entry, verb)
            if verb is not None:
                return Classification("refuse", f"verb '{verb}' is in may_never; no configuration grants it to an agent", None, verb)
            return Classification("permit", "not reserved", None, None)
        # Human principal: reserved actions require an approver role.
        if entry is not None:
            roles = set(principal_roles or [])
            if roles & set(entry.approver_role):
                return Classification("permit", "human approver holds a required role", entry, verb)
            return Classification("refuse", f"approver must hold one of {entry.approver_role}", entry, verb)
        return Classification("permit", "not reserved", None, verb)

    def run_tests(self) -> list[dict[str, Any]]:
        results = []
        for index, case in enumerate(self.raw.get("tests") or []):
            got = self.classify(case["action"], case.get("principal", "agent"), case.get("roles")).outcome
            want = case["expect"]
            results.append({
                "name": case.get("name") or f"{case['action']} as {case.get('principal', 'agent')}",
                "passed": got == want,
                "reason": "" if got == want else f"expected {want}, got {got}",
            })
        return results


def parse_registry(raw: dict[str, Any], source_path: str = "<memory>") -> ReservedRegistry:
    if raw.get("registry") != "reserved_decisions":
        raise RegistryLoadError(f"{source_path}: not a reserved_decisions registry")
    caps = raw.get("agent_capabilities") or {}
    entries = {}
    for item in raw.get("reserved") or []:
        roles = item.get("approver_role") or []
        if not roles:
            raise RegistryLoadError(f"{source_path}: {item.get('action')} names no approver role")
        entries[item["action"]] = ReservedEntry(item["action"], list(roles), item.get("mode", "any_of"), item.get("note", ""))
    route_only = {}
    for item in raw.get("route_only_never_decide") or []:
        route_only[item["action"]] = item.get("route_to_role", "hr_head")
    registry = ReservedRegistry(
        version=int(raw.get("version", 1)),
        entries=entries,
        route_only=route_only,
        may=list(caps.get("may") or []),
        may_never=list(caps.get("may_never") or []),
        source_path=source_path,
        raw=raw,
    )
    if not raw.get("tests"):
        raise RegistryLoadError(f"{source_path}: registry has no tests — refusing to load")
    failures = [r for r in registry.run_tests() if not r["passed"]]
    if failures:
        raise RegistryLoadError(f"{source_path}: registry tests failing — " + "; ".join(f"{f['name']}: {f['reason']}" for f in failures))
    return registry


def load_registry_file(path: Path) -> ReservedRegistry:
    return parse_registry(yaml.safe_load(path.read_text()), str(path))
