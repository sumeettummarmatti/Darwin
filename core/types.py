"""Small shared types for the kernel."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Principal:
    """Who is acting. Agents always act on behalf of a human principal."""

    id: str
    kind: str                                   # human | agent
    name: str = ""
    roles: list[str] = field(default_factory=list)
    org_units: list[str] = field(default_factory=list)
    on_behalf_of: "Principal | None" = None

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.id}" if not self.id.startswith(f"{self.kind}:") else self.id

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "name": self.name, "roles": self.roles, "org_units": self.org_units,
                "on_behalf_of": self.on_behalf_of.as_dict() if self.on_behalf_of else None}


@dataclass
class ProposedAction:
    """What an agent (or a workflow step) wants to happen in the outside world."""

    action: str                                 # "<connector>.<action>", e.g. "it.assets.allocate"
    args: dict[str, Any]
    idem_key: str | None = None
    connector: str | None = None
    connector_action: str | None = None
    run_id: str | None = None
    step_id: str | None = None
    subject_id: str | None = None
    workflow: str | None = None
    skill: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    outcome: str        # executed | deduplicated | refused | retrying | waiting | paused | failed
    status: int = 200
    reason: str = ""
    result: dict[str, Any] | None = None
    rule_ids: list[str] = field(default_factory=list)
    policy_versions: list[str] = field(default_factory=list)
    audit_seq: int | None = None

    @property
    def done(self) -> bool:
        return self.outcome in ("executed", "deduplicated")
