"""The governed executor: the only code path that touches the outside world.

For one proposed action it runs, in order:

    kill switch → authorize (reserved · RBAC ∩ capability ∩ scope · purpose)
      → outbox (intent committed before the call) → dispatch through the
      connector breaker → post-state verification by read-back → audit.

Retries reuse the **same** idempotency key. Before any retry the executor reads
back by that key, so a call that timed out *after* committing is recognised as
done instead of being sent again. A ``200`` is never taken as evidence: success
is "read-back finds exactly one record for this key".
"""

from __future__ import annotations

from typing import Any, Callable

from core.audit import AuditChain, AuditEntry
from core.clock import Clock
from core.connectors_sdk import TransportError
from core.db import Store, dumps, loads
from core.killswitch import ConnectorBreaker, KillSwitch
from core.pdp import PolicyDecisionPoint
from core.registry import Registry
from core.types import ActionResult, Principal, ProposedAction

MAX_ATTEMPTS = 8


class GovernedExecutor:
    def __init__(self, store: Store, clock: Clock, audit: AuditChain, registry: Callable[[], Registry],
                 pdp: PolicyDecisionPoint, killswitch: KillSwitch, breaker: ConnectorBreaker):
        self.store = store
        self.clock = clock
        self.audit = audit
        self._registry = registry
        self.pdp = pdp
        self.killswitch = killswitch
        self.breaker = breaker

    @property
    def registry(self) -> Registry:
        return self._registry()

    def submit(self, proposal: ProposedAction, principal: Principal, subject: dict[str, Any] | None) -> ActionResult:
        reg = self.registry
        connector = reg.connectors.get(proposal.connector or "")
        manifest = connector.manifest if connector else None
        base = dict(actor=principal.label, run_id=proposal.run_id, step_id=proposal.step_id,
                    on_behalf_of=principal.on_behalf_of.label if principal.on_behalf_of else None)

        # 0. Kill switch.
        switch = self.killswitch.blocking(workflow=proposal.workflow, skill=proposal.skill, connector=proposal.connector)
        if switch:
            return ActionResult("paused", 423, f"kill switch engaged: {switch['scope']}:{switch['target']} ({switch.get('reason') or 'no reason'})")

        # 1–2. Reserved check, RBAC triple intersection, purpose limitation.
        authz = self.pdp.authorize(principal, proposal.action, manifest=manifest, connector_action=proposal.connector_action,
                                   subject=subject, args=proposal.args)
        if not authz.allowed:
            seq = self.audit.append(AuditEntry(
                **base, action=proposal.action, kind="reserved" if authz.outcome in ("refuse", "route_only") and "RESERVED" in authz.reason else "policy",
                outcome="refused", inputs={"args": _redact(proposal.args), "idempotency_key": proposal.idem_key},
                policy_versions=authz.policy_versions, rule_ids=authz.rule_ids,
                detail={"status": authz.status, "reason": authz.reason},
            ))
            return ActionResult("refused", authz.status, authz.reason, None, authz.rule_ids, authz.policy_versions, seq)

        if connector is None or proposal.connector_action is None:
            return ActionResult("refused", 400, f"no connector for {proposal.action}")
        spec = manifest.actions.get(proposal.connector_action) if manifest else None
        if spec is None:
            return ActionResult("refused", 400, f"{proposal.connector} has no action {proposal.connector_action}")
        if spec.side_effect and not proposal.idem_key:
            # Invariant 4 at runtime as well as load time.
            return ActionResult("refused", 400, "side-effecting action without an idempotency key")
        key = proposal.idem_key or f"read:{proposal.action}"

        # 3. Outbox: commit the intent before touching the outside world.
        row = self.store.one("SELECT * FROM outbox WHERE idem_key=?", (key,))
        if row and row["status"] == "done":
            seq = self.audit.append(AuditEntry(
                **base, action=proposal.action, kind="connector", outcome="deduplicated",
                inputs={"idempotency_key": key}, policy_versions=authz.policy_versions,
                detail={"reason": "outbox already holds a verified result for this key", "result": loads(row["result"], {})},
            ))
            return ActionResult("deduplicated", 200, "already done under this idempotency key", loads(row["result"], {}),
                                authz.rule_ids, authz.policy_versions, seq)
        if row and row["status"] == "failed":
            return ActionResult("failed", 502, row["last_error"] or "failed")
        now = self.clock.now_iso()
        if row is None:
            with self.store.tx() as conn:
                conn.execute(
                    "INSERT INTO outbox (idem_key, run_id, step_id, connector, action, payload, status, attempts, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (key, proposal.run_id, proposal.step_id, proposal.connector, proposal.connector_action,
                     dumps(proposal.args), "pending", 0, now, now),
                )
            attempts = 0
        else:
            attempts = int(row["attempts"])

        # 4. Breaker: a flapping system does not take the platform down; the intent waits.
        if not self.breaker.allows(connector.name):
            return ActionResult("waiting", 503, f"circuit breaker open for {connector.name}; intent held in the outbox")

        # A previous attempt may have landed (timeout after commit). Read back first.
        if attempts > 0:
            landed = connector.read_back(proposal.connector_action, proposal.args, key)
            if len(landed) == 1:
                return self._complete(proposal, base, authz, key, landed[0], attempts, recovered=True)
            if len(landed) > 1:
                return self._duplicate(proposal, base, key, landed)

        attempts += 1
        try:
            result = connector.execute(proposal.connector_action, proposal.args, key)
        except TransportError as exc:
            opened = self.breaker.record_failure(connector.name)
            if exc.timeout:
                landed = connector.read_back(proposal.connector_action, proposal.args, key)
                if len(landed) == 1:
                    self.breaker.record_success(connector.name)
                    return self._complete(proposal, base, authz, key, landed[0], attempts, recovered=True)
            terminal = attempts >= MAX_ATTEMPTS or exc.status in (400, 404, 409)
            self._outbox_update(key, "failed" if terminal else "pending", attempts, last_error=str(exc))
            seq = self.audit.append(AuditEntry(
                **base, action=proposal.action, kind="connector", outcome="failed" if terminal else "retried",
                inputs={"idempotency_key": key, "attempt": attempts}, policy_versions=authz.policy_versions,
                detail={"error": str(exc), "status": exc.status, "timeout": exc.timeout, "breaker_opened": opened,
                        "next": "route to human with context" if terminal else "retry with the same key"},
            ))
            if terminal:
                return ActionResult("failed", exc.status, str(exc), None, authz.rule_ids, authz.policy_versions, seq)
            return ActionResult("retrying", exc.status, f"attempt {attempts} failed: {exc}", None, authz.rule_ids, authz.policy_versions, seq)

        self.breaker.record_success(connector.name)
        # 5. Post-state verification: read back by key; expect exactly one record.
        if not spec.verify:
            return self._complete(proposal, base, authz, key, {"data": result}, attempts)
        landed = connector.read_back(proposal.connector_action, proposal.args, key)
        if len(landed) == 1:
            return self._complete(proposal, base, authz, key, landed[0], attempts, response=result)
        if len(landed) > 1:
            return self._duplicate(proposal, base, key, landed)
        self._outbox_update(key, "pending", attempts, last_error="200 returned but read-back found nothing")
        seq = self.audit.append(AuditEntry(
            **base, action=proposal.action, kind="connector", outcome="verify_failed",
            inputs={"idempotency_key": key, "attempt": attempts}, policy_versions=authz.policy_versions,
            detail={"response": result, "reason": "system acknowledged but read-back found no record — a 200 is not evidence; retrying with the same key"},
        ))
        return ActionResult("retrying", 202, "acknowledged but not verified; will retry with the same key", None,
                            authz.rule_ids, authz.policy_versions, seq)

    def compensate(self, proposal: ProposedAction, principal: Principal, original_key: str) -> ActionResult:
        """Run a step's declared compensation with a derived, stable key."""
        proposal.idem_key = f"{original_key}:compensate"
        return self.submit(proposal, principal, None)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _complete(self, proposal: ProposedAction, base: dict[str, Any], authz: Any, key: str, record: dict[str, Any],
                  attempts: int, recovered: bool = False, response: dict[str, Any] | None = None) -> ActionResult:
        result = {"record_id": record.get("id"), "status": record.get("status"), "data": record.get("data"), "response": response}
        self._outbox_update(key, "done", attempts, result=result)
        seq = self.audit.append(AuditEntry(
            **base, action=proposal.action, kind="connector", outcome="ok",
            inputs={"args": _redact(proposal.args), "idempotency_key": key, "attempts": attempts},
            policy_versions=authz.policy_versions, rule_ids=authz.rule_ids,
            detail={"verified": "read-back found exactly one record for this key", "record_id": record.get("id"),
                    "recovered_after_timeout": recovered},
        ))
        return ActionResult("executed", 200, "executed and verified", result, authz.rule_ids, authz.policy_versions, seq)

    def _duplicate(self, proposal: ProposedAction, base: dict[str, Any], key: str, landed: list[dict[str, Any]]) -> ActionResult:
        self._outbox_update(key, "failed", 0, last_error=f"{len(landed)} records under one key")
        seq = self.audit.append(AuditEntry(
            **base, action=proposal.action, kind="connector", outcome="duplicate_detected",
            inputs={"idempotency_key": key}, detail={"records": [r.get("id") for r in landed]},
        ))
        return ActionResult("failed", 409, f"post-state check found {len(landed)} records for one key", None, [], [], seq)

    def _outbox_update(self, key: str, status: str, attempts: int, *, result: Any = None, last_error: str | None = None) -> None:
        with self.store.tx() as conn:
            conn.execute(
                "UPDATE outbox SET status=?, attempts=MAX(attempts, ?), result=COALESCE(?, result), last_error=?, updated_at=? WHERE idem_key=?",
                (status, attempts, dumps(result) if result is not None else None, last_error, self.clock.now_iso(), key),
            )


def _redact(args: dict[str, Any]) -> dict[str, Any]:
    """Audit entries keep tokens, never raw PII. Args only ever carry tokens, but be defensive."""
    return {k: ("«redacted»" if k.endswith(("_raw", "pan", "bank_account", "aadhaar")) else v) for k, v in args.items()}
