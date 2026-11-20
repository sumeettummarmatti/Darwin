"""Golden run for exit: Rahul's story (DESIGN.md §4.3, Friday afternoon)."""

from datetime import date, timedelta

from tests.conftest import decide_open, settle


def _start(kernel, **inputs):
    return kernel.orchestrator.start("exit", subject_id="EMP-3310", principal=kernel.principal("USR-101"),
                                     inputs={"person_id": "EMP-3310", **inputs})


def test_agent_prepares_but_does_not_accept(kernel):
    run_id = _start(kernel)
    steps = kernel.orchestrator.steps(run_id)
    assert steps["compute_notice"]["outputs"]["notice_days"] == 60
    assert steps["compute_settlement_preview"]["outputs"]["gratuity_eligible"] is False   # 4y2m: the rule decides
    assert steps["accept_resignation"]["status"] == "awaiting_human"
    for downstream in ("revoke_access_card", "recover_laptop", "prepare_settlement"):
        assert steps[downstream]["status"] == "pending"
    packet = next(i for i in kernel.queue.list() if i["run_id"] == run_id)["packet"]
    assert packet["recommendation"]["labelled"].startswith("agent recommendation")
    assert any(c["pack"].startswith("notice_period") and "NP-002" in c["rule_ids"] for c in packet["clauses"])


def test_grievance_line_routes_and_stops(kernel):
    run_id = _start(kernel, letter_text="I resign. Also, my manager has been bullying me for months.")
    item = next(i for i in kernel.queue.list() if i["run_id"] == run_id and i["kind"] == "route_only")
    assert item["approver_roles"] == ["ethics_officer"]
    assert "summary_performed" in str(kernel.audit.for_run(run_id))
    assert "bullying" not in str(item["packet"])          # no summary, no quote — a reference only
    model_calls = kernel.store.query("SELECT outbound_payload FROM model_calls WHERE run_id=?", (run_id,))
    assert all("bullying" not in c["outbound_payload"] for c in model_calls)


def test_buyout_moves_the_date_and_devils_advocate_reschedules_the_card(kernel):
    today = date.fromisoformat(kernel.clock.today())
    requested = (today + timedelta(days=20)).isoformat()
    run_id = _start(kernel, requested_last_day=requested)
    decide_open(kernel, action="exit.accept_resignation", user="USR-111", run_id=run_id)          # manager
    decide_open(kernel, action="exit.accept_resignation", user="USR-101", run_id=run_id)          # then HRBP
    steps = kernel.orchestrator.steps(run_id)
    original = steps["revoke_access_card"]["scheduled_for"]
    assert steps["notice_buyout"]["status"] == "awaiting_human"
    decide_open(kernel, action="exit.notice_buyout_agree", user="USR-103", run_id=run_id)
    settle(kernel)
    steps = kernel.orchestrator.steps(run_id)
    assert steps["revoke_access_card"]["scheduled_for"].startswith(requested)
    assert steps["revoke_access_card"]["scheduled_for"] != original
    objection = kernel.store.one("SELECT * FROM objections WHERE run_id=? AND class='date_ordering'", (run_id,))
    assert objection and objection["upheld"] == 1


def test_full_exit_to_retention(kernel):
    run_id = _start(kernel)
    decide_open(kernel, action="exit.accept_resignation", user="USR-111", run_id=run_id)
    decide_open(kernel, action="exit.accept_resignation", user="USR-101", run_id=run_id)
    settle(kernel)
    decide_open(kernel, action="payroll.sign_off", user="USR-104", run_id=run_id)
    lwd = kernel.orchestrator.run(run_id)["facts"]["last_working_day"]
    days = (date.fromisoformat(lwd) - date.fromisoformat(kernel.clock.today())).days + 1
    kernel.clock.advance(days * 86400)
    settle(kernel)
    run = kernel.orchestrator.run(run_id)
    assert run["status"] == "completed", kernel.orchestrator.steps(run_id)
    settlement = kernel.orchestrator.steps(run_id)["compute_settlement"]["outputs"]
    assert settlement["gratuity_amount"] == 0 and settlement["leave_encashment"] == round(92000 / 26 * 21)
    held = [f for f in kernel.vault.fields_for("EMP-3310") if f["statutory_hold_rule"]]
    assert {f["field"] for f in held} >= {"pan", "uan"}
    assert kernel.mocks.records("access", "revocation")
