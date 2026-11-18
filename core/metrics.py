"""Dashboard metrics, computed from the same database as the HR record and the
audit chain — so a number cannot drift from what actually happened, and every
tile can be drilled to the rows that produced it.

Only measured values come from here. Projections multiply measured ₹/run by
the volume assumptions in ``config/costs.yaml`` and are labelled as such.
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING, Any

import yaml

from core import config
from core.clock import parse_ts
from core.db import loads

if TYPE_CHECKING:
    from core.kernel import Kernel

ESCALATION_KINDS = ("low_confidence", "failure", "refused", "policy_violation", "schema", "objection")


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def overview(k: "Kernel") -> dict[str, Any]:
    costs_cfg = yaml.safe_load((config.CONFIG_DIR / "costs.yaml").read_text())
    workflows = {}
    runs = k.store.query("SELECT * FROM workflow_runs")
    steps = k.store.query("SELECT s.*, r.workflow FROM step_runs s JOIN workflow_runs r ON r.id=s.run_id")
    queue = k.store.query("SELECT run_id, kind FROM human_queue")
    escalated_runs = {q["run_id"] for q in queue if q["kind"] in ESCALATION_KINDS and q["run_id"]}

    for wf in k.registry.latest_workflows():
        wr = [r for r in runs if r["workflow"] == wf.name]
        completed = [r for r in wr if r["status"] == "completed"]
        ws = [s for s in steps if s["workflow"] == wf.name and s["status"] == "done"]
        costs = [r["cost_inr"] for r in completed]
        cycles = [(parse_ts(r["closed_at"]) - parse_ts(r["created_at"])).total_seconds() for r in completed if r["closed_at"]]
        touched = [s for s in ws if s["human_touch"]]
        tiers = {t: sum(1 for s in ws if s["tier"] == t) for t in (0, 1, 2, 3)}
        workflows[wf.name] = {
            "workflow": wf.ref,
            "description": wf.description,
            "runs": len(wr),
            "completed": len(completed),
            "in_flight": sum(1 for r in wr if r["status"] in ("running", "waiting", "paused")),
            "cost_p50": _pct(costs, 0.5),
            "cost_p95": _pct(costs, 0.95),
            "cost_mean": statistics.fmean(costs) if costs else None,
            "budget_inr_per_run": wf.budget_inr_per_run,
            "automation_rate": (1 - len(touched) / len(ws)) if ws else None,
            "steps_done": len(ws),
            "steps_human": len(touched),
            "target_automation_rate": wf.target_automation_rate,
            "escalation_rate": (sum(1 for r in wr if r["id"] in escalated_runs) / len(wr)) if wr else None,
            "cycle_p50_s": _pct(cycles, 0.5),
            "cycle_p95_s": _pct(cycles, 0.95),
            "tier_mix": tiers,
        }

    refused = k.store.query("SELECT action, rule_ids, detail FROM audit WHERE outcome='refused'")
    governed = k.store.one("SELECT COUNT(*) AS n FROM audit WHERE kind IN ('connector','reserved','policy') AND action NOT LIKE 'policy.evaluate%'")["n"]
    by_reason: dict[str, int] = {}
    for r in refused:
        reason = loads(r["detail"], {}).get("reason", r["action"])
        label = "RESERVED" if "RESERVED" in reason else reason.split(":")[0][:60]
        by_reason[label] = by_reason.get(label, 0) + 1

    objections = k.store.query("SELECT * FROM objections")
    resolved = [o for o in objections if o["upheld"] is not None]
    upheld = [o for o in resolved if o["upheld"]]
    pv_cost = k.store.one("SELECT COALESCE(SUM(inr),0) AS c FROM audit WHERE action LIKE 'model.prativaad%'")["c"]
    total_cost = k.store.one("SELECT COALESCE(SUM(cost_inr),0) AS c FROM workflow_runs")["c"]
    by_class: dict[str, int] = {}
    for o in objections:
        by_class[o["class"]] = by_class.get(o["class"], 0) + 1

    model_calls = k.store.query("SELECT tier, COUNT(*) AS n, SUM(inr) AS inr, SUM(tokens_in) AS tin, SUM(tokens_out) AS tout FROM model_calls GROUP BY tier")
    escalations = k.store.one("SELECT COUNT(*) AS n FROM model_calls WHERE escalation_reason LIKE 'measured trigger%' OR escalation_reason LIKE 'schema%'")["n"]
    receipts = k.store.query("SELECT r.action, r.decided_at, q.created_at FROM receipts r JOIN human_queue q ON q.id=r.queue_id")
    tta = [(parse_ts(r["decided_at"]) - parse_ts(r["created_at"])).total_seconds() for r in receipts]

    # Projection = measured ₹/run (p50, completed runs) × ASSUMED volumes + ASSUMED hosting.
    volumes = costs_cfg["volumes_per_month"]
    hosting = float(costs_cfg["hosting"]["monthly_inr"])
    total_runs = sum(volumes.values())
    projection_rows = []
    for name, vol in volumes.items():
        measured = workflows.get(name, {}).get("cost_p50")
        hosting_share = hosting * vol / total_runs
        projection_rows.append({
            "workflow": name, "runs_per_month_assumed": vol, "measured_inr_per_run_p50": measured,
            "inference_inr_per_month": None if measured is None else round(measured * vol, 2),
            "hosting_inr_per_month": round(hosting_share, 2),
            "total_inr_per_month": None if measured is None else round(measured * vol + hosting_share, 2),
        })

    return {
        "workflows": workflows,
        "governance": {
            "refusals": len(refused), "governed_actions": governed,
            "policy_block_rate": (len(refused) / governed) if governed else None,
            "refusals_by_reason": dict(sorted(by_reason.items(), key=lambda kv: -kv[1])),
            "reserved_decisions": len(receipts),
            "time_to_approve_p50_s": _pct(tta, 0.5),
            "audit": k.audit.verify(),
        },
        "prativaad": {
            "objections": len(objections), "by_class": by_class,
            "by_layer": {layer: sum(1 for o in objections if o["layer"] == layer) for layer in ("rules", "model")},
            "resolved": len(resolved), "upheld": len(upheld),
            "precision": (len(upheld) / len(resolved)) if resolved else None,
            "cost_inr": pv_cost, "overhead_share": (pv_cost / total_cost) if total_cost else None,
        },
        "models": {
            "by_tier": {f"tier{m['tier']}": {"calls": m["n"], "inr": m["inr"], "tokens_in": m["tin"], "tokens_out": m["tout"]} for m in model_calls},
            "escalations": escalations,
            "profile": k.routing.active_profile,
        },
        "projection": {
            "rows": projection_rows,
            "hosting_inr_per_month_assumed": hosting,
            "assumptions": "Volumes and hosting are ASSUMPTIONS from config/costs.yaml (placeholder until TBO shares figures); ₹/run is measured p50 of completed runs on the synthetic dataset with the active model profile's declared rate card.",
            "total_inr_per_month": round(sum(r["total_inr_per_month"] or 0 for r in projection_rows), 2),
        },
        "human_minutes": costs_cfg.get("human_minutes"),
        "clock": k.clock.now_iso(),
    }


def drill(k: "Kernel", tile: str, workflow: str | None = None) -> list[dict[str, Any]]:
    """The rows behind a tile. Clicking '79%' lands on the 21% and why."""
    where, params = "", []
    if workflow:
        where = " AND r.workflow=?"
        params.append(workflow)
    if tile == "automation":
        return k.store.query(
            "SELECT s.run_id, s.step_id, s.note, s.status, r.workflow, r.subject FROM step_runs s JOIN workflow_runs r ON r.id=s.run_id "
            f"WHERE s.human_touch=1{where} ORDER BY s.finished_at DESC LIMIT 200", params)
    if tile == "escalation":
        return k.store.query(
            "SELECT q.id, q.run_id, q.kind, q.title, q.status, r.workflow FROM human_queue q JOIN workflow_runs r ON r.id=q.run_id "
            f"WHERE q.kind IN ({','.join('?' for _ in ESCALATION_KINDS)}){where} ORDER BY q.created_at DESC LIMIT 200",
            list(ESCALATION_KINDS) + params)
    if tile == "cost":
        return k.store.query(
            "SELECT s.run_id, s.step_id, s.tier, s.cost_inr, r.workflow FROM step_runs s JOIN workflow_runs r ON r.id=s.run_id "
            f"WHERE s.cost_inr > 0{where} ORDER BY s.cost_inr DESC LIMIT 200", params)
    if tile == "refusals":
        rows = k.store.query("SELECT seq, at, actor, action, run_id, detail FROM audit WHERE outcome='refused' ORDER BY seq DESC LIMIT 200")
        for r in rows:
            r["detail"] = loads(r["detail"], {})
        return rows
    if tile == "objections":
        rows = k.store.query("SELECT * FROM objections ORDER BY at DESC LIMIT 200")
        for r in rows:
            r["evidence"] = loads(r["evidence"], [])
        return rows
    raise KeyError(tile)
