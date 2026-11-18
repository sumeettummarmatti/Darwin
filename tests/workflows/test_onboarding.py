"""Golden run for onboarding: Meera's story (DESIGN.md §4.3, Wednesday)."""

from tests.conftest import decide_open, settle


def test_meera_onboarding_golden_run(kernel):
    run_id = kernel.orchestrator.start("onboarding", subject_id="EMP-4821", inputs={}, principal=kernel.principal("USR-101"))
    steps = kernel.orchestrator.steps(run_id)

    # Entitlements by rule, tier 0.
    ent = steps["resolve_entitlements"]
    assert ent["status"] == "done" and ent["tier"] == 0 and ent["outputs"]["laptop_class"] == "A"

    # Prativaad caught the prior allocation and the kernel released it by *reading* the return ledger.
    objections = kernel.store.query("SELECT * FROM objections WHERE run_id=? AND class='duplicate_side_effect'", (run_id,))
    assert objections and objections[0]["upheld"] == 1 and "returned on 2024-09-14" in objections[0]["resolution"]
    assert steps["allocate_laptop"]["status"] == "done"

    # The faint ID scan went to a human with a context packet, not a guess — after a measured tier escalation.
    item = next(i for i in kernel.queue.list() if i["run_id"] == run_id)
    assert item["kind"] == "low_confidence" and item["packet"]["escalations"]
    calls = kernel.store.query("SELECT tier, escalation_reason FROM model_calls WHERE run_id=? AND skill LIKE 'onboarding.extract_id%'", (run_id,))
    assert [c["tier"] for c in calls] == [1, 2] and calls[1]["escalation_reason"].startswith("measured trigger")

    decide_open(kernel, kind="low_confidence", user="USR-101", decision="accept_draft")
    settle(kernel)
    run = kernel.orchestrator.run(run_id)
    assert run["status"] == "completed"
    assert run["cost_inr"] < kernel.registry.workflow("onboarding").budget_inr_per_run

    # Payroll received tokens only.
    payroll = kernel.mocks.records("payroll", "employee")[0]["data"]
    assert payroll["pan_token"].startswith("tok_") and "SYNPA" not in str(payroll)

    # Exactly one new laptop for Meera (plus the stale record from 2024).
    allocations = [a for a in kernel.mocks.records("assets", "allocation") if a["data"]["holder_ref"] == "EMP-4821"]
    assert len(allocations) == 1


def test_model_never_sees_raw_identifiers(kernel):
    kernel.orchestrator.start("onboarding", subject_id="EMP-4821", inputs={}, principal=kernel.principal("USR-101"))
    for call in kernel.store.query("SELECT outbound_payload FROM model_calls"):
        payload = call["outbound_payload"]
        assert "Meera" not in payload and "MEERA" not in payload and "SYNPA" not in payload and "@example.net" not in payload


def test_band_exception_is_reserved_to_the_hr_head(kernel):
    run_id = kernel.orchestrator.start("onboarding", subject_id="EMP-6002", inputs={"band_exception_requested": True},
                                       principal=kernel.principal("USR-103"))
    item = next(i for i in kernel.queue.list() if i["run_id"] == run_id and i["kind"] == "reserved")
    assert item["action"] == "policy.grant_exception" and item["approver_roles"] == ["hr_head"]
    decide_open(kernel, kind="reserved", user="USR-103", values={"approved_band": "B4"}, run_id=run_id)
    settle(kernel)
    payroll = [r for r in kernel.mocks.records("payroll", "employee") if r["data"]["employee_ref"] == "EMP-6002"]
    assert payroll and payroll[0]["data"]["band"] == "B4"
