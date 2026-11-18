"""Reserved decisions, RBAC, kill switch, circuit breaker, receipts, audit chain."""

import pytest

from core.queue import QueueError
from core.registry import Registry
from core.reserved import parse_registry
from core.types import Principal, ProposedAction
from core.workflows import WorkflowLoadError, parse_workflow, validate_workflow
from tests.conftest import decide_open, settle


def test_reserved_drill_every_reserved_action_is_refused_and_audited(kernel):
    results = kernel.reserved_drill("USR-103")
    assert results and all(r["outcome"] == "refused" and r["status"] == 403 for r in results)
    refused = kernel.audit.recent(500, outcome="refused")
    assert len([e for e in refused if e["actor"] == "agent:drill@v1"]) == len(results)


def test_agent_cannot_decide_a_queue_item_even_with_the_hash(kernel):
    run_id = kernel.orchestrator.start("exit", subject_id="EMP-3310", inputs={"person_id": "EMP-3310"}, principal=kernel.principal("USR-101"))
    item = next(i for i in kernel.queue.list() if i["run_id"] == run_id and i["kind"] == "reserved")
    agent = Principal(id="agent:exit@v1", kind="agent", on_behalf_of=kernel.principal("USR-103"))
    with pytest.raises(QueueError) as exc:
        kernel.queue.decide(item["id"], agent, "approve", context_hash_seen=item["context_hash"])
    assert exc.value.status == 403


def test_wrong_role_and_sequential_order_are_enforced(kernel):
    run_id = kernel.orchestrator.start("exit", subject_id="EMP-3310", inputs={"person_id": "EMP-3310"}, principal=kernel.principal("USR-101"))
    item = next(i for i in kernel.queue.list() if i["run_id"] == run_id and i["kind"] == "reserved")
    # Sequential: the reporting manager must approve before the HRBP.
    with pytest.raises(QueueError, match="reporting_manager"):
        kernel.decide(item["id"], "USR-101", "approve", context_hash=item["context_hash"])
    with pytest.raises(QueueError):
        kernel.decide(item["id"], "USR-104", "approve", context_hash=item["context_hash"])  # finance has no role here


def test_stale_context_is_refused(kernel):
    run_id = kernel.orchestrator.start("exit", subject_id="EMP-3310", inputs={"person_id": "EMP-3310"}, principal=kernel.principal("USR-101"))
    item = next(i for i in kernel.queue.list() if i["run_id"] == run_id and i["kind"] == "reserved")
    with pytest.raises(QueueError, match="stale"):
        kernel.decide(item["id"], "USR-111", "approve", context_hash="sha256:something-else")


def test_receipt_hash_matches_what_was_shown(kernel):
    kernel.orchestrator.start("exit", subject_id="EMP-3310", inputs={"person_id": "EMP-3310"}, principal=kernel.principal("USR-101"))
    decided = decide_open(kernel, action="exit.accept_resignation", user="USR-111")
    receipt_id = decided["receipt_ids"][0]
    assert kernel.queue.verify_receipt(receipt_id)["matches"]


def _registry_with(kernel, workflow_raw):
    wf = parse_workflow(workflow_raw)
    validate_workflow(wf, skills=kernel.registry.skills, connectors=kernel.registry.connectors, registry=kernel.registry.reserved)


def test_workflow_with_agent_reserved_verb_fails_at_load(kernel):
    with pytest.raises(WorkflowLoadError):
        _registry_with(kernel, {"workflow": "bad", "version": 1, "steps": [
            {"id": "x", "connector": "payroll", "action": "setup_employee", "idempotency_key": "k:{{subject.id}}:v1"},
            {"id": "y", "reserved": True, "action": "not.in.registry"}]})


def test_side_effect_without_idempotency_key_fails_at_load(kernel):
    with pytest.raises(WorkflowLoadError, match="idempotency_key"):
        _registry_with(kernel, {"workflow": "bad", "version": 1, "steps": [
            {"id": "x", "connector": "it.assets", "action": "allocate", "args": {}}]})


def test_deterministic_step_cannot_call_a_model(kernel):
    with pytest.raises(WorkflowLoadError, match="deterministic"):
        _registry_with(kernel, {"workflow": "bad", "version": 1, "steps": [
            {"id": "x", "skill": "exit.prepare_packet", "deterministic": True}]})


def test_skill_granting_a_reserved_verb_fails_at_load(tmp_path, kernel):
    from core.skills import SkillLoadError, load_skill
    d = tmp_path / "bad_skill"
    d.mkdir()
    (d / "manifest.yaml").write_text("skill: bad.approver\nkind: deterministic\ncapabilities: [compute, approve]\n")
    (d / "handler.py").write_text("def run(ctx):\n    return {}\n")
    with pytest.raises(SkillLoadError, match="reserved verb"):
        load_skill(d, may_never=kernel.registry.reserved.may_never, prohibited=[])


def test_rbac_same_agent_two_principals_different_outcomes(kernel):
    # Priya's org units include DATA; Sana's do not.
    agent_for = lambda uid: Principal(id="agent:onboarding@v3", kind="agent", on_behalf_of=kernel.principal(uid))
    subject = kernel.sor.subject_view("EMP-4821")
    proposal = lambda: ProposedAction(action="it.ticketing.open_ticket", args={"queue": "x", "title": "t"}, idem_key="rbac:test:v1",
                                      connector="it.ticketing", connector_action="open_ticket")
    refused = kernel.executor.submit(proposal(), agent_for("USR-108"), subject)
    assert refused.outcome == "refused" and "outside" in refused.reason
    allowed = kernel.executor.submit(proposal(), agent_for("USR-101"), subject)
    assert allowed.done


def test_purpose_limitation_refuses_cross_purpose_payload(kernel):
    subject = kernel.sor.subject_view("EMP-4821")
    agent = Principal(id="agent:x", kind="agent", on_behalf_of=kernel.principal("USR-101"))
    res = kernel.executor.submit(ProposedAction(action="it.assets.allocate", args={"asset_class": "B", "bank_account_token": subject["bank_account_token"]},
                                                idem_key="purpose:test:v1", connector="it.assets", connector_action="allocate"), agent, subject)
    assert res.outcome == "refused" and "purpose" in res.reason


def test_kill_switch_parks_and_release_resumes(kernel):
    kernel.killswitch.set("workflow", "onboarding", True, "human:USR-103", "suspected entitlement error")
    run_id = kernel.orchestrator.start("onboarding", subject_id="EMP-6000", inputs={}, principal=kernel.principal("USR-103"))
    assert kernel.orchestrator.run(run_id)["status"] == "paused"
    assert any(i["kind"] == "paused" and i["run_id"] == run_id for i in kernel.queue.list())
    kernel.killswitch.set("workflow", "onboarding", False, "human:USR-103")
    settle(kernel)
    assert kernel.orchestrator.run(run_id)["status"] in ("completed", "waiting")


def test_circuit_breaker_pauses_a_workflow_on_escalation_rate(kernel):
    # Over-balance leave requests each need an exception: escalate? No — reserved is by design.
    # Force genuine escalations instead: the leave pack refuses when the record lacks the field.
    for n in range(5):
        kernel.orchestrator.start("leave", subject_id=f"EMP-{5000 + n}", principal=kernel.principal("USR-103"),
                                  inputs={"leave_type": "unknown_type", "days": 2, "start_date": "not-a-date"})
    assert kernel.killswitch.blocking(workflow="leave") is not None
    assert kernel.killswitch.blocking(workflow="onboarding") is None


def test_audit_chain_detects_tampering(kernel):
    kernel.orchestrator.start("onboarding", subject_id="EMP-6001", inputs={}, principal=kernel.principal("USR-103"))
    assert kernel.audit.verify()["ok"]
    with kernel.store.tx() as conn:
        conn.execute("UPDATE audit SET outcome='ok-edited' WHERE seq=5")
    result = kernel.audit.verify()
    assert not result["ok"] and result["broken_at"] == 5


def test_hr_can_change_the_reserved_list_without_a_deploy(kernel):
    from core.reserved import RegistryLoadError
    raw = dict(kernel.registry.reserved.raw)
    raw["version"] = 3
    raw["reserved"] = list(raw["reserved"]) + [{"action": "it.assets.allocate", "approver_role": ["it_lead"]}]
    # The registry's own tests say agents may allocate laptops — so the edit is refused until they are updated.
    with pytest.raises(RegistryLoadError, match="tests failing"):
        parse_registry(raw)
    raw["tests"] = [t for t in raw["tests"] if t["action"] != "it.assets.allocate"] + [
        {"action": "it.assets.allocate", "principal": "agent", "expect": "refuse"}]
    candidate = parse_registry(raw)
    assert candidate.classify("it.assets.allocate", "agent").outcome == "refuse"
