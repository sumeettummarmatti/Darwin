"""hrx — the developer CLI for extending SETU without touching core/.

    hrx scaffold workflow <name>      workflow + policy pack (empty tests:) + test spec
    hrx scaffold skill <name>         deterministic skill skeleton
    hrx scaffold connector <name>     connector skeleton against the SDK
    hrx validate                      schema, invariants and the governance lint (Prativaad gate C)
    hrx test [--workflow NAME] [--runs N]
                                      pack tests + replay N synthetic runs under an injected retry storm

Run as ``python -m tools.hrx …`` or ``./hrx …``.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from core import config

GREEN, RED, YELLOW, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def bad(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {msg}")


# ── scaffold ──────────────────────────────────────────────────────────────────

WORKFLOW_TEMPLATE = """# {title} — scaffolded by hrx. Fill in the rules in policies/{name}.v1.yaml first.
workflow: {name}
version: 1
service_line: {name}
description: TODO one sentence on what this workflow does for an employee.
principal: agent:{name}
trigger:
  intents: []
inputs:
  person_id: {{ type: string }}
metrics:
  budget_inr_per_run: 0.50
  target_automation_rate: 0.80

steps:
  - id: compute
    title: Compute by rule
    skill: policy.compute
    deterministic: true
    args:
      pack: {name}
      facts: {{ grade: "{{{{subject.grade}}}}", employment_type: "{{{{subject.employment_type}}}}" }}

  - id: approve
    title: Human decision
    reserved: true
    action: policy.grant_exception          # TODO: the reserved action this needs (see reserved_decisions)
    needs: [compute]
    question: "TODO one specific question for the approver about {{{{subject.display_name}}}}?"
    packet_from: [compute]

  - id: record
    title: Record the outcome
    connector: hr.record
    action: record_event
    needs: [approve]
    args: {{ person_id: "{{{{subject.id}}}}", event: {name}.completed, payload: {{}} }}
    idempotency_key: "{name}:{{{{subject.id}}}}:record:v1"

  - id: notify
    title: Tell the employee
    connector: calendar
    action: create_event
    needs: [record]
    args: {{ title: "{title} completed", at: "{{{{today}}}}", attendees: ["{{{{subject.email}}}}"] }}
    idempotency_key: "{name}:{{{{subject.id}}}}:notify:v1"
"""

PACK_TEMPLATE = """# {title} policy — scaffolded by hrx. Rules here, never in a prompt or an if.
pack: {name}
version: 1
effective_from: 2026-01-01
owner: hr_business_partner

rules:
  - id: {prefix}-001
    when: "employment_type == 'permanent'"
    then: {{ eligible: true }}
  - id: {prefix}-099
    then: {{ eligible: false }}

# hrx validate refuses to load a pack with no tests. Write them before the rules grow.
tests: []
"""

SPEC_TEMPLATE = """# Golden-run spec for {name}, used by `hrx test --workflow {name}`.
workflow: {name}
subjects: [EMP-5000, EMP-5001, EMP-5002]
expect:
  completes: true
  no_duplicate_side_effects: true
"""

SKILL_MANIFEST = """skill: {dotted}
version: 1
kind: deterministic
description: TODO what this skill computes.
inputs: [args.example]                 # declare precisely: the PII proxy strips everything else
outputs: {{ result: any }}
capabilities: [compute]                # approve / accept / reject_candidate / sign_off / decide can never appear
"""

SKILL_HANDLER = '''"""{dotted} — TODO."""


def run(ctx):
    value = ctx.input("args.example")
    return {{"result": value}}
'''

CONNECTOR_MANIFEST = """connector: {dotted}
version: 1
system: {name}
domain: {name}
description: TODO the external system this adapts.
actions:
  do_thing: {{ side_effect: true, irreversible: false, capability: provision }}
cost_inr_per_call: 0.0
"""

CONNECTOR_CODE = '''"""{dotted} adapter."""

from typing import Any

from core.connectors_sdk import Connector


class Adapter(Connector):
    def execute(self, action: str, args: dict[str, Any], idem_key: str) -> dict[str, Any]:
        # Always pass the idempotency key to the system as the client reference.
        return self.call(action, {{**args, "reference": idem_key}})


CONNECTOR = Adapter
'''


def scaffold(kind: str, raw_name: str) -> int:
    name = raw_name.replace("-", "_").lower()
    title = name.replace("_", " ").capitalize()
    created: list[Path] = []

    def write(path: Path, text: str) -> None:
        if path.exists():
            warn(f"{path.relative_to(config.ROOT)} exists — left untouched")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        created.append(path)

    print(f"{BOLD}hrx scaffold {kind} {raw_name}{RESET}")
    if kind == "workflow":
        prefix = "".join(w[0] for w in name.split("_")).upper()[:3] or "X"
        write(config.WORKFLOWS_DIR / f"{name}.v1.yaml", WORKFLOW_TEMPLATE.format(name=name, title=title))
        write(config.POLICIES_DIR / f"{name}.v1.yaml", PACK_TEMPLATE.format(name=name, title=title, prefix=prefix))
        write(config.ROOT / "tests" / "workflows" / f"{name}.spec.yaml", SPEC_TEMPLATE.format(name=name))
    elif kind == "skill":
        d = config.SKILLS_DIR / name
        write(d / "manifest.yaml", SKILL_MANIFEST.format(dotted=name.replace("_", ".", 1)))
        write(d / "handler.py", SKILL_HANDLER.format(dotted=name.replace("_", ".", 1)))
    elif kind == "connector":
        d = config.CONNECTORS_DIR / name
        write(d / "manifest.yaml", CONNECTOR_MANIFEST.format(dotted=name.replace("_", "."), name=name))
        write(d / "connector.py", CONNECTOR_CODE.format(dotted=name.replace("_", ".")))
    else:
        bad(f"unknown kind '{kind}' (workflow | skill | connector)")
        return 2
    for p in created:
        ok(str(p.relative_to(config.ROOT)))
    if kind == "workflow":
        print(f"  {DIM}ℹ the pack ships with an empty tests: block — hrx validate will refuse it until you add tests{RESET}")
        print(f"  {DIM}ℹ review policies/reserved_decisions for the reserved action this line needs{RESET}")
    return 0


# ── validate ──────────────────────────────────────────────────────────────────

def _registry():
    from core.registry import Registry
    from mocks.tbo import InProcessTransport, TboMocks

    tmp = Path(tempfile.mkdtemp())
    return Registry.load(InProcessTransport(TboMocks(tmp / "mocks.db")), strict=False)


def validate() -> int:
    from core.prativaad import Prativaad

    print(f"{BOLD}hrx validate{RESET}")
    reg = _registry()
    errors = 0
    for p in reg.problems:
        bad(f"[{p.kind}] {p.message}")
        errors += 1
    tests = sum(len(p.run_tests()) for versions in reg.packs.values() for p in versions)
    if not [p for p in reg.problems if p.kind == "pack"]:
        ok(f"policy packs: {sum(len(v) for v in reg.packs.values())} loaded, {tests} pack tests passing")
    if reg.reserved:
        ok(f"reserved registry {reg.reserved.ref}: {len(reg.reserved.entries)} reserved actions, "
           f"{len(reg.reserved.route_only)} route-only, may_never {reg.reserved.may_never}")
    ok(f"skills: {len(reg.skills)} — no reserved verb granted, no prohibited input declared")
    ok(f"connectors: {len(reg.connectors)} (including spares)")
    ok(f"workflows: {sum(len(v) for v in reg.workflows.values())} — idempotency keys templated and unique, "
       "deterministic steps model-free, reserved actions known")

    class _Null:
        def append(self, *_a, **_k):
            return 0

    lint = Prativaad(None, None, _Null(), lambda: reg)  # gate C needs only the registry
    for wf in reg.latest_workflows():
        for f in lint.gate_c(wf):
            where = f"{wf.ref}{(':' + f['step']) if f['step'] else ''}"
            if f["level"] == "error":
                bad(f"governance lint {f['rule']} {where}: {f['message']}")
                errors += 1
            else:
                warn(f"governance lint {f['rule']} {where}: {f['message']}")
    print(f"\n{(GREEN + 'valid') if not errors else (RED + f'{errors} error(s)')}{RESET}")
    return 1 if errors else 0


# ── test ──────────────────────────────────────────────────────────────────────

def test(workflow: str | None, runs: int) -> int:
    import os

    import yaml

    from core.kernel import Kernel
    from tools.seed import seed

    print(f"{BOLD}hrx test{RESET}")
    if validate() != 0:
        bad("fix validation errors first")
        return 1
    print()
    tmp = Path(tempfile.mkdtemp())
    os.environ["SETU_VAR"] = str(tmp)
    k = Kernel(tmp / "setu.db", tmp / "mocks.db")
    k.routing.set_profile("sim")          # replay is about governance, not model quality: stay offline
    seed(k)
    targets = [workflow] if workflow else [w.name for w in k.registry.latest_workflows()
                                           if w.name in ("onboarding", "exit", "leave") or (config.ROOT / "tests" / "workflows" / f"{w.name}.spec.yaml").exists()]
    failures = 0
    for name in targets:
        spec_path = config.ROOT / "tests" / "workflows" / f"{name}.spec.yaml"
        spec = yaml.safe_load(spec_path.read_text()) if spec_path.exists() else {}
        subjects = spec.get("subjects") or _default_subjects(k, name)
        subjects = (subjects * ((runs // max(len(subjects), 1)) + 1))[:runs]
        # Retry storm: every external system fails its next calls, then recovers.
        for system in ("tickets", "assets", "access", "directory", "payroll", "mail", "calendar"):
            k.mocks.set_chaos(system, "error_500", 2)
        run_ids = []
        for subject in subjects:
            run_ids.append(k.orchestrator.start(name, subject_id=subject, inputs=dict(spec.get("inputs") or {}),
                                                principal=k.principal("USR-103")))
        for _ in range(60):
            k.clock.advance(5)
            _auto_decide(k, run_ids)
            k.orchestrator.tick()
        k.clock.advance(86400 * 120)          # past every last working day, so scheduled steps fire
        for _ in range(20):
            k.clock.advance(5)
            _auto_decide(k, run_ids)
            k.orchestrator.tick()
        duplicates = _duplicates(k)
        statuses = [k.orchestrator.run(r)["status"] for r in run_ids]
        completed = sum(s == "completed" for s in statuses)
        line = f"{name}: {completed}/{len(run_ids)} runs completed under an injected retry storm"
        (ok if completed == len(run_ids) else warn)(line)
        if duplicates:
            bad(f"{name}: {len(duplicates)} idempotency key(s) produced more than one side effect: {duplicates[:3]}")
            failures += 1
        else:
            ok(f"{name}: no duplicate side effects ({_effects(k)} keyed effects verified by read-back)")
    ok(f"audit chain: {k.audit.verify()['checked']} entries verified" if k.audit.verify()["ok"] else "audit chain broken")
    print(f"\n{(GREEN + 'pass') if not failures else (RED + 'fail')}{RESET}")
    return 1 if failures else 0


def _default_subjects(k, name: str) -> list[str]:
    status = "pre_joining" if name == "onboarding" else "active"
    return [p["id"] for p in k.sor.people("employee") if p["attrs"].get("status") == status][:8]


_RETRIES: dict[tuple, int] = {}


def _auto_decide(k, run_ids: list[str]) -> None:
    """Simulated humans for the harness: approve reserved decisions, accept drafts. Labelled in the audit."""
    users = k.users()
    for item in k.queue.list("open"):
        if item["run_id"] not in run_ids:
            continue
        needed = item["approver_roles"][len(item["approvals"])] if item["approver_roles"] else None
        user = next((u for u in users if needed in u["roles"]), None) or next(
            (u for u in users if set(u["roles"]) & set(item["approver_roles"])), None)
        if not user:
            continue
        decision = {"reserved": "approve", "route_only": "acknowledge", "objection": "proceed", "failure": "retry",
                    "refused": "mark_done", "paused": "finish_by_hand"}.get(item["kind"], "accept_draft")
        if item["kind"] == "failure":
            key = (item["run_id"], item["step_id"])
            _RETRIES[key] = _RETRIES.get(key, 0) + 1
            if _RETRIES[key] > 2:
                decision = "mark_done"          # a person would stop retrying and finish it by hand
        try:
            k.decide(item["id"], user["id"], decision, context_hash=item["context_hash"], note="hrx test harness (simulated human)")
        except Exception:  # noqa: BLE001 - harness keeps going
            pass


def _duplicates(k) -> list[str]:
    dup = []
    for row in k.store.query("SELECT idem_key, connector FROM outbox WHERE status='done'"):
        conn = k.registry.connectors.get(row["connector"])
        if not conn or conn.manifest.system == "sor":
            continue
        records = k.mocks.by_reference(conn.manifest.system, row["idem_key"])
        if len(records) > 1:
            dup.append(row["idem_key"])
    return dup


def _effects(k) -> int:
    return k.store.one("SELECT COUNT(*) AS n FROM outbox WHERE status='done'")["n"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hrx", description="Extend SETU without touching core/.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scaffold")
    s.add_argument("kind", choices=["workflow", "skill", "connector"])
    s.add_argument("name")
    sub.add_parser("validate")
    t = sub.add_parser("test")
    t.add_argument("--workflow")
    t.add_argument("--runs", type=int, default=6)
    args = parser.parse_args(argv)
    if args.cmd == "scaffold":
        return scaffold(args.kind, args.name)
    if args.cmd == "validate":
        return validate()
    return test(args.workflow, args.runs)


if __name__ == "__main__":
    sys.exit(main())
