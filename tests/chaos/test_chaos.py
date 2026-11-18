"""Chaos drill: 500s, timeouts after commit, 200-without-commit, outages, process kill, clock skew.
In every case: exactly one side effect, and the audit chain explains the episode."""

import pytest

from core.kernel import Kernel
from tests.conftest import settle


def _laptops(kernel, person):
    return [a for a in kernel.mocks.records("assets", "allocation") if a["data"]["holder_ref"] == person]


def _advance_retries(kernel, rounds=12):
    for _ in range(rounds):
        kernel.clock.advance(3)
        kernel.orchestrator.tick()


@pytest.mark.parametrize("mode,count", [("error_500", 3), ("timeout_after_commit", 1), ("ack_no_commit", 1)])
def test_retries_never_duplicate(kernel, mode, count):
    kernel.mocks.set_chaos("assets", mode, count)
    run_id = kernel.orchestrator.start("onboarding", subject_id="EMP-6003", inputs={}, principal=kernel.principal("USR-103"))
    _advance_retries(kernel)
    assert len(_laptops(kernel, "EMP-6003")) == 1
    assert kernel.orchestrator.steps(run_id)["allocate_laptop"]["status"] == "done"
    failures = [c for c in kernel.mocks.call_log() if c["system"] == "assets" and c["outcome"] != "ok"]
    assert failures, "the chaos mode never fired"
    outcomes = [e["outcome"] for e in kernel.audit.for_run(run_id) if e["action"] == "it.assets.allocate"]
    assert outcomes[-1] == "ok"


def test_outage_opens_breaker_then_drains(kernel):
    kernel.mocks.set_chaos("assets", "down")
    run_id = kernel.orchestrator.start("onboarding", subject_id="EMP-6004", inputs={}, principal=kernel.principal("USR-103"))
    _advance_retries(kernel, 8)
    assert kernel.breaker.state("it.assets")["state"] in ("open", "half_open")
    assert kernel.orchestrator.steps(run_id)["allocate_laptop"]["status"] == "running"
    kernel.mocks.clear_chaos("assets")
    kernel.clock.advance(30)
    _advance_retries(kernel, 6)
    assert len(_laptops(kernel, "EMP-6004")) == 1
    assert kernel.breaker.state("it.assets")["state"] == "closed"


def test_process_kill_mid_run_resumes_without_duplicates(kernel, tmp_path):
    kernel.mocks.set_chaos("assets", "error_500", 2)
    kernel.orchestrator.start("onboarding", subject_id="EMP-6005", inputs={}, principal=kernel.principal("USR-103"))
    # "Kill" the process: drop this kernel, build a new one on the same databases.
    kernel.store.close()
    revived = Kernel(tmp_path / "setu.db", tmp_path / "mocks.db")
    for _ in range(10):
        revived.clock.advance(3)
        revived.orchestrator.tick()
    assert len(_laptops(revived, "EMP-6005")) == 1
    assert revived.audit.verify()["ok"]


def test_duplicate_delivery_of_the_same_trigger(kernel):
    principal = kernel.principal("USR-103")
    a = kernel.orchestrator.start("onboarding", subject_id="EMP-6006", inputs={}, principal=principal)
    b = kernel.orchestrator.start("onboarding", subject_id="EMP-6006", inputs={}, principal=principal)
    settle(kernel)
    assert a != b
    assert len(_laptops(kernel, "EMP-6006")) == 1                      # same keys ⇒ second run deduplicates
    dedup = [e for e in kernel.audit.for_run(b) if e["outcome"] == "deduplicated"]
    assert dedup


def test_clock_skew_does_not_fire_scheduled_steps_early(kernel):
    from tests.conftest import decide_open
    run_id = kernel.orchestrator.start("exit", subject_id="EMP-3310", inputs={}, principal=kernel.principal("USR-101"))
    decide_open(kernel, action="exit.accept_resignation", user="USR-111", run_id=run_id)
    decide_open(kernel, action="exit.accept_resignation", user="USR-101", run_id=run_id)
    kernel.clock.advance(-3600 * 24 * 3)       # skew backwards
    settle(kernel)
    assert kernel.orchestrator.steps(run_id)["revoke_access_card"]["status"] == "scheduled"
    assert not kernel.mocks.records("access", "revocation")
