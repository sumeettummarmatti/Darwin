"""Policy decision point.

Two jobs:

* ``evaluate`` — run a policy pack against facts, with an audit entry naming
  the pack version and the rule IDs that fired.
* ``authorize`` — decide whether a principal may perform an action:

    effective = principal_permissions ∩ agent_capabilities ∩ workflow_step_scope

  plus the reserved-decision check and DPDP purpose limitation. Three
  intersections, never a union. The step-scope intersection is structural:
  the executor only ever submits the action the workflow step names, and a
  skill's ``propose()`` is limited to the step's ``may_propose`` list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from core.audit import AuditChain, AuditEntry
from core.connectors_sdk import ConnectorManifest
from core.pii import Vault
from core.registry import Registry
from core.rules.packs import Decision
from core.types import Principal


@dataclass
class AuthzResult:
    allowed: bool
    status: int
    reason: str
    rule_ids: list[str] = field(default_factory=list)
    policy_versions: list[str] = field(default_factory=list)
    outcome: str = "permit"          # permit | refuse | route_only


class PolicyDecisionPoint:
    def __init__(self, registry: Callable[[], Registry], vault: Vault, audit: AuditChain, today: Callable[[], str]):
        self._registry = registry
        self.vault = vault
        self.audit = audit
        self.today = today

    @property
    def registry(self) -> Registry:
        return self._registry()

    def evaluate(self, pack_name: str, facts: dict[str, Any], *, actor: str, run_id: str | None = None,
                 step_id: str | None = None, as_of: str | None = None, audit: bool = True) -> Decision:
        pack = self.registry.pack(pack_name, as_of or self.today())
        decision = pack.evaluate(facts)
        if audit:
            self.audit.append(AuditEntry(
                actor=actor, action=f"policy.evaluate.{pack_name}", kind="policy",
                outcome="ok" if decision.ok else "violation", run_id=run_id, step_id=step_id,
                inputs=_safe_facts(facts), policy_versions=[pack.ref], rule_ids=decision.rule_ids,
                detail={"outputs": decision.outputs, "error": decision.error, "pack_hash": pack.content_hash},
            ))
        return decision

    def authorize(self, principal: Principal, action: str, *, manifest: ConnectorManifest | None,
                  connector_action: str | None, subject: dict[str, Any] | None, args: dict[str, Any]) -> AuthzResult:
        reg = self.registry
        reserved = reg.reserved
        assert reserved is not None
        rule_ids: list[str] = []
        versions = [reserved.ref]

        # 1. Reserved decisions and may_never verbs — checked first, for every principal.
        cls = reserved.classify(action, principal.kind, principal.roles)
        if cls.outcome == "route_only":
            return AuthzResult(False, 403, cls.reason, [], versions, "route_only")
        if cls.outcome == "refuse":
            return AuthzResult(False, 403, f"RESERVED — {cls.reason}", [], versions, "refuse")

        # 2. Principal permissions (RBAC pack) — for an agent, those of the human it acts for.
        human = principal.on_behalf_of if principal.kind == "agent" else principal
        if human is None:
            return AuthzResult(False, 403, "agent has no principal to act on behalf of", [], versions, "refuse")
        domain = (manifest.domain if manifest else None) or action.split(".")[0]
        rbac = reg.pack("rbac", self.today())
        versions.append(rbac.ref)
        allowed_by_role = False
        for role in human.roles:
            d = rbac.evaluate({"role": role, "domain": domain})
            rule_ids += d.rule_ids
            if d.ok and d.outputs.get("allowed"):
                allowed_by_role = True
                break
        if not allowed_by_role:
            return AuthzResult(False, 403, f"{human.label} (roles {human.roles}) may not act in domain '{domain}'",
                               rule_ids, versions, "refuse")

        # Org-unit scope: a principal acts only on people inside their org units.
        if subject and subject.get("org_unit") and "*" not in human.org_units:
            if subject["org_unit"] not in human.org_units:
                return AuthzResult(False, 403, f"{subject.get('id')} is in {subject['org_unit']}, outside {human.label}'s "
                                               f"org units {human.org_units}", rule_ids, versions, "refuse")

        # 3. Agent capability allow-list.
        if principal.kind == "agent" and manifest and connector_action:
            spec = manifest.actions.get(connector_action)
            capability = spec.capability if spec else "provision"
            if capability not in reserved.may:
                return AuthzResult(False, 403, f"capability '{capability}' is not in the agent allow-list", rule_ids, versions, "refuse")

        # 4. DPDP purpose limitation on any PII token in the payload.
        if subject and manifest:
            purpose = manifest.purpose
            for key in args:
                if not key.endswith("_token"):
                    continue
                field_name = key[: -len("_token")]
                tags = next((f["purposes"] for f in self.vault.fields_for(subject["id"]) if f["field"] == field_name), None)
                if tags is not None and purpose and purpose not in tags:
                    return AuthzResult(False, 403, f"DPDP purpose limitation: '{field_name}' is tagged {tags}; "
                                                   f"{manifest.name} declares purpose '{purpose}'", rule_ids,
                                       versions + [reg.pack('dpdp', self.today()).ref], "refuse")
        return AuthzResult(True, 200, "permitted", rule_ids, versions, "permit")


def _safe_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """Facts written to the audit log: drop anything that looks like raw PII."""
    return {k: v for k, v in facts.items() if not str(k).endswith(("_raw", "pan", "bank_account", "aadhaar"))}
