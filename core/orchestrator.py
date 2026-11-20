"""Durable workflow orchestrator.

Workflow state lives in ``workflow_runs`` / ``step_runs``. ``advance(run_id)``
moves a run forward as far as it can and stops at anything that needs a human,
a clock, or a recovering system. Because every step's state is persisted before
and after it acts — and connector actions are keyed and read back — killing the
process mid-run and calling ``advance`` again resumes without duplicating work.

Step kinds:

* ``skill``      — an agent skill. Deterministic skills never reach a model.
* ``connector``  — a side effect, through Devil's Advocate gate A and the governed executor.
* ``reserved``   — a decision only a named human can make; produces a receipt.
* ``route_only`` — POSH / grievance / whistleblower: hand off untouched, decide nothing.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.audit import AuditEntry
from core.clock import new_id, parse_ts
from core.connectors_sdk import TransportError
from core.db import dumps, loads
from core.pii import PointerOnlyViolation, PurposeViolation, UndeclaredInput
from core.devils_advocate import Objection
from core.router.router import CallContext
from core.rules.expr import Expression, ExpressionError
from core.rules.packs import Decision, PolicyViolation
from core.types import Principal, ProposedAction
from core.workflows import StepDef, WorkflowDef, render

if TYPE_CHECKING:
    from core.kernel import Kernel

TERMINAL = ("done", "skipped", "rejected", "cancelled", "compensated")
RETRY_BACKOFF_S = 2
REFUSAL_TITLES = {   # display names for why the kernel refused a skill; the audit keeps the exception type
    "PointerOnlyViolation": "no permission to use this person's data",
    "PurposeViolation": "data used for the wrong purpose",
    "UndeclaredInput": "the AI asked for data it didn't declare",
    "DeterministicViolation": "a rules-only step tried to use AI",
}
SYSTEM_NAMES = {"assets": "laptop", "tickets": "IT ticketing", "access": "access card", "directory": "email directory",
                "payroll": "payroll", "mail": "mail", "calendar": "calendar"}   # display names only
SYSTEM_NOTICE_AFTER = 3   # failed attempts before a person is told a system is down (an open breaker tells them at once)


class NeedsHuman(Exception):
    def __init__(self, question: str, packet: dict[str, Any], kind: str = "low_confidence", title: str | None = None):
        super().__init__(question)
        self.question = question
        self.packet = packet
        self.kind = kind
        self.title = title


class DeterministicViolation(Exception):
    """A deterministic skill tried to call a model."""


class SkillContext:
    """Everything a skill handler may use. Note what is absent: HTTP, DB, connectors."""

    def __init__(self, kernel: "Kernel", run: dict[str, Any], wf: WorkflowDef, step: StepDef, spec: Any,
                 args: dict[str, Any], scope: dict[str, Any], agent: Principal):
        self._kernel = kernel
        self._run = run
        self._wf = wf
        self._step = step
        self._spec = spec
        self._scope = scope
        self._agent = agent
        self.args = args
        self.manifest = dict(spec.raw)          # read-only view of the skill's own manifest
        self.today = kernel.clock.today()
        self.proposals: list[ProposedAction] = []
        self.policy_refs: list[str] = []
        self.rule_ids: list[str] = []
        self.cost_inr = 0.0
        self.tokens_in = 0
        self.tokens_out = 0
        self.tier = 0
        self.model_id: str | None = None
        self.escalations: list[str] = []
        self._source = kernel.sor.source_record(scope, args)

    # ── data access: declared inputs only ─────────────────────────────────────

    @property
    def subject_mode(self) -> str:
        return (self._scope.get("subject") or {}).get("processing_mode", "full")

    def input(self, path: str, default: Any = None) -> Any:
        if path not in self._spec.inputs:
            self._kernel.audit.append(AuditEntry(
                actor=self._agent.label, action="skill.read_undeclared", kind="policy", outcome="refused",
                run_id=self._run["id"], step_id=self._step.id, detail={"field": path, "skill": self._spec.ref}))
            raise UndeclaredInput(f"{self._spec.name} did not declare '{path}' in its manifest inputs")
        return self._source.get(path, default)

    def inputs(self) -> dict[str, Any]:
        return {k: self._source.get(k) for k in self._spec.inputs if k in self._source}

    # ── policy ────────────────────────────────────────────────────────────────

    def policy(self, pack: str, facts: dict[str, Any], *, must_pass: bool = True) -> Decision:
        decision = self._kernel.pdp.evaluate(pack, facts, actor=self._agent.label, run_id=self._run["id"],
                                             step_id=self._step.id, as_of=self.today)
        self.policy_refs.append(decision.pack_ref)
        self.rule_ids += decision.rule_ids
        if must_pass and not decision.ok:
            raise PolicyViolation(decision.pack_ref, decision.error_rule or "-", decision.error or "")
        return decision

    def lookup_policy_table(self, pack: str, table: str) -> dict[str, Any]:
        p = self._kernel.registry.pack(pack, self.today)
        return dict(p.tables.get(table) or {})

    def clauses(self, pack: str) -> list[dict[str, Any]]:
        p = self._kernel.registry.pack(pack, self.today)
        return [{**c, "pack": p.ref} for c in p.clauses]

    # ── model (metered, minimised) ────────────────────────────────────────────

    def ask_model(self, extra: dict[str, Any] | None = None, names: list[str] | None = None) -> dict[str, Any]:
        if self._spec.kind != "model" or self._step.deterministic:
            raise DeterministicViolation(f"{self._spec.name} in step '{self._step.id}' is deterministic: no model call permitted")
        subject = self._scope.get("subject")
        source = {**self._source, **(extra or {})}
        minimised = self._kernel.proxy.minimise(source, self._spec.inputs, subject, extra_names=names)
        budget = self._run.get("budget_inr")
        remaining = None if budget is None else max(budget - float(self._run.get("cost_inr") or 0) - self.cost_inr, 0)
        ctx = CallContext(run_id=self._run["id"], step_id=self._step.id, actor=self._agent.label,
                          on_behalf_of=self._agent.on_behalf_of.label if self._agent.on_behalf_of else None,
                          budget_remaining_inr=remaining, max_tier=self._kernel.router.config.max_tier,
                          source_record=self._kernel.sor.masked(source, self._spec.inputs))
        result = self._kernel.router.complete(self._spec, minimised, ctx)
        self.cost_inr += result.inr
        self.tokens_in += result.tokens_in
        self.tokens_out += result.tokens_out
        self.tier = max(self.tier, result.tier)
        self.model_id = result.model
        self.escalations += result.escalations
        output = minimised.rehydrate(result.output)
        if result.needs_human:
            # Low confidence is treated like a reserved decision: stop and ask one plain question.
            template = self._spec.raw.get("needs_human_question") or "The agent was not confident enough to rely on its draft. Is the draft correct?"
            question = render(template, self._scope)
            tried_bigger = " even after trying the bigger model" if result.tier != self._spec.model_tier else ""
            raise NeedsHuman(
                question,
                {"summary": f"The AI wasn't sure enough{tried_bigger}, so HR Autopilot stopped instead of guessing.",
                 "draft": output, "reason": result.reason, "escalations": result.escalations, "model": result.model},
                kind="low_confidence", title=self._spec.raw.get("needs_human_title") or f"Low confidence · {self._spec.name}")
        return output

    # ── proposals and escalation ──────────────────────────────────────────────

    def propose(self, action: str, args: dict[str, Any], idem_key: str | None = None) -> None:
        allowed = set(self._step.raw.get("may_propose") or [])
        connector, _, connector_action = action.rpartition(".")
        self.proposals.append(ProposedAction(action=action, args=args, idem_key=idem_key, connector=connector or None,
                                             connector_action=connector_action or None, run_id=self._run["id"],
                                             step_id=self._step.id, workflow=self._wf.name, skill=self._spec.name,
                                             evidence={"in_step_scope": action in allowed}))

    def needs_human(self, question: str, packet: dict[str, Any], kind: str = "low_confidence", title: str | None = None) -> None:
        raise NeedsHuman(question, packet, kind, title)

    # ── read-only governance hooks (no egress, no writes) ─────────────────────

    def challenge_rationales(self, rationales: dict[str, str]) -> list[dict[str, Any]]:
        """Devil's Advocate gate D. Flags proxy phrases for the human reviewer; never rewrites a ranking."""
        return self._kernel.devils_advocate.gate_d(rationales, run_id=self._run["id"])

    def is_suppressed(self, public_url: str) -> bool:
        """Has this person objected to contact? Checked before anything else touches them."""
        return self._kernel.dpdp.is_suppressed(public_url)


class Orchestrator:
    def __init__(self, kernel: "Kernel"):
        self.k = kernel
        # One advancer per run: the background worker and an API request must never execute
        # the same step at the same time (found live: model calls ran twice, connectors were
        # saved only by their idempotency keys).
        self._run_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, run_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._run_locks.setdefault(run_id, threading.Lock())

    # ── run lifecycle ─────────────────────────────────────────────────────────

    def start(self, workflow: str, *, subject_id: str | None, inputs: dict[str, Any], principal: Principal,
              channel: str = "web", tags: list[str] | None = None) -> str:
        wf = self.k.registry.workflow(workflow)
        switch = self.k.killswitch.blocking(workflow=wf.name)
        inputs = self._with_defaults(wf, inputs)
        run_id = new_id("run")
        now = self.k.clock.now_iso()
        with self.k.store.tx() as conn:
            conn.execute(
                "INSERT INTO workflow_runs (id, workflow, version, subject, inputs, facts, status, principal, channel, created_at, "
                "budget_inr, tags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, wf.name, wf.version, subject_id, dumps(inputs), dumps({}), "running", principal.id, channel, now,
                 wf.budget_inr_per_run, dumps(tags or [])),
            )
            for position, step in enumerate(wf.steps):
                conn.execute("INSERT INTO step_runs (run_id, step_id, kind, status, position) VALUES (?,?,?,?,?)",
                             (run_id, step.id, step.kind, "pending", position))
        self.k.audit.append(AuditEntry(
            actor=principal.label, action=f"run.start.{wf.name}", kind="step", outcome="ok", run_id=run_id,
            inputs={"workflow": wf.ref, "subject": subject_id, "inputs": inputs, "channel": channel},
            detail={"steps": len(wf.steps), "budget_inr": wf.budget_inr_per_run, "kill_switch": bool(switch)},
        ))
        self.advance(run_id)
        return run_id

    def _with_defaults(self, wf: WorkflowDef, inputs: dict[str, Any]) -> dict[str, Any]:
        """Fill declared input defaults. A default may be a template such as '{{today}}'."""
        merged = dict(inputs)
        scope = {"today": self.k.clock.today(), "now": self.k.clock.now_iso()}
        for name, spec in wf.inputs.items():
            if name not in merged and isinstance(spec, dict) and "default" in spec:
                merged[name] = render(spec["default"], scope)
        return merged

    def run(self, run_id: str) -> dict[str, Any]:
        row = self.k.store.one("SELECT * FROM workflow_runs WHERE id=?", (run_id,))
        if not row:
            raise KeyError(run_id)
        for key, default in (("inputs", {}), ("facts", {}), ("policy_versions", []), ("tags", [])):
            row[key] = loads(row[key], default)
        return row

    def steps(self, run_id: str) -> dict[str, dict[str, Any]]:
        rows = self.k.store.query("SELECT * FROM step_runs WHERE run_id=? ORDER BY position", (run_id,))
        out = {}
        for r in rows:
            r["outputs"] = loads(r["outputs"], None)
            out[r["step_id"]] = r
        return out

    def active_run_ids(self) -> list[str]:
        return [r["id"] for r in self.k.store.query("SELECT id FROM workflow_runs WHERE status IN ('running','waiting','paused') ORDER BY created_at")]

    def tick(self) -> int:
        moved = 0
        for run_id in self.active_run_ids():
            try:
                moved += self.advance(run_id)
            except Exception as exc:  # noqa: BLE001 - one bad run must not stop the others
                self.k.audit.append(AuditEntry(actor="kernel", action="run.advance_error", kind="system", outcome="failed",
                                               run_id=run_id, detail={"error": repr(exc)}))
        return moved

    def advance(self, run_id: str) -> int:
        lock = self._lock_for(run_id)
        if not lock.acquire(timeout=30):
            return 0
        try:
            return self._advance(run_id)
        finally:
            lock.release()

    def _advance(self, run_id: str) -> int:
        moved = 0
        for _ in range(200):  # bounded: a run can never spin the worker
            run = self.run(run_id)
            if run["status"] in ("completed", "closed", "cancelled", "compensated", "failed"):
                return moved
            wf = self.k.registry.workflow(run["workflow"], run["version"])
            if self._handle_kill_switch(run, wf):
                return moved
            progressed = False
            steps = self.steps(run_id)
            for step in wf.steps:
                sr = steps[step.id]
                if sr["status"] in TERMINAL or sr["status"] in ("awaiting_human", "paused", "refused", "failed"):
                    continue
                if not all(steps[n]["status"] in ("done", "skipped") for n in step.needs):
                    continue
                before = (sr["status"], sr["attempts"], sr["scheduled_for"])
                self._run_step(run, wf, step, sr)
                after = self.k.store.one("SELECT status, attempts, scheduled_for FROM step_runs WHERE run_id=? AND step_id=?", (run_id, step.id))
                if (after["status"], after["attempts"], after["scheduled_for"]) != before:
                    progressed = True
                    moved += 1
                    break  # re-read state after every change: simple and always consistent
            if not progressed:
                break
        self._settle(run_id)
        return moved

    def _settle(self, run_id: str) -> None:
        run = self.run(run_id)
        if run["status"] in ("completed", "closed", "cancelled", "compensated", "paused"):
            return
        steps = self.steps(run_id)
        statuses = [s["status"] for s in steps.values()]
        if all(s in ("done", "skipped") for s in statuses):
            self._close(run_id, "completed")
        elif any(s in ("awaiting_human", "refused", "failed", "paused") for s in statuses):
            self._set_run(run_id, status="waiting")
        else:
            self._set_run(run_id, status="running")

    def _close(self, run_id: str, status: str) -> None:
        cost = self.k.store.one("SELECT COALESCE(SUM(cost_inr),0) AS c FROM step_runs WHERE run_id=?", (run_id,))["c"]
        self._set_run(run_id, status=status, closed_at=self.k.clock.now_iso(), cost_inr=cost)
        run = self.run(run_id)
        self.k.audit.append(AuditEntry(actor="kernel", action=f"run.{status}.{run['workflow']}", kind="step", outcome="ok",
                                       run_id=run_id, inr=0, policy_versions=run["policy_versions"],
                                       detail={"cost_inr": round(cost, 4)}))

    # ── kill switch parking ───────────────────────────────────────────────────

    def _handle_kill_switch(self, run: dict[str, Any], wf: WorkflowDef) -> bool:
        switch = self.k.killswitch.blocking(workflow=wf.name)
        if switch and run["status"] != "paused":
            self._set_run(run["id"], status="paused")
            steps = self.steps(run["id"])
            self.k.queue.create(
                kind="paused", run_id=run["id"], step_id=None, title=f"Paused · {wf.name} run for {run['subject']}",
                question="This run is parked by a kill switch. Finish the remaining steps by hand, or leave it to resume automatically when the switch is released?",
                approver_roles=["hr_business_partner", "hr_head"],
                packet={"summary": f"Kill switch {switch['scope']}:{switch['target']} engaged by {switch['actor']}",
                        "reason": switch.get("reason"),
                        "computed": {"done": [s for s, r in steps.items() if r["status"] == "done"],
                                     "remaining": [s for s, r in steps.items() if r["status"] not in TERMINAL]},
                        "clauses": [], "options": ["finish_by_hand", "leave_parked"]},
            )
            return True
        if switch:
            return True
        if run["status"] == "paused":
            self._set_run(run["id"], status="running")
            for item in self.k.queue.list("open"):
                if item["run_id"] == run["id"] and item["kind"] == "paused":
                    with self.k.store.tx() as conn:
                        conn.execute("UPDATE human_queue SET status='auto_resumed', decided_at=? WHERE id=?",
                                     (self.k.clock.now_iso(), item["id"]))
            self.k.audit.append(AuditEntry(actor="kernel", action="run.resume", kind="step", outcome="ok", run_id=run["id"],
                                           detail={"reason": "kill switch released"}))
        return False

    # ── step execution ────────────────────────────────────────────────────────

    def _scope(self, run: dict[str, Any]) -> dict[str, Any]:
        steps = self.steps(run["id"])
        subject = self.k.sor.subject_view(run["subject"]) if run["subject"] else {}
        return {
            "inputs": run["inputs"],
            "subject": subject,
            "facts": run["facts"],
            "steps": {sid: (s["outputs"] or {}) for sid, s in steps.items() if s["status"] == "done"},
            "today": self.k.clock.today(),
            "now": self.k.clock.now_iso(),
            "run": {"id": run["id"], "workflow": run["workflow"], "channel": run["channel"]},
        }

    def agent_for(self, run: dict[str, Any], wf: WorkflowDef) -> Principal:
        human = self.k.principal(run["principal"])
        return Principal(id=f"agent:{wf.name}@v{wf.version}", kind="agent", name=f"{wf.name} agent",
                         roles=[], org_units=[], on_behalf_of=human)

    def _run_step(self, run: dict[str, Any], wf: WorkflowDef, step: StepDef, sr: dict[str, Any]) -> None:
        scope = self._scope(run)
        if sr["status"] == "pending" and step.when is not None:
            try:
                go = bool(step.when.evaluate(scope))
            except ExpressionError as exc:
                return self._fail(run, step, f"when: could not be evaluated: {exc}")
            if not go:
                self._set_step(run["id"], step.id, status="skipped", finished_at=self.k.clock.now_iso(), note="condition false")
                self.k.audit.append(AuditEntry(actor="kernel", action=f"step.skip.{step.id}", kind="step", outcome="skipped",
                                               run_id=run["id"], step_id=step.id, detail={"when": step.when.source}))
                return
        handler = {"skill": self._run_skill, "connector": self._run_connector,
                   "reserved": self._run_reserved, "route_only": self._run_route_only}[step.kind]
        try:
            handler(run, wf, step, sr, scope)
        except ExpressionError as exc:
            self._fail(run, step, f"template could not be rendered: {exc}")

    def _run_skill(self, run: dict[str, Any], wf: WorkflowDef, step: StepDef, sr: dict[str, Any], scope: dict[str, Any]) -> None:
        spec = self.k.registry.skills[step.skill]
        switch = self.k.killswitch.blocking(skill=spec.name)
        if switch:
            return self._park_step(run, step, f"kill switch {switch['scope']}:{switch['target']}")
        agent = self.agent_for(run, wf)
        args = render(step.args, scope)
        ctx = SkillContext(self.k, run, wf, step, spec, args, scope, agent)
        self._set_step(run["id"], step.id, status="running", started_at=self.k.clock.now_iso(), attempts=sr["attempts"] + 1)
        try:
            outputs = spec.run(ctx)
        except NeedsHuman as nh:
            self._charge(run, step, ctx)
            packet = {**nh.packet, "clauses": nh.packet.get("clauses") or _clauses(ctx)}
            self._to_human(run, step, kind=nh.kind, title=nh.title or f"{step.title or step.id} needs a decision",
                           question=nh.question, packet=packet, roles=step.raw.get("escalate_to_roles") or ["hr_business_partner"])
            return
        except PolicyViolation as pv:
            self._charge(run, step, ctx)
            self._to_human(run, step, kind="policy_violation", title=f"Policy guard failed · {step.title or step.id}",
                           question=f"Rule {pv.rule_id} in {pv.pack_ref} refused this: “{pv.message}”. Correct the input data, or route as a policy exception?",
                           packet={"summary": pv.message, "conflict": f"{pv.pack_ref} {pv.rule_id}", "computed": args,
                                   "clauses": [{"pack": pv.pack_ref, "rule_ids": [pv.rule_id]}] + _clauses(ctx)},
                           roles=["hr_business_partner", "hr_head"])
            return
        except (PointerOnlyViolation, UndeclaredInput, PurposeViolation, DeterministicViolation) as exc:
            self.k.audit.append(AuditEntry(actor=agent.label, action=f"skill.{spec.name}", kind="policy", outcome="refused",
                                           run_id=run["id"], step_id=step.id, detail={"error": str(exc), "type": type(exc).__name__}))
            self._to_human(run, step, kind="refused", title=f"Blocked · {REFUSAL_TITLES.get(type(exc).__name__, 'a safety rule')}",
                           question=f"HR Autopilot blocked this step: {exc}. Stop this step, or complete it by hand?",
                           packet={"summary": str(exc), "conflict": type(exc).__name__, "clauses": _clauses(ctx)},
                           roles=["hr_business_partner"], status="refused")
            return
        except Exception as exc:  # noqa: BLE001 - a buggy skill must fail safe, never crash the kernel
            self._charge(run, step, ctx)
            self.k.audit.append(AuditEntry(actor=agent.label, action=f"skill.{spec.name}", kind="step", outcome="failed",
                                           run_id=run["id"], step_id=step.id, detail={"error": repr(exc)}))
            self._to_human(run, step, kind="failure", title=f"Skill error · {spec.name}",
                           question=f"{spec.name} raised an error ({type(exc).__name__}: {exc}). Retry after a fix, or mark the step done by hand?",
                           packet={"summary": repr(exc), "clauses": _clauses(ctx), "options": ["retry", "mark_done"]},
                           roles=["hr_business_partner"], status="failed")
            return

        problems = spec.validate_output(outputs)
        if problems:
            self._charge(run, step, ctx)
            return self._to_human(run, step, kind="schema", title=f"Invalid output · {spec.name}",
                                  question=f"{spec.name} returned output that violates its schema ({problems}). Provide the values by hand?",
                                  packet={"summary": "schema violation", "draft": outputs, "clauses": _clauses(ctx)},
                                  roles=["hr_business_partner"])

        proposal_results = []
        for proposal in ctx.proposals:
            if not proposal.evidence.get("in_step_scope"):
                # Step-scope intersection: an agent may only propose what its step allows.
                res_reason = f"{proposal.action} is outside this step's scope (may_propose)"
                classification = self.k.registry.reserved.classify(proposal.action, "agent")
                status = 403
                if classification.outcome == "refuse":
                    res_reason = f"RESERVED — {classification.reason}"
                self.k.audit.append(AuditEntry(actor=agent.label, on_behalf_of=agent.on_behalf_of.label if agent.on_behalf_of else None,
                                               action=proposal.action, kind="reserved" if "RESERVED" in res_reason else "policy",
                                               outcome="refused", run_id=run["id"], step_id=step.id,
                                               policy_versions=[self.k.registry.reserved.ref],
                                               detail={"status": status, "reason": res_reason}))
                proposal_results.append({"action": proposal.action, "outcome": "refused", "status": status, "reason": res_reason})
                continue
            result = self.k.executor.submit(proposal, agent, scope.get("subject") or None)
            proposal_results.append({"action": proposal.action, "outcome": result.outcome, "status": result.status, "reason": result.reason})
        if proposal_results:
            outputs = {**outputs, "_proposals": proposal_results}

        self._charge(run, step, ctx)
        self._finish_step(run, step, outputs, ctx=ctx)

    def _run_connector(self, run: dict[str, Any], wf: WorkflowDef, step: StepDef, sr: dict[str, Any], scope: dict[str, Any]) -> None:
        connector = self.k.registry.connectors[step.connector]
        now = self.k.clock.now()
        if step.raw.get("foreach"):
            if sr["status"] == "running" and sr["scheduled_for"] and parse_ts(sr["scheduled_for"]) > now:
                return  # retry backoff
            return self._run_fanout(run, wf, step, sr, scope, connector)
        args = render(step.args, scope)
        key = render(step.idempotency_key, scope) if step.idempotency_key else None

        # Scheduled steps wait for their time; the governing date is re-checked every tick.
        if step.schedule_at:
            should_be = _as_ts(render(step.schedule_at, scope))
            if sr["status"] == "pending":
                self._set_step(run["id"], step.id, status="scheduled", scheduled_for=should_be,
                               note=f"scheduled for {should_be[:16]}")
                self.k.audit.append(AuditEntry(actor=self.agent_for(run, wf).label, action=f"step.schedule.{step.id}", kind="step",
                                               outcome="scheduled", run_id=run["id"], step_id=step.id,
                                               detail={"scheduled_for": should_be}))
                return
            if sr["status"] == "scheduled":
                objection = self.k.devils_advocate.check_schedule(run_id=run["id"], step_id=step.id,
                                                            scheduled_for=sr["scheduled_for"], should_be=should_be)
                if objection:
                    for oid in self.k.devils_advocate.latest_objection_ids(run["id"], step.id):
                        self.k.devils_advocate.resolve(oid, f"auto-corrected: rescheduled {sr['scheduled_for'][:16]} → {should_be[:16]}", True)
                    self._set_step(run["id"], step.id, scheduled_for=should_be,
                                   note=f"rescheduled by Devil's Advocate (date_ordering): {sr['scheduled_for'][:16]} → {should_be[:16]}")
                    return
                if parse_ts(sr["scheduled_for"]) > now:
                    return
        if sr["status"] == "running" and sr["scheduled_for"] and parse_ts(sr["scheduled_for"]) > now:
            return  # retry backoff
        agent = self.agent_for(run, wf)
        spec = connector.manifest.actions[step.action]

        # Devil's Advocate gate A — once per step, before an irreversible action.
        if spec.irreversible and not sr["gate"]:
            raw_pii = self.k.vault.raw_values_for(run["subject"]) if run["subject"] else set()
            try:
                # The model residue reviews the plan once per run (first irreversible step);
                # every irreversible step still gets the deterministic checks.
                review = self.k.devils_advocate_model_review(run, step, agent) if self.k.devils_advocate.spent_inr(run["id"]) == 0 else None
                gate = self.k.devils_advocate.gate_a(run=run, wf=wf, step=step, connector=connector, args=args, idem_key=key or "",
                                               scope=scope, raw_pii=raw_pii, model_review=review)
                blocking = gate.blocking
                unresolved = self._auto_resolve(connector, step, args, key or "", blocking) if blocking else []
            except TransportError as exc:
                # A gate that cannot verify must not wave the action through: wait and re-check.
                self.k.breaker.record_failure(connector.name)
                retry_at = datetime.fromtimestamp(now.timestamp() + RETRY_BACKOFF_S, tz=now.tzinfo).isoformat()
                if sr["attempts"] + 1 >= SYSTEM_NOTICE_AFTER:
                    self._notify_system_down(run, step, connector, key or "", sr["attempts"] + 1, str(exc))
                return self._set_step(run["id"], step.id, status="running", attempts=sr["attempts"] + 1, scheduled_for=retry_at,
                                      note=f"The Devil's Advocate could not read {connector.manifest.system} to check for duplicates, so it is waiting")
            if gate.cost_inr:
                # Devil's Advocate's review is metered to the run but does not change where the step itself ran.
                self._add_cost(run["id"], step.id, gate.cost_inr, tier=0)
            ids = self.k.devils_advocate.latest_objection_ids(run["id"], step.id)
            if blocking:
                if unresolved:
                    return self._to_human(
                        run, step, kind="objection", title=f"The Devil's Advocate has a concern · {step.title or step.id}",
                        question=f"The Devil's Advocate raised {len(unresolved)} concern(s) before this step. "
                                 "Go ahead anyway, or skip it?",
                        packet={"summary": unresolved[0].claim, "objections": [o.as_dict() for o in unresolved],
                                "objection_ids": ids, "computed": {"args": args, "idempotency_key": key},
                                "clauses": [], "options": ["proceed", "skip_step"]},
                        roles=["hr_business_partner"])
                for oid in ids:
                    self.k.devils_advocate.resolve(oid, "verified by kernel read-back: " + "; ".join(o.claim for o in blocking), True)
            advisory = len(gate.objections) - len(blocking)
            if blocking:
                note = "The Devil's Advocate raised a concern. HR Autopilot checked the other system and it was fine."
            elif advisory:
                note = f"The Devil's Advocate noted {advisory} minor point(s). Nothing serious."
            else:
                note = "Devil's Advocate: clear"
            self._set_step(run["id"], step.id, gate=("verified" if blocking else "advisory" if advisory else "clear"), note=note)

        proposal = ProposedAction(action=f"{connector.name}.{step.action}", args=args, idem_key=key, connector=connector.name,
                                  connector_action=step.action, run_id=run["id"], step_id=step.id, subject_id=run["subject"],
                                  workflow=wf.name)
        attempts = sr["attempts"] + 1
        self._set_step(run["id"], step.id, status="running", attempts=attempts, started_at=sr["started_at"] or self.k.clock.now_iso())
        result = self.k.executor.submit(proposal, agent, scope.get("subject") or None)
        if result.done:
            self._close_system_notice(run, step.id, "the system came back and HR Autopilot finished the step automatically")
            self._add_cost(run["id"], step.id, connector.manifest.cost_inr_per_call, tier=0)
            outputs = {**(result.result or {}), "idempotency_key": key, "outcome": result.outcome}
            return self._finish_step(run, step, outputs)
        if result.outcome in ("retrying", "waiting"):
            if result.outcome == "waiting" or attempts >= SYSTEM_NOTICE_AFTER:
                self._notify_system_down(run, step, connector, key, attempts, result.reason)
            retry_at = (self.k.clock.now().timestamp() + RETRY_BACKOFF_S)
            self._set_step(run["id"], step.id, status="running", note=result.reason,
                           scheduled_for=datetime.fromtimestamp(retry_at, tz=now.tzinfo).isoformat())
            return
        if result.outcome == "paused":
            return self._park_step(run, step, result.reason)
        if result.outcome == "refused":
            return self._to_human(run, step, kind="refused", title=f"Refused · {connector.name}.{step.action}",
                                  question=f"The kernel refused this action ({result.status}): {result.reason}. Complete it by hand outside the platform, or abort the run?",
                                  packet={"summary": result.reason, "conflict": f"HTTP {result.status}",
                                          "computed": {"args": args, "idempotency_key": key},
                                          "clauses": [{"pack": p, "rule_ids": result.rule_ids} for p in result.policy_versions],
                                          "options": ["mark_done", "abort"]},
                                  roles=["hr_business_partner"], status="refused")
        return self._to_human(run, step, kind="failure", title=f"Failed · {connector.name}.{step.action}",
                              question=f"{connector.name}.{step.action} failed after {attempts} attempt(s): {result.reason}. Retry with the same key, compensate and abort the run, or mark done by hand?",
                              packet={"summary": result.reason, "computed": {"args": args, "idempotency_key": key, "attempts": attempts},
                                      "clauses": [], "options": ["retry", "compensate", "mark_done"]},
                              roles=["hr_business_partner"], status="failed")

    def _run_fanout(self, run: dict[str, Any], wf: WorkflowDef, step: StepDef, sr: dict[str, Any], scope: dict[str, Any],
                    connector: Any) -> None:
        """``foreach:`` — one keyed action per item (e.g. one notice per approved recipient).

        Re-entrant by construction: on a retry, items that already landed are
        deduplicated by the outbox under their own keys, so only the remainder runs.
        Each item passes through the full governed executor and gets its own audit entry.
        """
        items = render(step.raw["foreach"], scope) or []
        agent = self.agent_for(run, wf)
        now = self.k.clock.now()
        self._set_step(run["id"], step.id, status="running", attempts=sr["attempts"] + 1,
                       started_at=sr["started_at"] or self.k.clock.now_iso())
        results, waiting, failed = [], False, []
        for index, item in enumerate(items):
            item_scope = {**scope, "item": item, "index": index}
            args = render(step.args, item_scope)
            key = render(step.idempotency_key, item_scope) if step.idempotency_key else None
            proposal = ProposedAction(action=f"{connector.name}.{step.action}", args=args, idem_key=key, connector=connector.name,
                                      connector_action=step.action, run_id=run["id"], step_id=step.id,
                                      subject_id=run["subject"], workflow=wf.name)
            res = self.k.executor.submit(proposal, agent, scope.get("subject") or None)
            results.append({"index": index, "key": key, "outcome": res.outcome, "status": res.status,
                            "reason": "" if res.done else res.reason, "record_id": (res.result or {}).get("record_id")})
            if res.outcome in ("retrying", "waiting"):
                waiting = True
            elif res.outcome in ("failed", "paused"):
                failed.append(results[-1])
        if failed:
            return self._to_human(run, step, kind="failure", title=f"Fan-out failed · {step.title or step.id}",
                                  question=f"{len(failed)} of {len(items)} item(s) failed in {connector.name}.{step.action}. Retry the failed items with the same keys, or mark the step done by hand?",
                                  packet={"summary": failed[0]["reason"], "computed": {"items": results}, "clauses": [],
                                          "options": ["retry", "mark_done"]},
                                  roles=["hr_business_partner"], status="failed")
        if waiting:
            retry_at = datetime.fromtimestamp(now.timestamp() + RETRY_BACKOFF_S, tz=now.tzinfo).isoformat()
            return self._set_step(run["id"], step.id, status="running", scheduled_for=retry_at,
                                  note=f"{sum(r['outcome'] in ('executed', 'deduplicated') for r in results)}/{len(items)} done; retrying the rest with the same keys")
        executed = sum(r["outcome"] in ("executed", "deduplicated") for r in results)
        refused = sum(r["outcome"] == "refused" for r in results)
        self._add_cost(run["id"], step.id, connector.manifest.cost_inr_per_call * executed, tier=0)
        self._finish_step(run, step, {"items": results, "executed": executed, "refused": refused, "total": len(items)})

    def _auto_resolve(self, connector: Any, step: StepDef, args: dict[str, Any], key: str, blocking: list[Objection]) -> list[Objection]:
        """The kernel resolves what it can by *reading* (never by acting). The rest goes to a human."""
        unresolved = []
        for o in blocking:
            if o.cls == "duplicate_side_effect":
                priors = connector.prior_effects(step.action or "", args, key)
                verdicts = [connector.is_effect_closed(p) for p in priors]
                if priors and all(closed for closed, _ in verdicts):
                    o.claim += " — kernel verified: " + "; ".join(e for _, e in verdicts)
                    continue
            unresolved.append(o)
        return unresolved

    def _run_reserved(self, run: dict[str, Any], wf: WorkflowDef, step: StepDef, sr: dict[str, Any], scope: dict[str, Any]) -> None:
        entry = self.k.registry.reserved.entries[step.reserved_action]
        packet = self.build_packet(run, wf, step, scope)
        question = render(step.question, scope) if step.question else f"Approve {step.reserved_action}?"
        self._to_human(run, step, kind="reserved", title=step.title or step.reserved_action, question=question,
                       packet=packet, roles=entry.approver_role, action=step.reserved_action)

    def _run_route_only(self, run: dict[str, Any], wf: WorkflowDef, step: StepDef, sr: dict[str, Any], scope: dict[str, Any]) -> None:
        role = self.k.registry.reserved.route_only[step.reserved_action]
        source_ref = render(step.args.get("source_ref", "{{run.id}}"), scope) if step.args else run["id"]
        packet = {
            "summary": "Passed straight to you. HR Autopilot didn't read, judge or summarise it.",
            "source_ref": source_ref,
            "route": {"action": step.reserved_action, "to_role": role},
            "platform_did": ["detected a route-only trigger with a deterministic lexicon rule", "stopped", "handed off"],
            "platform_did_not": ["classify", "summarise", "recommend", "notify the person named"],
            "clauses": [{"pack": self.k.registry.reserved.ref, "rule_ids": [f"route_only:{step.reserved_action}"]}],
        }
        self.k.audit.append(AuditEntry(actor="kernel", action=f"route_only.{step.reserved_action}", kind="reserved",
                                       outcome="routed", run_id=run["id"], step_id=step.id,
                                       policy_versions=[self.k.registry.reserved.ref],
                                       detail={"to_role": role, "classification_performed": False, "summary_performed": False}))
        self._to_human(run, step, kind="route_only", title=f"Route only · {step.reserved_action}",
                       question=f"Acknowledge that this matter has been received by the {role.replace('_', ' ')} and is handled outside the platform?",
                       packet=packet, roles=[role], action=step.reserved_action)

    # ── packets ───────────────────────────────────────────────────────────────

    def build_packet(self, run: dict[str, Any], wf: WorkflowDef, step: StepDef, scope: dict[str, Any]) -> dict[str, Any]:
        computed: dict[str, Any] = {}
        recommendation = None
        clauses: dict[str, set[str]] = {}
        for source in step.packet_from:
            outputs = dict(scope["steps"].get(source) or {})
            if "recommendation" in outputs:
                recommendation = {"text": outputs.pop("recommendation"), "confidence": outputs.pop("confidence", None),
                                  "labelled": "agent recommendation — not a decision"}
            outputs.pop("_proposals", None)
            computed[source] = outputs
            for entry in self.k.audit.for_run(run["id"]):
                if entry["step_id"] == source and entry["kind"] == "policy":
                    for pv in entry["policy_versions"]:
                        clauses.setdefault(pv, set()).update(entry["rule_ids"])
        subject = scope.get("subject") or {}
        return {
            "summary": step.raw.get("summary") and render(step.raw["summary"], scope) or step.title or step.reserved_action,
            "subject": {k: subject.get(k) for k in ("id", "display_name", "grade", "org_unit", "location", "employment_type") if k in subject},
            "computed": computed,
            "clauses": [{"pack": p, "rule_ids": sorted(r)} for p, r in sorted(clauses.items())],
            "recommendation": recommendation,
            "decision_fields": step.decision_fields,
            "workflow": wf.ref,
            "action": step.reserved_action,
        }

    # ── human decisions flow back here ────────────────────────────────────────

    def on_decision(self, item: dict[str, Any]) -> None:
        if item["status"] != "decided" or not item.get("run_id"):
            return
        decision = item["decision"]["decision"]
        values = item["decision"].get("values") or {}
        run = self.run(item["run_id"])
        step_id = item["step_id"]
        kind = item["kind"]
        human_outputs = {"decided_by": [a["by"] for a in item["approvals"]], "receipt_ids": item["receipt_ids"], "decision": decision}

        if kind == "paused":
            if decision in ("finish_by_hand", "approve"):
                for sid, sr in self.steps(run["id"]).items():
                    if sr["status"] not in TERMINAL:
                        self._set_step(run["id"], sid, status="done", human_touch=1, finished_at=self.k.clock.now_iso(),
                                       outputs=dumps({"completed_by_hand": True, **human_outputs}), note="finished by hand while paused")
                self._close(run["id"], "completed")
            return
        if step_id is None:
            return
        if kind == "reserved":
            if decision == "approve":
                self._finish_step(run, self.k.registry.workflow(run["workflow"], run["version"]).step(step_id),
                                  {**values, **human_outputs, "approved": True}, human=True)
            else:
                self._set_step(run["id"], step_id, status="rejected", human_touch=1, finished_at=self.k.clock.now_iso(),
                               outputs=dumps({**human_outputs, "approved": False}))
                for sid, sr in self.steps(run["id"]).items():
                    if sr["status"] not in TERMINAL:
                        self._set_step(run["id"], sid, status="skipped", note=f"upstream reserved decision {step_id} rejected")
                self._close(run["id"], "closed")
                return
        elif kind == "route_only":
            self._finish_step(run, self._step_def(run, step_id), {"handed_to": item["approver_roles"], "platform_action": "none", **human_outputs}, human=True)
        elif kind == "objection":
            ids = item["packet"].get("objection_ids") or []
            if decision in ("proceed", "approve"):
                for oid in ids:
                    self.k.devils_advocate.resolve(oid, f"overruled by human: {item['decision'].get('note') or 'no note'}", False)
                self._set_step(run["id"], step_id, status="pending", human_touch=1, gate="overruled", note="Devil's Advocate objection overruled by a human")
            else:
                for oid in ids:
                    self.k.devils_advocate.resolve(oid, "upheld by human: action skipped", True)
                self._set_step(run["id"], step_id, status="skipped", human_touch=1, note="skipped on Devil's Advocate objection (upheld)")
        elif kind == "system_down":
            if decision == "compensate":
                self.compensate(run["id"], reason=f"human chose to undo while {step_id} waited for a system that was down")
                return
            # "Keep waiting": nothing to change; the step is still retrying with the same key.
        elif kind in ("failure",):
            if decision == "retry":
                key = (item["packet"].get("computed") or {}).get("idempotency_key")
                if key:
                    with self.k.store.tx() as conn:
                        conn.execute("UPDATE outbox SET status='pending', attempts=1 WHERE idem_key=?", (key,))
                self._set_step(run["id"], step_id, status="pending", human_touch=1, note="retry requested by human (same key)")
            elif decision == "compensate":
                self.compensate(run["id"], reason=f"human chose compensation after {step_id} failed")
                return
            else:
                self._finish_step(run, self._step_def(run, step_id), {**values, **human_outputs, "completed_by_hand": True}, human=True)
        elif kind == "refused":
            if decision in ("abort",):
                self._cancel(run["id"], f"aborted after refusal at {step_id}")
                return
            self._finish_step(run, self._step_def(run, step_id), {**values, **human_outputs, "completed_by_hand": True}, human=True)
        else:  # low_confidence, policy_violation, schema
            if decision == "abort":
                self._cancel(run["id"], f"aborted by human at {step_id}")
                return
            draft = item["packet"].get("draft") or {}
            outputs = {**draft, **values} if decision in ("accept_draft", "approve") else values
            self._finish_step(run, self._step_def(run, step_id), {**outputs, **human_outputs}, human=True)
        self.advance(run["id"])

    def compensate(self, run_id: str, reason: str) -> list[dict[str, Any]]:
        """Saga: undo completed side effects in reverse order, each with a stable derived key."""
        run = self.run(run_id)
        wf = self.k.registry.workflow(run["workflow"], run["version"])
        agent = self.agent_for(run, wf)
        results = []
        steps = self.steps(run_id)
        for step in reversed(wf.steps):
            sr = steps[step.id]
            if step.kind != "connector" or sr["status"] != "done" or not step.compensation:
                continue
            outputs = sr["outputs"] or {}
            proposal = ProposedAction(action=f"{step.connector}.{step.compensation}",
                                      args={"original": outputs.get("response") or {}, "record_id": outputs.get("record_id"),
                                            "data": outputs.get("data") or {}},
                                      connector=step.connector, connector_action=step.compensation, run_id=run_id,
                                      step_id=step.id, subject_id=run["subject"], workflow=wf.name)
            res = self.k.executor.compensate(proposal, agent, outputs.get("idempotency_key") or f"{run_id}:{step.id}")
            results.append({"step": step.id, "compensation": step.compensation, "outcome": res.outcome, "reason": res.reason})
            if res.done:
                self._set_step(run_id, step.id, status="compensated", note=f"compensated via {step.compensation}")
        for sid, sr in self.steps(run_id).items():
            if sr["status"] not in TERMINAL:
                self._set_step(run_id, sid, status="cancelled", note="run compensated")
        self._close(run_id, "compensated")
        self.k.audit.append(AuditEntry(actor="kernel", action="run.compensate", kind="step", outcome="ok", run_id=run_id,
                                       detail={"reason": reason, "results": results}))
        return results

    def _cancel(self, run_id: str, reason: str) -> None:
        for sid, sr in self.steps(run_id).items():
            if sr["status"] not in TERMINAL:
                self._set_step(run_id, sid, status="cancelled", note=reason)
        self._close(run_id, "cancelled")

    # ── persistence helpers ───────────────────────────────────────────────────

    def _step_def(self, run: dict[str, Any], step_id: str) -> StepDef:
        return self.k.registry.workflow(run["workflow"], run["version"]).step(step_id)

    def _finish_step(self, run: dict[str, Any], step: StepDef, outputs: dict[str, Any], *, ctx: SkillContext | None = None,
                     human: bool = False) -> None:
        self._set_step(run["id"], step.id, status="done", outputs=dumps(outputs), finished_at=self.k.clock.now_iso(),
                       human_touch=1 if human else None)
        if step.export:
            facts = dict(self.run(run["id"])["facts"])
            scope = {**self._scope(run), "outputs": outputs}
            for fact, expr in step.export.items():
                try:
                    facts[fact] = Expression(expr).evaluate(scope)
                except ExpressionError:
                    continue
            self._set_run(run["id"], facts=dumps(facts))
        if ctx is not None and ctx.policy_refs:
            current = self.run(run["id"])["policy_versions"]
            merged = sorted(set(current) | set(ctx.policy_refs))
            self._set_run(run["id"], policy_versions=dumps(merged))
        self.k.audit.append(AuditEntry(
            actor=("human" if human else self.agent_for(run, self.k.registry.workflow(run["workflow"], run["version"])).label),
            action=f"step.complete.{step.id}", kind="step", outcome="ok", run_id=run["id"], step_id=step.id,
            policy_versions=sorted(set(ctx.policy_refs)) if ctx else [], rule_ids=ctx.rule_ids if ctx else [],
            prompt_version=(f"{ctx._spec.name}/v{ctx._spec.prompt_version}" if ctx and ctx.model_id else None),
            model_id=ctx.model_id if ctx else None, tier=ctx.tier if ctx else 0,
            tokens_in=ctx.tokens_in if ctx else 0, tokens_out=ctx.tokens_out if ctx else 0, inr=ctx.cost_inr if ctx else 0.0,
            detail={"outputs": _brief(outputs), "human_touch": human, "escalations": ctx.escalations if ctx else []},
        ))

    def _to_human(self, run: dict[str, Any], step: StepDef, *, kind: str, title: str, question: str, packet: dict[str, Any],
                  roles: list[str], action: str | None = None, status: str = "awaiting_human") -> None:
        self._close_system_notice(run, step.id, "replaced by a decision item")
        if self.k.queue.open_for_step(run["id"], step.id) is None:
            self.k.queue.create(kind=kind, run_id=run["id"], step_id=step.id, title=title, question=question,
                                packet={**packet, "workflow": packet.get("workflow") or run["workflow"],
                                        "subject_id": run["subject"]}, approver_roles=roles, action=action)
        self._set_step(run["id"], step.id, status=status, human_touch=1, note=title)
        self.k.check_workflow_breaker(run["workflow"])

    def _notify_system_down(self, run: dict[str, Any], step: StepDef, connector: Any, key: str, attempts: int, reason: str) -> None:
        """Tell a person a system is down, with context, while the intent stays held in the outbox.
        The step keeps retrying with the same key, so it still finishes by itself, exactly once, when the system returns."""
        if self.k.queue.open_for_step(run["id"], step.id) is not None:
            return
        already = self.k.store.one("SELECT 1 AS x FROM human_queue WHERE run_id=? AND step_id=? AND kind='system_down' AND status!='resolved'",
                                   (run["id"], step.id))
        if already:     # told once per outage; "keep waiting" is not asked again on every retry
            return
        system = SYSTEM_NAMES.get(connector.manifest.system, connector.manifest.system)
        self.k.queue.create(
            kind="system_down", run_id=run["id"], step_id=step.id, title=f"System down · {step.title or step.id}",
            question=f"The {system} system is not responding, so '{step.title or step.id}' is on hold. "
                     "HR Autopilot will finish it automatically when the system is back. Keep waiting, or undo this process?",
            packet={"summary": f"HR Autopilot tried {attempts} time(s) and is holding the request safely. Nothing has been done twice.",
                    "computed": {"system": system, "step": step.title or step.id, "attempts": attempts,
                                 "last_error": reason, "idempotency_key": key},
                    "workflow": run["workflow"], "subject_id": run["subject"], "clauses": [],
                    "options": ["acknowledge", "compensate"]},
            approver_roles=["hr_business_partner", "it_lead"])

    def _close_system_notice(self, run: dict[str, Any], step_id: str, why: str) -> None:
        item = self.k.queue.open_for_step(run["id"], step_id)
        if not item or item["kind"] != "system_down":
            return
        with self.k.store.tx() as conn:
            conn.execute("UPDATE human_queue SET status='resolved' WHERE id=?", (item["id"],))
        self.k.audit.append(AuditEntry(actor="kernel", action="queue.system_down.resolved", kind="human", outcome="ok",
                                       run_id=run["id"], step_id=step_id, detail={"queue_id": item["id"], "reason": why}))

    def _park_step(self, run: dict[str, Any], step: StepDef, reason: str) -> None:
        self._to_human(run, step, kind="failure", title=f"Parked · {step.title or step.id}",
                       question=f"This step is parked ({reason}). Retry once the switch is released, or mark it done by hand?",
                       packet={"summary": reason, "clauses": [], "options": ["retry", "mark_done"]},
                       roles=["hr_business_partner"], status="paused")

    def _fail(self, run: dict[str, Any], step: StepDef, reason: str) -> None:
        self._to_human(run, step, kind="failure", title=f"Error · {step.title or step.id}",
                       question=f"This step could not run: {reason}. Mark it done by hand, or abort the run?",
                       packet={"summary": reason, "clauses": [], "options": ["mark_done", "abort"]},
                       roles=["hr_business_partner"], status="failed")

    def _charge(self, run: dict[str, Any], step: StepDef, ctx: SkillContext) -> None:
        if ctx.cost_inr or ctx.tier:
            self._add_cost(run["id"], step.id, ctx.cost_inr, tier=ctx.tier)

    def _add_cost(self, run_id: str, step_id: str, inr: float, tier: int) -> None:
        with self.k.store.tx() as conn:
            conn.execute("UPDATE step_runs SET cost_inr=cost_inr+?, tier=MAX(tier, ?) WHERE run_id=? AND step_id=?",
                         (inr, tier, run_id, step_id))
            conn.execute("UPDATE workflow_runs SET cost_inr=cost_inr+? WHERE id=?", (inr, run_id))

    def _set_step(self, run_id: str, step_id: str, **fields: Any) -> None:
        fields = {k: v for k, v in fields.items() if v is not None}
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.k.store.tx() as conn:
            conn.execute(f"UPDATE step_runs SET {sets} WHERE run_id=? AND step_id=?", (*fields.values(), run_id, step_id))

    def _set_run(self, run_id: str, **fields: Any) -> None:
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.k.store.tx() as conn:
            conn.execute(f"UPDATE workflow_runs SET {sets} WHERE id=?", (*fields.values(), run_id))


def _clauses(ctx: SkillContext) -> list[dict[str, Any]]:
    return [{"pack": ref, "rule_ids": sorted(set(ctx.rule_ids))} for ref in sorted(set(ctx.policy_refs))]


def _brief(outputs: dict[str, Any]) -> dict[str, Any]:
    text = dumps(outputs)
    return outputs if len(text) < 1500 else {"keys": sorted(outputs.keys()), "truncated": True}


def _as_ts(value: Any) -> str:
    """Accept '2026-12-01 18:00', '2026-12-01T18:00:00+00:00' or a date; return ISO-8601 UTC."""
    text = str(value).strip().replace(" ", "T", 1)
    if len(text) == 10:
        text += "T18:00:00"
    if len(text) == 16:
        text += ":00"
    dt = parse_ts(text)
    return dt.isoformat()
