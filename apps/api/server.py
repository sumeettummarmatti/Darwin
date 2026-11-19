"""HTTP API for the web console, the chat surface and the mock systems.

A thin layer: every endpoint delegates to the kernel. The console is an
*experience plane* client — it cannot do anything the kernel would refuse.

    uvicorn apps.api.server:app --port 8000
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any

import yaml
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from core import config, intents, metrics
from core.connectors_sdk import TransportError
from core.db import loads
from core.kernel import Kernel
from core.queue import QueueError
from core.rules.packs import PackLoadError, parse_pack
from core.reserved import RegistryLoadError, parse_registry

WEB_DIST = config.ROOT / "apps" / "web" / "dist"
SAFE_NAME = re.compile(r"[a-z0-9_]+")


class Holder:
    """Holds the live kernel so a demo reset can swap it without restarting the server."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.kernel: Kernel | None = None
        self.tamper_backup: dict[str, Any] | None = None

    def get(self) -> Kernel:
        with self.lock:
            if self.kernel is None:
                fresh = not config.db_path().exists()
                self.kernel = Kernel()
                if fresh:
                    from tools.seed import seed
                    seed(self.kernel)
                if os.environ.get("SETU_WORKER", "1") == "1":
                    self.kernel.start_worker()
            return self.kernel

    def reset(self) -> dict[str, Any]:
        with self.lock:
            if self.kernel:
                self.kernel.stop_worker()
                self.kernel.store.close()
            from tools.seed import reset_and_seed
            summary = reset_and_seed()
            self.kernel = Kernel()
            if os.environ.get("SETU_WORKER", "1") == "1":
                self.kernel.start_worker()
            self.tamper_backup = None
            return summary


holder = Holder()
app = FastAPI(title="SETU", version="0.2.0", description="Agent-first HR platform with a governance kernel.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def K() -> Kernel:
    return holder.get()


@app.exception_handler(QueueError)
async def _queue_error(_: Request, exc: QueueError) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=exc.status)


@app.exception_handler(KeyError)
async def _key_error(_: Request, exc: KeyError) -> JSONResponse:
    return JSONResponse({"error": f"not found: {exc}"}, status_code=404)


# ── bootstrap ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict[str, Any]:
    k = K()
    return {"ok": True, "clock": k.clock.now_iso(), "audit": k.audit.verify()["ok"]}


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    k = K()
    return {
        "users": k.users(),
        "registry": k.registry.summary(),
        "workflows": [_workflow_view(k, wf) for wf in k.registry.latest_workflows()],
        "clock": k.clock.now_iso(),
        "profile": k.routing.active_profile,
        "profiles": list(k.routing.profiles().keys()),
        "groq_ready": bool(os.environ.get("GROQ_API_KEY")) and k.routing.key_status["state"] != "rejected",
        "kill_switches": k.killswitch.active(),
    }


def _workflow_view(k: Kernel, wf: Any) -> dict[str, Any]:
    return {
        "name": wf.name, "version": wf.version, "ref": wf.ref, "description": wf.description, "service_line": wf.service_line,
        "budget_inr_per_run": wf.budget_inr_per_run, "target_automation_rate": wf.target_automation_rate,
        "inputs": wf.inputs, "triggers": wf.triggers, "source_path": str(Path(wf.source_path).relative_to(config.ROOT)),
        "steps": [{"id": s.id, "title": s.title or s.id, "kind": s.kind, "needs": s.needs, "skill": s.skill,
                   "connector": s.connector, "action": s.action or s.reserved_action, "deterministic": s.deterministic,
                   "when": s.when.source if s.when else None, "schedule_at": s.schedule_at,
                   "model": bool(s.skill and k.registry.skills[s.skill].kind == "model")} for s in wf.steps],
        "lint": k.prativaad.gate_c(wf),
    }


# ── runs ──────────────────────────────────────────────────────────────────────

@app.get("/api/runs")
def list_runs(workflow: str | None = None, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    k = K()
    sql, params, where = "SELECT * FROM workflow_runs", [], []
    if workflow:
        where.append("workflow=?")
        params.append(workflow)
    if status:
        where.append("status=?")
        params.append(status)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = k.store.query(sql, params)
    counts = {r["run_id"]: r for r in k.store.query(
        "SELECT run_id, COUNT(*) AS total, SUM(status='done') AS done, SUM(status='skipped') AS skipped, "
        "SUM(status IN ('awaiting_human','refused','failed','paused')) AS blocked, SUM(human_touch) AS human FROM step_runs GROUP BY run_id")}
    names = {p["id"]: p["display_name"] for p in k.store.query("SELECT id, display_name FROM people")}
    for r in rows:
        r["inputs"] = loads(r["inputs"], {})
        r["facts"] = loads(r["facts"], {})
        r["subject_name"] = names.get(r["subject"])
        c = counts.get(r["id"], {})
        r["progress"] = {k2: c.get(k2) or 0 for k2 in ("total", "done", "skipped", "blocked", "human")}
    return rows


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    k = K()
    run = k.orchestrator.run(run_id)
    wf = k.registry.workflow(run["workflow"], run["version"])
    steps = k.orchestrator.steps(run_id)
    defs = {s["id"]: s for s in _workflow_view(k, wf)["steps"]}
    subject = k.sor.person(run["subject"]) if run["subject"] else None
    return {
        "run": run,
        "subject": {"id": subject["id"], "display_name": subject["display_name"], **{x: subject["attrs"].get(x) for x in ("grade", "role_title", "org_unit", "location")}} if subject else None,
        "steps": [{**defs[sid], **s} for sid, s in steps.items()],
        "audit": k.audit.for_run(run_id),
        "queue": [i for i in k.queue.list(None) if i["run_id"] == run_id],
        "model_calls": k.store.query("SELECT id, step_id, skill, tier, model, tokens_in, tokens_out, inr, escalation_reason, at FROM model_calls WHERE run_id=? ORDER BY at", (run_id,)),
        "objections": [{**o, "evidence": loads(o["evidence"], [])} for o in k.store.query("SELECT * FROM objections WHERE run_id=? ORDER BY at", (run_id,))],
        "workflow": {"ref": wf.ref, "budget_inr_per_run": wf.budget_inr_per_run},
    }


@app.post("/api/runs")
def start_run(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    k = K()
    principal = k.principal(body.get("user_id", "USR-101"))
    subject = body.get("subject_id")
    inputs = {"person_id": subject, **(body.get("inputs") or {})}
    run_id = k.orchestrator.start(body["workflow"], subject_id=subject, inputs=inputs, principal=principal,
                                  channel=body.get("channel", "web"))
    return {"run_id": run_id, "run": k.orchestrator.run(run_id)}


@app.post("/api/runs/{run_id}/compensate")
def compensate(run_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return {"results": K().orchestrator.compensate(run_id, reason=body.get("reason", "requested from console"))}


# ── human queue and receipts ──────────────────────────────────────────────────

@app.get("/api/queue")
def queue(status: str | None = "open", user_id: str | None = None) -> list[dict[str, Any]]:
    k = K()
    viewer_roles = set(k.principal(user_id).roles) if user_id else set()
    items = k.queue.list(status or None)
    for item in items:
        visible_to = set(item["packet"].get("visible_to") or [])
        if "matter_text" in item["packet"] and not (visible_to & viewer_roles):
            # Route-only matters: only the named role may read the words.
            item["packet"]["matter_text"] = "«withheld — visible only to " + ", ".join(sorted(visible_to)) + "»"
            item["redacted"] = True
        item["can_decide"] = bool(set(item["approver_roles"]) & viewer_roles) if user_id else None
    return items


@app.post("/api/queue/{item_id}/decide")
def decide(item_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    k = K()
    return k.decide(item_id, body["user_id"], body["decision"], context_hash=body["context_hash"], note=body.get("note", ""),
                    values=body.get("values") or {}, channel=body.get("channel", "web"))


@app.post("/api/queue/{item_id}/agent-attempt")
def agent_attempt(item_id: str) -> dict[str, Any]:
    """Demo: an agent tries to decide a queue item. The kernel must refuse with 403."""
    from core.types import Principal

    k = K()
    item = k.queue.get(item_id)
    agent = Principal(id="agent:exit@v1", kind="agent", on_behalf_of=k.principal("USR-101"))
    try:
        k.queue.decide(item_id, agent, "approve", context_hash_seen=item["context_hash"])
    except QueueError as exc:
        return {"refused": True, "status": exc.status, "reason": str(exc)}
    return {"refused": False}


@app.get("/api/receipts")
def receipts() -> list[dict[str, Any]]:
    return K().queue.receipts()


@app.get("/api/receipts/{receipt_id}/verify")
def verify_receipt(receipt_id: str) -> dict[str, Any]:
    return K().queue.verify_receipt(receipt_id)


# ── audit ─────────────────────────────────────────────────────────────────────

@app.get("/api/audit")
def audit(limit: int = 200, kind: str | None = None, outcome: str | None = None) -> list[dict[str, Any]]:
    return K().audit.recent(limit, kind, outcome)


@app.get("/api/audit/verify")
def audit_verify() -> dict[str, Any]:
    return K().audit.verify()


@app.post("/api/audit/tamper")
def audit_tamper() -> dict[str, Any]:
    """Demo: edit one historic row directly in the database, as an attacker with DB access would."""
    k = K()
    row = k.store.one("SELECT seq, outcome FROM audit WHERE kind='human' OR kind='reserved' ORDER BY seq LIMIT 1") or \
        k.store.one("SELECT seq, outcome FROM audit ORDER BY seq LIMIT 1 OFFSET 3")
    if not row:
        raise HTTPException(400, "no audit rows yet")
    holder.tamper_backup = row
    with k.store.tx() as conn:
        conn.execute("UPDATE audit SET outcome=? WHERE seq=?", ("approve" if row["outcome"] != "approve" else "reject", row["seq"]))
    return {"tampered_seq": row["seq"], "verify": k.audit.verify()}


@app.post("/api/audit/repair")
def audit_repair() -> dict[str, Any]:
    k = K()
    if holder.tamper_backup:
        with k.store.tx() as conn:
            conn.execute("UPDATE audit SET outcome=? WHERE seq=?", (holder.tamper_backup["outcome"], holder.tamper_backup["seq"]))
        holder.tamper_backup = None
    return {"verify": k.audit.verify()}


# ── people, DPDP ──────────────────────────────────────────────────────────────

@app.get("/api/people")
def people(kind: str | None = None) -> list[dict[str, Any]]:
    return K().sor.people(kind)


@app.get("/api/people/{person_id}")
def person(person_id: str) -> dict[str, Any]:
    k = K()
    p = k.sor.person(person_id)
    if p is None:
        raise HTTPException(404, "no such person")
    return {**p, "pii_fields": k.vault.fields_for(person_id), "events": k.sor.events(person_id),
            "spells": k.sor.spells(person_id), "consents": k.dpdp.consents(person_id)}


@app.get("/api/dpdp/access/{person_id}")
def dsr_access(person_id: str, user_id: str = "USR-106") -> dict[str, Any]:
    return K().dpdp.access(person_id, f"human:{user_id}")


@app.post("/api/dpdp/erase")
def dsr_erase(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return K().dpdp.erase(body["person_id"], body["field"], f"human:{body.get('user_id', 'USR-106')}")


@app.post("/api/dpdp/sweep")
def dpdp_sweep() -> dict[str, Any]:
    return K().dpdp.sweep()


@app.get("/api/dpdp/schedule")
def dpdp_schedule() -> list[dict[str, Any]]:
    return K().dpdp.schedule()


@app.post("/api/dpdp/cross-purpose")
def cross_purpose(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Demo: read a payroll-only field for an onboarding-logistics purpose. Refused and audited."""
    from core.audit import AuditEntry
    from core.pii import PurposeViolation

    k = K()
    person_id, field_name, purpose = body.get("person_id", "EMP-4821"), body.get("field", "bank_account"), body.get("purpose", "onboarding_logistics")
    try:
        k.vault.read(person_id, field_name, purpose)
        outcome, reason = "ok", "permitted"
    except PurposeViolation as exc:
        outcome, reason = "refused", str(exc)
    seq = k.audit.append(AuditEntry(actor="agent:onboarding@v3", action=f"vault.read.{field_name}", kind="policy", outcome=outcome,
                                    inputs={"person": person_id, "purpose": purpose}, policy_versions=[k.registry.pack('dpdp').ref],
                                    detail={"reason": reason}))
    return {"outcome": outcome, "reason": reason, "audit_seq": seq}


# ── governance: policies, registry, workflows, kill switch, drill ─────────────

@app.get("/api/policies")
def policies() -> list[dict[str, Any]]:
    k = K()
    out = []
    for name, versions in sorted(k.registry.packs.items()):
        active = k.registry.pack(name, k.clock.today()) if any(p.effective_from.isoformat() <= k.clock.today() for p in versions) else None
        for p in sorted(versions, key=lambda v: v.version):
            tests = p.run_tests()
            out.append({"name": name, "ref": p.ref, "version": p.version, "effective_from": p.effective_from.isoformat(),
                        "active": active is not None and active.version == p.version, "owner": p.raw.get("owner"),
                        "description": p.raw.get("description") or (p.raw.get("rules") and None),
                        "rules": len(p.rules), "derive": len(p.derive), "guards": len(p.guards),
                        "tests": tests, "tests_passed": sum(t["passed"] for t in tests), "clauses": p.clauses,
                        "hash": p.content_hash, "path": str(Path(p.source_path).relative_to(config.ROOT)),
                        "has_properties": bool(p.raw.get("properties"))})
    return out


@app.get("/api/policies/{name}/source")
def policy_source(name: str, version: int | None = None) -> dict[str, Any]:
    k = K()
    pack = k.registry.pack_version(name, version) if version else k.registry.pack(name, k.clock.today())
    return {"ref": pack.ref, "path": str(Path(pack.source_path).relative_to(config.ROOT)), "yaml": Path(pack.source_path).read_text()}


@app.get("/api/policies/{name}/draft")
def policy_draft(name: str) -> dict[str, Any]:
    path = config.POLICIES_DIR / "drafts" / f"{name}.draft.yaml"
    if not path.exists():
        raise HTTPException(404, "no prepared draft")
    return {"yaml": path.read_text(), "path": str(path.relative_to(config.ROOT))}


@app.post("/api/policies/{name}/review")
def policy_review(name: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Prativaad gate B over a draft pack: tests + property-based adversarial cases + diff vs the active version."""
    k = K()
    try:
        raw = yaml.safe_load(body["yaml"])
    except yaml.YAMLError as exc:
        return {"ok": False, "load_error": f"YAML: {exc}", "findings": [], "proposed_tests": [], "changed": []}
    try:
        old = k.registry.pack(name, k.clock.today())
    except KeyError:
        old = None
    return k.prativaad.gate_b(raw, old)


@app.post("/api/policies/{name}/activate")
def policy_activate(name: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Write a new pack version and hot-reload. Refused unless tests pass and gate B is clean."""
    k = K()
    raw = yaml.safe_load(body["yaml"])
    review = k.prativaad.gate_b(raw, None)
    if not review["ok"]:
        return {"ok": False, "reason": "Prativaad gate B blocked activation", "review": review}
    try:
        pack = parse_pack(raw, "<activate>")
    except PackLoadError as exc:
        return {"ok": False, "reason": str(exc)}
    # The file name comes from the draft, so it must be a plain identifier: no path traversal.
    if not SAFE_NAME.fullmatch(pack.name) or (pack.jurisdiction and not SAFE_NAME.fullmatch(pack.jurisdiction.lower())):
        return {"ok": False, "reason": "pack and jurisdiction names must be lowercase letters, digits and underscores"}
    if pack.name != name:
        return {"ok": False, "reason": f"draft declares pack '{pack.name}' but is being activated as '{name}'"}
    suffix = f".{pack.jurisdiction.lower()}" if pack.jurisdiction else ""
    path = config.POLICIES_DIR / f"{pack.name}{suffix}.v{pack.version}.yaml"
    if path.exists():
        return {"ok": False, "reason": f"{path.name} already exists — bump the version"}
    path.write_text(body["yaml"])
    result = k.reload()
    if not result["ok"]:
        path.unlink()
    return {"ok": result["ok"], "path": str(path.relative_to(config.ROOT)), "reload": result}


@app.get("/api/reserved")
def reserved() -> dict[str, Any]:
    k = K()
    reg = k.registry.reserved
    return {"ref": reg.ref, "path": str(Path(reg.source_path).relative_to(config.ROOT)), "yaml": Path(reg.source_path).read_text(),
            "entries": [e.__dict__ for e in reg.entries.values()],
            "route_only": [{"action": a, "route_to_role": r} for a, r in reg.route_only.items()],
            "may": reg.may, "may_never": reg.may_never, "tests": reg.run_tests(),
            "reserved_facts": reg.raw.get("reserved_facts", [])}


@app.post("/api/reserved")
def reserved_update(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """HR edits the reserved list: validated (tests must pass), written as a new version, hot-reloaded. No deploy."""
    k = K()
    try:
        raw = yaml.safe_load(body["yaml"])
        candidate = parse_registry(raw, "<edit>")
    except (yaml.YAMLError, RegistryLoadError, KeyError) as exc:
        return {"ok": False, "reason": str(exc)}
    if candidate.version <= k.registry.reserved.version:
        return {"ok": False, "reason": f"version must be greater than {k.registry.reserved.version}"}
    path = config.POLICIES_DIR / f"reserved_decisions.v{candidate.version}.yaml"
    path.write_text(body["yaml"])
    result = k.reload()
    if not result["ok"]:
        path.unlink()
    return {"ok": result["ok"], "path": str(path.relative_to(config.ROOT)), "reload": result}


@app.get("/api/killswitch")
def killswitch() -> dict[str, Any]:
    k = K()
    return {"switches": k.killswitch.all(), "breakers": k.breaker.all()}


@app.post("/api/killswitch")
def killswitch_set(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    k = K()
    k.killswitch.set(body["scope"], body.get("target") or "*", bool(body["active"]), f"human:{body.get('user_id', 'USR-103')}",
                     body.get("reason", ""))
    return {"switches": k.killswitch.all()}


@app.post("/api/drill")
def drill(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    results = K().reserved_drill(body.get("user_id", "USR-103"))
    return {"results": results, "all_refused": all(r["outcome"] == "refused" for r in results)}


# ── conversational surface ────────────────────────────────────────────────────

@app.post("/api/intent")
def intent(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return intents.handle(K(), body["user_id"], body["text"], body.get("channel", "web"))


# ── models, metrics, payload viewer ───────────────────────────────────────────

@app.get("/api/model-calls")
def model_calls(run_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    k = K()
    if run_id:
        rows = k.store.query("SELECT * FROM model_calls WHERE run_id=? ORDER BY at DESC", (run_id,))
    else:
        rows = k.store.query("SELECT * FROM model_calls ORDER BY at DESC LIMIT ?", (limit,))
    for r in rows:
        for key in ("source_record", "stripped_fields", "response"):
            r[key] = loads(r[key], None)
        r["outbound_payload"] = loads(r["outbound_payload"], {})
    return rows


@app.get("/api/metrics")
def get_metrics() -> dict[str, Any]:
    return metrics.overview(K())


@app.get("/api/metrics/drill")
def get_drill(tile: str, workflow: str | None = None) -> list[dict[str, Any]]:
    return metrics.drill(K(), tile, workflow)


@app.get("/api/provider")
def provider_status() -> dict[str, Any]:
    """What the console needs to ask for (or re-ask for) a model-provider key. Never returns the key."""
    k = K()
    key = os.environ.get("GROQ_API_KEY", "")
    return {"profile": k.routing.active_profile, "profiles": list(k.routing.profiles().keys()),
            "groq": {**k.routing.key_status, "configured": bool(key), "hint": f"…{key[-4:]}" if key else None,
                     "create_url": "https://console.groq.com/keys"}}


@app.post("/api/provider/key")
def provider_key(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Validate a Groq key with the provider, then keep it in the git-ignored .env and switch to Groq."""
    from core.router.adapters import check_key

    k = K()
    key = str(body.get("key", "")).strip()
    ok, message = check_key("https://api.groq.com/openai/v1", key)
    if not ok:
        # A bad paste does not condemn the key already in use; only report it.
        if not os.environ.get("GROQ_API_KEY"):
            k.routing.key_status = {"state": "missing", "message": message}
        return {"ok": False, "message": message, "create_url": "https://console.groq.com/keys"}
    env_path = config.ROOT / ".env"
    lines = [l for l in (env_path.read_text().splitlines() if env_path.exists() else []) if not l.startswith("GROQ_API_KEY=")]
    env_path.write_text("\n".join(lines + [f"GROQ_API_KEY={key}"]) + "\n")
    os.environ["GROQ_API_KEY"] = key
    k.routing.set_profile("groq")
    k.routing.key_status = {"state": "ok", "message": "Key accepted by Groq."}
    from core.audit import AuditEntry
    k.audit.append(AuditEntry(actor=f"human:{body.get('user_id', 'USR-103')}", action="router.provider.key_set", kind="system",
                              outcome="ok", detail={"provider": "groq", "key_hint": f"…{key[-4:]}"}))
    return {"ok": True, "message": "Key accepted. Model steps now run on Groq.", "profile": "groq"}


@app.post("/api/provider")
def provider(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    k = K()
    k.routing.set_profile(body["profile"])
    from core.audit import AuditEntry
    k.audit.append(AuditEntry(actor=f"human:{body.get('user_id', 'USR-103')}", action="router.profile.switch", kind="system",
                              outcome="ok", detail={"profile": body["profile"]}))
    return {"profile": k.routing.active_profile}


# ── demo controls ─────────────────────────────────────────────────────────────

@app.post("/api/clock/advance")
def clock_advance(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    k = K()
    seconds = float(body.get("days", 0)) * 86400 + float(body.get("hours", 0)) * 3600
    now = k.clock.advance(seconds)
    k.orchestrator.tick()
    return {"clock": now.isoformat()}


@app.post("/api/clock/reset")
def clock_reset() -> dict[str, Any]:
    k = K()
    k.clock.reset()
    return {"clock": k.clock.now_iso()}


@app.get("/api/mocks/records")
def mock_records(system: str | None = None, kind: str | None = None) -> list[dict[str, Any]]:
    return K().mocks.records(system, kind)


@app.get("/api/mocks/chaos")
def mock_chaos() -> dict[str, Any]:
    k = K()
    return {"chaos": k.mocks.chaos_state(), "calls": k.mocks.call_log(60)}


@app.post("/api/mocks/chaos")
def mock_chaos_set(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    k = K()
    if body.get("mode") in (None, "clear"):
        k.mocks.clear_chaos(body.get("system"))
    else:
        k.mocks.set_chaos(body["system"], body["mode"], int(body.get("count", 1)))
    return {"chaos": k.mocks.chaos_state()}


@app.post("/api/demo/reset")
def demo_reset() -> dict[str, Any]:
    return holder.reset()


@app.post("/mocks/{system}/{op}")
def mock_http(system: str, op: str, payload: dict[str, Any] = Body(default={})) -> Any:
    """The TBO mocks over HTTP, for HttpTransport and for anyone who wants to poke them."""
    try:
        return K().mocks.handle(system, op, payload)
    except TransportError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status)


# ── the web console (built SPA) ───────────────────────────────────────────────

@app.get("/{path:path}", include_in_schema=False)
def spa(path: str) -> Any:
    if not WEB_DIST.exists():
        return JSONResponse({"message": "SETU API is running. Build the console with `make web` (apps/web)."})
    target = (WEB_DIST / path).resolve()
    if path and target.is_file() and WEB_DIST.resolve() in target.parents:
        return FileResponse(target)
    return FileResponse(WEB_DIST / "index.html", headers={"Cache-Control": "no-cache"})
