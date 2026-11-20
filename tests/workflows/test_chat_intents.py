"""Chat answers from the record: greetings, 'who am I', and joining status need no model and never hit the HR queue."""

from core import intents


def test_greeting_is_answered_without_a_model_or_a_queue_item(kernel):
    r = intents.handle(kernel, "USR-4821", "hi")
    assert r["intent"] == "greeting" and r["tier"] == 0 and "Meera" in r["reply"]
    assert kernel.store.one("SELECT COUNT(*) AS n FROM human_queue")["n"] == 0


def test_who_am_i_comes_from_the_record(kernel):
    r = intents.handle(kernel, "USR-4821", "what is my name")
    assert r["intent"] == "self.profile" and "Meera Iyer" in r["reply"] and "Arjun Mehta" in r["reply"]


def test_joining_status_before_and_after_onboarding_starts(kernel):
    before = intents.handle(kernel, "USR-4821", "when is my latop issued")
    assert before["intent"] == "onboarding.status" and "hasn't started" in before["reply"]
    kernel.orchestrator.start("onboarding", subject_id="EMP-4821", principal=kernel.principal("USR-101"), channel="web", inputs={})
    after = intents.handle(kernel, "USR-4821", "when is my laptop issued")
    assert "Laptop:" in after["reply"] and after["run_id"]


def test_a_complaint_mentioning_my_manager_is_still_routed(kernel):
    r = intents.handle(kernel, "USR-3310", "my manager has been bullying me")
    assert r["intent"] == "route_only" and r.get("queue_id")
