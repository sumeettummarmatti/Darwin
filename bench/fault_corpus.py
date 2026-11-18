"""Run Prativaad gate A against the planted-defect corpus and report what each layer caught.

The number this produces is the honest one: if the model layer adds nothing over
the deterministic checks, the report says so.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core import config
from core.connectors_sdk import Connector
from core.types import Principal
from core.workflows import parse_workflow

CORPUS = config.ROOT / "tests" / "fault_corpus" / "cases.yaml"


class _PlantedConnector(Connector):
    """Wraps a real connector's manifest; prior effects come from the case."""

    def __init__(self, real: Connector, prior: list[dict[str, Any]]):
        super().__init__(real.manifest, real.transport)
        self._prior = prior

    def execute(self, action, args, idem_key):  # pragma: no cover - never executed by the corpus
        raise RuntimeError("the corpus never executes")

    def prior_effects(self, action, args, idem_key):
        return [p for p in self._prior if p.get("status") in ("open", "active")]


def _workflow(case: dict[str, Any]):
    steps = []
    needs = []
    if case.get("upstream_reserved"):
        steps.append({"id": "approve", "reserved": True, "action": "policy.grant_exception", "question": "?"})
        needs = ["approve"]
    steps.append({"id": "act", "connector": case["connector"], "action": case["action"], "args": case.get("args") or {},
                  "idempotency_key": f"corpus:{case['id']}:v1", "needs": needs, "invariants": case.get("invariants") or []})
    return parse_workflow({"workflow": f"corpus_{case['id']}", "version": 1, "steps": steps})


def run_corpus(kernel, path: Path = CORPUS) -> dict[str, Any]:
    cases = yaml.safe_load(path.read_text())["cases"]
    agent = Principal(id="agent:corpus", kind="agent", on_behalf_of=kernel.principal("USR-103"))
    rows = []
    for case in cases:
        expect = case.get("expect")
        if "schedule" in case:
            s = case["schedule"]
            obj = kernel.prativaad.check_schedule(run_id=f"corpus-{case['id']}", step_id="act",
                                                  scheduled_for=s["scheduled_for"], should_be=s["should_be"])
            found = [obj] if obj else []
        else:
            wf = _workflow(case)
            step = wf.step("act")
            connector = _PlantedConnector(kernel.registry.connectors[case["connector"]], case.get("prior_effects") or [])
            run = {"id": f"corpus-{case['id']}", "budget_inr": 2.0, "policy_versions": case.get("policy_versions") or []}
            scope = {"steps": case.get("steps") or {}, "facts": case.get("facts") or {}, "subject": {"id": "EMP-1"}}
            result = kernel.prativaad.gate_a(run=run, wf=wf, step=step, connector=connector, args=case.get("args") or {},
                                             idem_key=f"corpus:{case['id']}:v1", scope=scope, raw_pii=set(case.get("raw_pii") or []),
                                             model_review=kernel.prativaad_model_review(run, step, agent))
            found = result.objections
        classes_rules = {o.cls for o in found if o.layer == "rules"}
        classes_model = {o.cls for o in found if o.layer == "model"}
        blocking = [o for o in found if o.severity in ("high", "medium")]
        rows.append({
            "id": case["id"], "title": case["title"], "expect": expect, "clean": bool(case.get("clean")),
            "judgement": bool(case.get("judgement")),
            "caught_by_rules": bool(expect and expect in classes_rules),
            "caught_by_model": bool(expect and expect in classes_model),
            "false_alarm": bool(case.get("clean") and blocking),
            "raised": sorted(classes_rules | classes_model),
        })
    planted = [r for r in rows if not r["clean"]]
    clean = [r for r in rows if r["clean"]]
    caught_rules = sum(r["caught_by_rules"] for r in planted)
    caught_any = sum(r["caught_by_rules"] or r["caught_by_model"] for r in planted)
    model_only = sum(r["caught_by_model"] and not r["caught_by_rules"] for r in planted)
    return {
        "cases": len(rows), "planted": len(planted), "clean": len(clean),
        "catch_rate_rules": caught_rules / len(planted) if planted else None,
        "catch_rate_total": caught_any / len(planted) if planted else None,
        "model_only_catches": model_only,
        "false_clear_rate": 1 - (caught_any / len(planted)) if planted else None,
        "false_alarm_rate": sum(r["false_alarm"] for r in clean) / len(clean) if clean else None,
        "judgement_cases": sum(r["judgement"] for r in planted),
        "judgement_caught": sum((r["caught_by_rules"] or r["caught_by_model"]) for r in planted if r["judgement"]),
        "model_profile": kernel.routing.active_profile,
        "rows": rows,
    }
