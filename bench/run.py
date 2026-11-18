"""`make bench` — every number SETU publishes comes out of this file.

Runs a deterministic week of work on the synthetic dataset in a fresh,
throw-away database, with an injected IT outage, simulated human approvers
(labelled as such in every receipt), and the fault corpus. Writes
bench/results/latest.json and bench/results/latest.md.

    python -m bench.run [--profile sim|sim_alt]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import tempfile
from datetime import date, timedelta
from pathlib import Path

from bench.fault_corpus import run_corpus
from core import config, metrics

OUT = config.ROOT / "bench" / "results"

HELPDESK = [
    ("USR-4821", "What do I need to bring on day one?"),
    ("USR-4821", "When is my laptop issued?"),
    ("USR-4821", "When will I get my Form 16 for this year?"),
    ("USR-2207", "Who is my buddy and when will I meet them?"),
    ("USR-2207", "What is the induction schedule?"),
    ("USR-3310", "How many casual leaves do I have?"),
    ("USR-3310", "What is the probation period for permanent roles?"),
    ("USR-2207", "How many sick leaves do I have?"),
]


def bench(profile: str = "sim", seed_value: int = 7) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="setu-bench-"))
    os.environ["SETU_VAR"] = str(tmp)
    from core.kernel import Kernel
    from core import intents
    from tools.hrx.__main__ import _auto_decide
    from tools.seed import seed

    k = Kernel(tmp / "setu.db", tmp / "mocks.db")
    k.routing.set_profile(profile)
    seed(k)
    rng = random.Random(seed_value)
    hrbp = k.principal("USR-103")
    run_ids: list[str] = []

    def settle(rounds: int = 40) -> None:
        for _ in range(rounds):
            k.clock.advance(5)
            _auto_decide(k, run_ids)
            k.orchestrator.tick()

    # Thursday's outage: the asset system fails its next calls.
    k.mocks.set_chaos("assets", "error_500", 4)

    # Onboarding: every pre-joiner, Meera first.
    joiners = ["EMP-4821"] + [p["id"] for p in k.sor.people("employee") if p["attrs"]["status"] == "pre_joining" and p["id"] != "EMP-4821"]
    for n, pid in enumerate(joiners):
        run_ids.append(k.orchestrator.start("onboarding", subject_id=pid, principal=hrbp,
                                            inputs={"band_exception_requested": n == 3}))
    settle()

    # Exits: Rahul (with grievance line and early-release request) plus a sample of the population.
    today = date.fromisoformat(k.clock.today())
    leavers = ["EMP-3310"] + rng.sample([p["id"] for p in k.sor.people("employee") if p["id"].startswith("EMP-50")], 7)
    for n, pid in enumerate(leavers):
        inputs = {"letter_text": "I am resigning to pursue another role." + (" My manager has been bullying me." if n == 0 else "")}
        if n % 3 == 0:
            inputs["requested_last_day"] = (today + timedelta(days=20)).isoformat()
        run_ids.append(k.orchestrator.start("exit", subject_id=pid, principal=hrbp, inputs=inputs))
    settle()

    # Leave: forty requests from the population, through the intent API's workflow.
    population = [p for p in k.sor.people("employee") if p["attrs"]["status"] == "active"]
    for _ in range(40):
        p = rng.choice(population)
        leave_type = rng.choice(["casual", "casual", "sick", "earned"])
        days = rng.choice([1, 1, 2, 3, 6, 9])
        start = (today + timedelta(days=rng.randint(1, 30))).isoformat()
        run_ids.append(k.orchestrator.start("leave", subject_id=p["id"], principal=k.principal("USR-103"),
                                            inputs={"leave_type": leave_type, "days": days, "start_date": start}))
    settle()

    # Helpdesk through the chat intent API (same path Slack uses).
    for user, text in HELPDESK * 4:
        reply = intents.handle(k, user, text, "slack")
        if reply.get("run_id"):
            run_ids.append(reply["run_id"])
    settle(10)

    # Talent: one requisition, campaign approved by the TA lead.
    run_ids.append(k.orchestrator.start("sourcing", subject_id=None, principal=k.principal("USR-110"), inputs={}))
    settle(10)

    # Move past every last working day so scheduled deprovisioning and settlement close.
    k.clock.advance(86400 * 100)
    settle(30)

    corpus = run_corpus(k)
    overview = metrics.overview(k)
    result = {
        "generated_by": "make bench (bench/run.py)",
        "profile": profile,
        "dataset": "synthetic seed (tools/seed.py), seeded RNG",
        "note": "Human approvals in this harness are simulated and labelled as such in each receipt note.",
        "runs_started": len(run_ids),
        "workflows": overview["workflows"],
        "governance": {k2: v for k2, v in overview["governance"].items() if k2 != "audit"},
        "audit_chain": overview["governance"]["audit"],
        "prativaad": overview["prativaad"],
        "models": overview["models"],
        "projection": overview["projection"],
        "fault_corpus": corpus,
    }
    k.store.close()
    return result


def _inr(v, d=4):
    return "—" if v is None else f"₹{v:,.{d}f}"


def _pct(v):
    return "—" if v is None else f"{v * 100:.0f}%"


def to_markdown(r: dict) -> str:
    lines = [f"# SETU bench — measured on the synthetic dataset ({r['profile']} profile)", "",
             f"Generated by `make bench`. {r['note']} Rupee figures use the profile's declared rate card (config/routing.yaml).", "",
             "| Line | Completed / runs | ₹/run p50 | ₹/run p95 | No human touch | Escalated runs | Tier-0 steps |",
             "|---|---|---|---|---|---|---|"]
    for name, w in r["workflows"].items():
        if not w["runs"]:
            continue
        mix = w["tier_mix"]
        total = sum(mix.values()) or 1
        lines.append(f"| {name} | {w['completed']} / {w['runs']} | {_inr(w['cost_p50'])} | {_inr(w['cost_p95'])} | "
                     f"{_pct(w['automation_rate'])} | {_pct(w['escalation_rate'])} | {_pct(mix.get(0, mix.get('0', 0)) / total)} |")
    g, pv, fc = r["governance"], r["prativaad"], r["fault_corpus"]
    lines += ["", "## Governance", "",
              f"- Kernel refusals: **{g['refusals']}** ({_pct(g['policy_block_rate'])} of governed actions)",
              f"- Human decisions with receipts: **{g['reserved_decisions']}** (reserved decisions, plus any escalation a person resolved)",
              f"- Audit chain: {'intact' if r['audit_chain']['ok'] else 'BROKEN'}, {r['audit_chain']['checked']} entries", "",
              "## Prativaad", "",
              f"- Objections raised at runtime: {pv['objections']} (rules layer {pv['by_layer']['rules']}, model layer {pv['by_layer']['model']})",
              f"- Precision (upheld / resolved): {_pct(pv['precision'])}",
              f"- Cost: {_inr(pv['cost_inr'])}, {_pct(pv['overhead_share'])} of total run cost",
              f"- Fault corpus ({fc['planted']} planted defects, {fc['clean']} clean steps): rules caught {_pct(fc['catch_rate_rules'])}, "
              f"rules + model {_pct(fc['catch_rate_total'])}, model-only catches {fc['model_only_catches']}, "
              f"judgement-only defects caught {fc['judgement_caught']}/{fc['judgement_cases']}, false alarms {_pct(fc['false_alarm_rate'])}",
              "", "## Projection (assumed volumes)", "",
              f"{r['projection']['assumptions']}", "",
              "| Line | Runs / month (assumed) | Measured ₹/run | ₹ / month incl. hosting share |", "|---|---|---|---|"]
    for row in r["projection"]["rows"]:
        lines.append(f"| {row['workflow']} | {row['runs_per_month_assumed']} | {_inr(row['measured_inr_per_run_p50'])} | {_inr(row['total_inr_per_month'], 0)} |")
    lines.append(f"| **total** | | | **{_inr(r['projection']['total_inr_per_month'], 0)}** |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="sim")
    args = parser.parse_args()
    result = bench(args.profile)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(result, indent=2, default=str))
    md = to_markdown(result)
    (OUT / "latest.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
