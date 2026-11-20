"""Gatekeeper — the governance kernel. Wires every component together.

The kernel is the only path to the outside world. Agents (skills) return
proposed actions; the kernel decides whether they happen, executes them once,
verifies them, prices them and writes them down.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import yaml

from core import config
from core.audit import AuditChain, AuditEntry
from core.clock import Clock
from core.db import Store
from core.dpdp import Dpdp
from core.executor import GovernedExecutor
from core.killswitch import ConnectorBreaker, KillSwitch
from core.orchestrator import Orchestrator
from core.pdp import PolicyDecisionPoint
from core.pii import PiiProxy, Vault
from core.devils_advocate import DevilsAdvocate, Objection
from core.queue import HumanQueue
from core.registry import Registry
from core.router.router import CallContext, Router, RoutingConfig
from core.sor import SystemOfRecord
from core.sor_service import RoutedTransport, SorService
from core.types import Principal, ProposedAction
from mocks.tbo import InProcessTransport, TboMocks


class Kernel:
    def __init__(self, db_path: Path | str | None = None, mocks_db_path: Path | str | None = None):
        self.store = Store(db_path or config.db_path())
        self.clock = Clock(self.store)
        self.audit = AuditChain(self.store, self.clock)
        self.mocks = TboMocks(mocks_db_path or config.mocks_db_path())
        self.transport = RoutedTransport(InProcessTransport(self.mocks), SorService(self))
        self.registry = Registry.load(self.transport)
        self.vault = Vault(self.store)
        self.proxy = PiiProxy(lambda: self.registry.pack("dpdp", self.clock.today()), lambda: self.registry.prohibited_criteria())
        self.routing = RoutingConfig(config.CONFIG_DIR / "routing.yaml")
        self.router = Router(self.store, self.clock, self.audit, self.routing)
        self.pdp = PolicyDecisionPoint(lambda: self.registry, self.vault, self.audit, self.clock.today)
        self.killswitch = KillSwitch(self.store, self.clock, self.audit)
        self.breaker = ConnectorBreaker(self.store, self.clock, self.audit)
        self.executor = GovernedExecutor(self.store, self.clock, self.audit, lambda: self.registry, self.pdp, self.killswitch, self.breaker)
        self.queue = HumanQueue(self.store, self.clock, self.audit, lambda: self.registry.reserved)
        self.devils_advocate = DevilsAdvocate(self.store, self.clock, self.audit, lambda: self.registry)
        self.sor = SystemOfRecord(self.store, self.clock, self.audit, self.vault, lambda: self.registry.pack("dpdp", self.clock.today()))
        self.dpdp = Dpdp(self.store, self.clock, self.audit, self.vault, self.sor, lambda: self.registry.pack("dpdp", self.clock.today()))
        self.orchestrator = Orchestrator(self)
        self._users = self._load_users()
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()

    # ── principals ────────────────────────────────────────────────────────────

    def _load_users(self) -> dict[str, dict[str, Any]]:
        path = config.DATA_DIR / "seed" / "users.yaml"
        if not path.exists():
            return {}
        return {u["id"]: u for u in yaml.safe_load(path.read_text())["users"]}

    def users(self) -> list[dict[str, Any]]:
        return list(self._users.values())

    def principal(self, user_id: str) -> Principal:
        user = self._users.get(user_id)
        if user is None:
            raise KeyError(f"unknown user {user_id}")
        return Principal(id=user["id"], kind="human", name=user["name"], roles=list(user.get("roles") or []),
                         org_units=list(user.get("org_units") or []))

    # ── reload (hot-swap packs and workflows, no restart) ─────────────────────

    def reload(self) -> dict[str, Any]:
        candidate = Registry.load(self.transport, strict=False)
        if candidate.problems:
            return {"ok": False, "problems": [p.__dict__ for p in candidate.problems]}
        self.registry = candidate
        self.audit.append(AuditEntry(actor="kernel", action="registry.reload", kind="system", outcome="ok",
                                     detail=candidate.summary()))
        return {"ok": True, "summary": candidate.summary()}

    # ── human decisions ───────────────────────────────────────────────────────

    def decide(self, item_id: str, user_id: str, decision: str, *, context_hash: str, note: str = "",
               values: dict[str, Any] | None = None, channel: str = "web") -> dict[str, Any]:
        approver = self.principal(user_id)
        item = self.queue.get(item_id)
        subject = None
        if item.get("run_id"):
            subject = self.orchestrator.run(item["run_id"])["subject"]
        decided = self.queue.decide(item_id, approver, decision, context_hash_seen=context_hash, note=note,
                                    values=values, channel=channel, subject=subject)
        self.orchestrator.on_decision(decided)
        return decided

    # ── Devil's Advocate model residue ───────────────────────────────────────────────

    def devils_advocate_model_review(self, run: dict[str, Any], step: Any, agent: Principal):
        spec = self.registry.skills.get("devils_advocate.review")
        if spec is None:
            return None

        def review(plan: dict[str, Any], budget_left: float) -> tuple[list[Objection], float]:
            source = {f"plan.{k}": v for k, v in plan.items()}
            minimised = self.proxy.minimise(source, spec.inputs, None)
            ctx = CallContext(run_id=run["id"], step_id=step.id, actor="devils_advocate", on_behalf_of=agent.label,
                              budget_remaining_inr=budget_left, max_tier=1, source_record=source)
            try:
                result = self.router.complete(spec, minimised, ctx)
            except Exception as exc:  # noqa: BLE001 - a provider outage degrades Devil's Advocate to rules-only
                self.audit.append(AuditEntry(actor="devils_advocate", action="model.devils_advocate.review", kind="model", outcome="failed",
                                             run_id=run["id"], step_id=step.id,
                                             detail={"error": repr(exc), "degraded_to": "deterministic checks only"}))
                return [], 0.0
            objections = []
            for o in (result.output or {}).get("objections", []) if not result.needs_human else []:
                objections.append(Objection(o.get("class", "reserved_leakage"), o.get("severity", "medium"),
                                            o.get("claim", ""), o.get("evidence") or [], o.get("suggested_action"), layer="model"))
            return objections, result.inr

        return review

    # ── circuit breaker on escalation rate ────────────────────────────────────

    def check_workflow_breaker(self, workflow: str) -> None:
        try:
            pack = self.registry.pack("circuit_breakers", self.clock.today())
        except KeyError:
            return
        window = int(pack.tables.get("window", {}).get("runs", 10))
        runs = self.store.query("SELECT id FROM workflow_runs WHERE workflow=? ORDER BY created_at DESC LIMIT ?", (workflow, window))
        if not runs:
            return
        ids = [r["id"] for r in runs]
        marks = ",".join("?" for _ in ids)
        escalated = self.store.one(
            f"SELECT COUNT(DISTINCT run_id) AS n FROM human_queue WHERE run_id IN ({marks}) "
            "AND kind IN ('low_confidence','failure','refused','policy_violation','schema','objection')", ids)["n"]
        decision = pack.evaluate({"workflow": workflow, "runs": len(ids), "escalated_runs": escalated})
        if decision.ok and decision.outputs.get("trip") and not self.killswitch.blocking(workflow=workflow):
            self.killswitch.set("workflow", workflow, True, "kernel:circuit_breaker",
                                f"escalation rate {escalated}/{len(ids)} over the last {len(ids)} runs crossed "
                                f"{decision.outputs.get('threshold')} ({pack.ref} {', '.join(decision.rule_ids)})")

    # ── the reserved-decision drill (§16.10) ──────────────────────────────────

    def reserved_drill(self, on_behalf_of: str) -> list[dict[str, Any]]:
        """An agent deliberately attempts every reserved action and may_never verb.
        The kernel must refuse each one with an audit entry."""
        human = self.principal(on_behalf_of)
        agent = Principal(id="agent:drill@v1", kind="agent", name="drill agent", on_behalf_of=human)
        attempts = list(self.registry.reserved.entries.keys())
        attempts += [f"drill.{verb}" for verb in self.registry.reserved.may_never]
        attempts += list(self.registry.reserved.route_only.keys())
        results = []
        for action in attempts:
            res = self.executor.submit(ProposedAction(action=action, args={"drill": True}, idem_key=f"drill:{action}",
                                                      workflow="drill", skill="drill"), agent, None)
            results.append({"action": action, "outcome": res.outcome, "status": res.status, "reason": res.reason,
                            "audit_seq": res.audit_seq})
        return results

    # ── background worker ─────────────────────────────────────────────────────

    def start_worker(self, interval_s: float = 0.5) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    self.orchestrator.tick()
                except Exception as exc:  # noqa: BLE001
                    self.audit.append(AuditEntry(actor="kernel", action="worker.error", kind="system", outcome="failed",
                                                 detail={"error": repr(exc)}))
                time.sleep(interval_s)

        self._worker = threading.Thread(target=loop, name="setu-worker", daemon=True)
        self._worker.start()

    def stop_worker(self) -> None:
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=5)
