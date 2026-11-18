"""The live-extension rehearsal: built with hrx, zero core changes."""

from tests.conftest import decide_open, settle


def test_small_encashment_needs_no_signoff(kernel):
    # Rahul: 21 earned days × ₹92,000/26 = ₹74,308 → above ₹50,000 → Finance signs off.
    run_id = kernel.orchestrator.start("leave_encashment", subject_id="EMP-3310", inputs={}, principal=kernel.principal("USR-103"))
    item = next(i for i in kernel.queue.list() if i["run_id"] == run_id)
    assert item["action"] == "payroll.sign_off" and item["approver_roles"] == ["finance_controller"]
    decide_open(kernel, action="payroll.sign_off", user="USR-104", run_id=run_id)
    settle(kernel)
    assert kernel.orchestrator.run(run_id)["status"] == "completed"
    steps = kernel.orchestrator.steps(run_id)
    assert steps["compute"]["outputs"]["encashable_days"] == 21 and steps["compute"]["outputs"]["amount"] == 74308


def test_finance_gate_skipped_below_threshold(kernel):
    kernel.sor.update_attrs("EMP-5000", {"leave_balance": {"earned": 2.0}, "basic_monthly": 36000}, "test", "fixture")
    run_id = kernel.orchestrator.start("leave_encashment", subject_id="EMP-5000", inputs={}, principal=kernel.principal("USR-103"))
    assert kernel.orchestrator.run(run_id)["status"] == "completed"
    assert kernel.orchestrator.steps(run_id)["finance_sign_off"]["status"] == "skipped"
