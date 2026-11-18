"""PRATIVAAD — the devil's-advocate layer.

Its instruction is not "check this" but "find the reason this must not run".
A fixed taxonomy of objection classes keeps it cheap and measurable:

    duplicate_side_effect · date_ordering · reserved_leakage · entitlement_mismatch
    pii_overreach · policy_version_staleness · compensation_coverage · proxy_bias

Gates:

* **A — pre-commit** (runtime): before an irreversible connector action. The
  deterministic checks run in code first; a tier-1 model reviews only the
  judgement-shaped residue, and only while Prativaad has spent < 8% of the
  workflow budget. Over budget it degrades to rules-only and logs that.
* **B — policy change**: property-based adversarial cases over a pack's
  declared input domains; finds statutory-floor breaches before activation.
* **C — extension time**: the governance lint behind ``hrx validate``.
* **D — fair hiring**: proxy-bias challenge over ranking rationales.

Every objection is stored with its layer (``rules`` or ``model``) so the fault
corpus can measure what the model actually adds — and we report it honestly.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from core.audit import AuditChain, AuditEntry
from core.clock import Clock, new_id
from core.connectors_sdk import Connector
from core.db import Store, dumps
from core.registry import Registry
from core.rules.expr import Expression, ExpressionError
from core.rules.packs import PackLoadError, PolicyPack, parse_pack
from core.workflows import StepDef, WorkflowDef, template_expressions

BUDGET_SHARE = 0.08
BLOCKING = ("high", "medium")


@dataclass
class Objection:
    cls: str
    severity: str                       # high | medium | low
    claim: str
    evidence: list[str] = field(default_factory=list)
    suggested_action: str | None = None
    layer: str = "rules"                # rules | model

    def as_dict(self) -> dict[str, Any]:
        return {"class": self.cls, "severity": self.severity, "claim": self.claim, "evidence": self.evidence,
                "suggested_action": self.suggested_action, "layer": self.layer}


@dataclass
class GateResult:
    verdict: str                        # CLEAR | OBJECT
    objections: list[Objection]
    checked: list[str]
    model_used: bool = False
    degraded: bool = False
    cost_inr: float = 0.0

    @property
    def blocking(self) -> list[Objection]:
        return [o for o in self.objections if o.severity in BLOCKING]


class Prativaad:
    def __init__(self, store: Store, clock: Clock, audit: AuditChain, registry: Callable[[], Registry]):
        self.store = store
        self.clock = clock
        self.audit = audit
        self._registry = registry

    @property
    def registry(self) -> Registry:
        return self._registry()

    # ── Gate A ────────────────────────────────────────────────────────────────

    def gate_a(self, *, run: dict[str, Any], wf: WorkflowDef, step: StepDef, connector: Connector, args: dict[str, Any],
               idem_key: str, scope: dict[str, Any], raw_pii: set[str],
               model_review: Callable[[dict[str, Any], float], tuple[list[Objection], float]] | None = None) -> GateResult:
        objections: list[Objection] = []
        checked = ["duplicate_side_effect", "pii_overreach", "entitlement_mismatch", "reserved_leakage",
                   "compensation_coverage", "policy_version_staleness"]

        # duplicate_side_effect — could this already have happened?
        for prior in connector.prior_effects(step.action or "", args, idem_key):
            objections.append(Objection(
                "duplicate_side_effect", "high",
                f"An open {prior.get('kind', 'record')} {prior.get('id')} already exists for this holder "
                f"(reference {prior.get('reference') or 'none'}), created {str(prior.get('created_at', ''))[:10]}; "
                f"executing {connector.name}.{step.action} again risks a duplicate.",
                [f"{connector.manifest.system}:{prior.get('id')}"], "verify_prior_effect_closed"))

        # pii_overreach — raw personal data must never travel in a connector payload; tokens only.
        flat = dumps(args)
        leaked = sorted(v for v in raw_pii if len(v) >= 6 and v in flat)
        if leaked:
            objections.append(Objection("pii_overreach", "high",
                                        f"{len(leaked)} raw PII value(s) found in the outbound payload; only vault tokens may leave the kernel.",
                                        ["payload"], "replace_with_tokens"))

        # entitlement_mismatch — step-declared invariants (YAML, not Python).
        for inv in step.invariants:
            try:
                ok = Expression(inv["check"]).evaluate({**scope, "args": args})
            except ExpressionError as exc:
                ok, inv = False, {**inv, "claim": f"invariant could not be evaluated: {exc}"}
            if not ok:
                objections.append(Objection(inv.get("class", "entitlement_mismatch"), inv.get("severity", "high"),
                                            inv.get("claim", f"invariant failed: {inv['check']}"), [f"step:{step.id}"],
                                            inv.get("suggested_action", "recompute_and_review")))

        # reserved_leakage — acting on a reserved fact with no reserved step upstream.
        reserved_facts = set(self.registry.reserved.raw.get("reserved_facts") or []) if self.registry.reserved else set()
        referenced = {n.split(".")[1] for e in template_expressions(step.args) for n in Expression(e).names()
                      if n.startswith("facts.") and n.count(".") >= 1}
        touched = referenced & reserved_facts
        if touched:
            upstream_reserved = [a for a in wf.ancestors(step.id) if wf.step(a).kind == "reserved"]
            if not upstream_reserved:
                objections.append(Objection("reserved_leakage", "high",
                                            f"Step uses reserved fact(s) {sorted(touched)} but no reserved decision precedes it.",
                                            [f"step:{step.id}"], "add_reserved_gate"))

        # compensation_coverage — irreversible with no declared undo.
        spec = connector.manifest.actions.get(step.action or "")
        if spec and spec.irreversible and not step.compensation:
            objections.append(Objection("compensation_coverage", "low",
                                        f"{connector.name}.{step.action} is irreversible and declares no compensation; "
                                        "a later failure cannot undo it automatically.", [f"step:{step.id}"], "declare_compensation"))

        # policy_version_staleness — was the plan built on a superseded pack?
        for ref in run.get("policy_versions") or []:
            name, _, version = ref.partition("@v")
            base_name = name.split(".")[0]
            try:
                current = self.registry.pack(base_name, self.clock.today())
            except KeyError:
                continue
            if version.isdigit() and current.version > int(version):
                objections.append(Objection("policy_version_staleness", "medium",
                                            f"Run computed with {ref} but {current.ref} is now in force.",
                                            [ref, current.ref], "recompute_under_current_pack"))

        # Model residue — judgement-shaped questions only, inside the 8% budget.
        model_used, degraded, cost = False, False, 0.0
        budget = (run.get("budget_inr") or 0) * BUDGET_SHARE
        spent = self.spent_inr(run["id"])
        if model_review is not None:
            if budget and spent < budget:
                extra, cost = model_review({
                    "workflow": wf.ref, "step": step.id, "action": f"{connector.name}.{step.action}",
                    "arg_keys": sorted(args.keys()), "rules_objections": [o.cls for o in objections],
                    "classes_to_consider": checked,
                }, budget - spent)
                objections += extra
                model_used = True
            else:
                degraded = True
        verdict = "OBJECT" if objections else "CLEAR"
        result = GateResult(verdict, objections, checked + (["model_residue"] if model_used else []), model_used, degraded, cost)
        self._log(run["id"], step.id, "A", result)
        return result

    def check_schedule(self, *, run_id: str, step_id: str, scheduled_for: str, should_be: str) -> Objection | None:
        """date_ordering — the governing date moved after this step was scheduled."""
        if scheduled_for[:16] == should_be[:16]:
            return None
        objection = Objection("date_ordering", "high",
                              f"Step is scheduled for {scheduled_for[:16]} but its governing date now resolves to "
                              f"{should_be[:16]}; executing as scheduled would act on a superseded date.",
                              [f"step:{step_id}", "facts.last_working_day"], "reschedule_to_governing_date")
        self._log(run_id, step_id, "A", GateResult("OBJECT", [objection], ["date_ordering"]))
        return objection

    def spent_inr(self, run_id: str) -> float:
        row = self.store.one("SELECT COALESCE(SUM(inr),0) AS s FROM audit WHERE run_id=? AND action LIKE 'model.prativaad%'", (run_id,))
        return float(row["s"]) if row else 0.0

    def resolve(self, objection_id: str, resolution: str, upheld: bool | None) -> None:
        with self.store.tx() as conn:
            conn.execute("UPDATE objections SET resolution=?, upheld=? WHERE id=?", (resolution, None if upheld is None else int(upheld), objection_id))

    def _log(self, run_id: str | None, step_id: str | None, gate: str, result: GateResult) -> list[str]:
        ids = []
        with self.store.tx() as conn:
            for o in result.objections:
                oid = new_id("obj")
                ids.append(oid)
                conn.execute(
                    "INSERT INTO objections (id, run_id, step_id, gate, class, severity, claim, evidence, suggested_action, layer, at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (oid, run_id, step_id, gate, o.cls, o.severity, o.claim, dumps(o.evidence), o.suggested_action, o.layer,
                     self.clock.now_iso()),
                )
        self.audit.append(AuditEntry(
            actor="prativaad", action=f"prativaad.gate_{gate.lower()}", kind="prativaad",
            outcome="objected" if result.objections else "cleared", run_id=run_id, step_id=step_id,
            inputs={"checked": result.checked}, inr=0.0,
            detail={"objections": [o.as_dict() for o in result.objections], "objection_ids": ids,
                    "model_used": result.model_used, "degraded_to_rules_only": result.degraded},
        ))
        result.objection_ids = ids  # type: ignore[attr-defined]
        return ids

    def latest_objection_ids(self, run_id: str, step_id: str) -> list[str]:
        rows = self.store.query("SELECT id FROM objections WHERE run_id=? AND step_id=? AND resolution IS NULL", (run_id, step_id))
        return [r["id"] for r in rows]

    # ── Gate B — policy change review ─────────────────────────────────────────

    def gate_b(self, new_raw: dict[str, Any], old: PolicyPack | None = None, max_cases: int = 600) -> dict[str, Any]:
        """Generate adversarial cases from the pack's ``adversarial`` domains and
        check its ``properties`` hold for every one. Returns findings plus
        proposed test cases to append to ``tests:``."""
        findings: list[dict[str, Any]] = []
        try:
            pack = parse_pack(new_raw, "<draft>", require_tests=False)
        except PackLoadError as exc:
            return {"ok": False, "load_error": str(exc), "findings": [], "proposed_tests": [], "cases": 0, "changed": []}
        own_tests = pack.run_tests() if new_raw.get("tests") else []
        failing_tests = [t for t in own_tests if not t["passed"]]
        domains = new_raw.get("adversarial") or {}
        properties = [(p["id"], Expression(p["holds"]), p.get("claim", p["holds"]), p.get("when"))
                      for p in new_raw.get("properties") or []]
        keys = list(domains.keys())
        cases = 0
        proposed: list[dict[str, Any]] = []
        changed: list[dict[str, Any]] = []
        for combo in itertools.islice(itertools.product(*[domains[k] for k in keys]), max_cases):
            given = dict(zip(keys, combo))
            cases += 1
            decision = pack.evaluate(given)
            if old is not None:
                before = old.evaluate(given)
                if before.ok != decision.ok or before.outputs != decision.outputs:
                    changed.append({"given": given, "before": before.outputs if before.ok else before.error,
                                    "after": decision.outputs if decision.ok else decision.error})
            if not decision.ok:
                continue          # a guard refused it: that is the pack working
            scope = {**pack.defaults, **given, **decision.outputs}
            funcs = pack._functions()
            for pid, expr, claim, when in properties:
                if when and not Expression(when).evaluate(scope, funcs):
                    continue
                try:
                    holds = expr.evaluate(scope, funcs)
                except ExpressionError:
                    holds = False
                if not holds:
                    findings.append({"property": pid, "claim": claim, "given": given, "got": decision.outputs,
                                     "rule_ids": decision.rule_ids, "severity": "blocking"})
                    proposed.append({"name": f"gate-B: {pid} {given}", "given": given, "expect_error": claim})
        # One proposed regression test per distinct property is enough to stop it recurring.
        seen: set[str] = set()
        unique = []
        for t in proposed:
            prop = t["name"].split(" ")[1]
            if prop not in seen:
                seen.add(prop)
                unique.append(t)
        result = {"ok": not findings and not failing_tests, "cases": cases, "findings": findings[:50],
                  "finding_count": len(findings), "failing_tests": failing_tests, "proposed_tests": unique,
                  "changed": changed[:50], "changed_count": len(changed), "pack": pack.ref}
        self.audit.append(AuditEntry(
            actor="prativaad", action="prativaad.gate_b", kind="prativaad",
            outcome="objected" if findings or failing_tests else "cleared", policy_versions=[pack.ref],
            inputs={"cases": cases}, detail={"finding_count": len(findings), "failing_tests": len(failing_tests),
                                             "changed_count": len(changed)},
        ))
        return result

    # ── Gate C — governance lint (hrx validate) ───────────────────────────────

    def gate_c(self, wf: WorkflowDef) -> list[dict[str, Any]]:
        reg = self.registry
        findings: list[dict[str, Any]] = []

        def add(level: str, step: str | None, rule: str, message: str) -> None:
            findings.append({"level": level, "step": step, "rule": rule, "message": message})

        if wf.budget_inr_per_run is None:
            add("error", None, "C-BUDGET", "workflow declares no metrics.budget_inr_per_run — every run must have a cost ceiling")
        for step in wf.steps:
            if step.kind == "connector":
                conn = reg.connectors[step.connector]  # validated already
                spec = conn.manifest.actions[step.action]
                upstream = [a for a in wf.ancestors(step.id) if wf.step(a).kind == "reserved"]
                if spec.money and not upstream:
                    add("error", step.id, "C-MONEY",
                        f"{conn.name}.{step.action} moves money to or for a person and no reserved: step precedes it — "
                        "comparable actions are reserved (payroll.sign_off / finance approval)")
                if spec.irreversible and not step.compensation:
                    add("warning", step.id, "C-COMP", f"irreversible action {conn.name}.{step.action} declares no compensation:")
                if spec.side_effect and step.idempotency_key and "v" not in step.idempotency_key.split(":")[-1]:
                    add("warning", step.id, "C-KEYVER", "idempotency key has no version suffix (e.g. ':v1'); a workflow bump would reuse old keys")
            if step.kind == "skill":
                spec = reg.skills[step.skill]
                if spec.kind == "model" and spec.prompt_text and _looks_like_rule(spec.prompt_text):
                    add("error", step.id, "C-PROMPT-RULE",
                        f"prompt for {spec.name} contains what looks like a policy rule ({_looks_like_rule(spec.prompt_text)}) — rules live in policies/")
                if spec.kind == "model" and step.raw.get("model_tier", 0) and int(step.raw["model_tier"]) >= 3:
                    add("error", step.id, "C-TIER3", "tier 3 requested at the workflow level; tier 3 needs a per-skill opt-in")
            if step.kind == "reserved" and not step.question:
                add("error", step.id, "C-PACKET", "reserved step has no question: — a context packet must ask one specific question")
            if step.kind == "reserved" and not step.packet_from:
                add("warning", step.id, "C-PACKET-FROM", "reserved step attaches no computed outputs (packet_from:) for the approver")
        model_steps = [s for s in wf.steps if s.kind == "skill" and reg.skills[s.skill].kind == "model"]
        tier0_share = 1 - len(model_steps) / max(len(wf.steps), 1)
        if tier0_share < 0.7:
            add("warning", None, "C-TIER0", f"only {tier0_share:.0%} of steps are tier 0 (code); target is ≥ 70%")
        return findings

    # ── Gate D — fair hiring proxy-bias challenge ─────────────────────────────

    def gate_d(self, rationales: dict[str, str], *, run_id: str | None = None) -> list[dict[str, Any]]:
        pack = self.registry.pack("fair_hiring", self.clock.today())
        phrases: dict[str, str] = pack.tables.get("proxy_phrases", {})
        flags = []
        for candidate_id, text in rationales.items():
            for phrase, proxy_for in phrases.items():
                match = re.search(rf"\b{re.escape(phrase)}\b", text, flags=re.IGNORECASE)
                if match:
                    flags.append({"candidate": candidate_id, "phrase": match.group(0), "proxy_for": proxy_for,
                                  "span": [match.start(), match.end()],
                                  "claim": f"'{match.group(0)}' may stand in for {proxy_for}, a prohibited criterion"})
        result = GateResult("OBJECT" if flags else "CLEAR",
                            [Objection("proxy_bias", "medium", f["claim"], [f"candidate:{f['candidate']}"], "human_review")
                             for f in flags], ["proxy_bias"])
        self._log(run_id, "gate_d", "D", result)
        return flags


_RULE_SMELL = re.compile(r"\b\d+\s*(?:days?|months?|years?|weeks?|%|percent|lakh|rupees|inr|₹)\b|₹\s*\d", re.IGNORECASE)


def _looks_like_rule(prompt: str) -> str | None:
    match = _RULE_SMELL.search(prompt)
    return match.group(0) if match else None
