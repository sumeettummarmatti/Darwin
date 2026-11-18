"""Second live-extension rehearsal: probation confirmation, built with hrx, zero core changes."""

from datetime import date, timedelta

import pytest

from core.queue import QueueError
from core.types import Principal
from tests.conftest import decide_open


def _recent_joiner(kernel):
    doj = (date.fromisoformat(kernel.clock.today()) - timedelta(days=175)).isoformat()
    kernel.sor.update_attrs("EMP-5000", {"date_of_joining": doj, "employment_type": "permanent"}, "test", "fixture")


def test_manager_confirms_when_review_is_due(kernel):
    _recent_joiner(kernel)
    run_id = kernel.orchestrator.start("probation_confirmation", subject_id="EMP-5000", inputs={}, principal=kernel.principal("USR-103"))
    item = next(i for i in kernel.queue.list() if i["run_id"] == run_id)
    assert item["action"] == "probation.confirm" and item["approver_roles"] == ["reporting_manager"]
    agent = Principal(id="agent:probation_confirmation@v1", kind="agent", on_behalf_of=kernel.principal("USR-103"))
    with pytest.raises(QueueError):
        kernel.queue.decide(item["id"], agent, "approve", context_hash_seen=item["context_hash"])
    decide_open(kernel, action="probation.confirm", user="USR-111", values={"outcome": "confirmed"}, run_id=run_id)
    assert kernel.orchestrator.run(run_id)["status"] == "completed"
    assert any(e["event"] == "probation.decided" for e in kernel.sor.events("EMP-5000"))


def test_nothing_happens_before_the_window(kernel):
    run_id = kernel.orchestrator.start("probation_confirmation", subject_id="EMP-5001", inputs={}, principal=kernel.principal("USR-103"))
    steps = kernel.orchestrator.steps(run_id)
    assert steps["manager_decision"]["status"] == "skipped" and kernel.orchestrator.run(run_id)["status"] == "completed"
