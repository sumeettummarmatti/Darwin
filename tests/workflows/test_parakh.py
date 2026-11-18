"""PARAKH: lawful basis, no-raid, span-backed claims, deterministic scores, reserved rejection, suppression."""

from tests.conftest import decide_open


def _run(kernel):
    run_id = kernel.orchestrator.start("sourcing", subject_id=None, inputs={}, principal=kernel.principal("USR-110"))
    return run_id, kernel.orchestrator.steps(run_id)


def test_people_with_no_basis_are_pointers_with_nothing_derived(kernel):
    _, steps = _run(kernel)
    pointers = kernel.sor.people("sourced")
    assert pointers and all(p["processing_mode"] == "pointer_only" and p["lawful_basis"] == "none" for p in pointers)
    allowed = {"public_url", "source_id", "collected_at", "role_hypothesis", "org_hint", "public_contact", "identity_hash"}
    assert all(set(p["attrs"]) <= allowed for p in pointers)
    # The suppressed identity was never stored again.
    assert not any("IN202341007731" in p["attrs"]["public_url"] for p in pointers)
    assert steps["basis_gate"]["outputs"]["suppressed"] == 1
    # No model call ever mentioned a pointer.
    for call in kernel.store.query("SELECT outbound_payload FROM model_calls"):
        assert "patents.example" not in call["outbound_payload"] and "code.example" not in call["outbound_payload"]


def test_no_raid_blocks_name_the_clause(kernel):
    _, steps = _run(kernel)
    blocked = {b["ref"]: b["clause"] for b in steps["no_raid"]["outputs"]["blocked"]}
    assert blocked["SIG-PAT-118822"] == "partner_agreement_9b"
    assert blocked["CAND-2003"] == "msa_clause_14"


def test_claims_without_a_verbatim_span_are_discarded_and_scores_are_rule_based(kernel):
    _, steps = _run(kernel)
    discarded = steps["extract_claims"]["outputs"]["discarded"]
    assert any(d["candidate"] == "CAND-2004" and d["criterion"] == "oss_or_patent" for d in discarded)
    ranking = steps["score"]["outputs"]["ranking"]
    assert ranking[0]["candidate_id"] == "CAND-2001" and ranking[0]["score"] == 0.969
    assert all(b["span"] for r in ranking for b in r["breakdown"])
    assert steps["score"]["tier"] == 0


def test_agent_cannot_reject_a_candidate(kernel):
    _, steps = _run(kernel)
    proposals = steps["score"]["outputs"]["_proposals"]
    assert proposals and all(p["action"] == "hire.reject_candidate" and p["status"] == 403 for p in proposals)


def test_gate_d_flags_college_tier_proxy_without_changing_the_ranking(kernel):
    _, steps = _run(kernel)
    flags = steps["bias_challenge"]["outputs"]["flags"]
    assert flags[0]["candidate"] == "CAND-2002" and flags[0]["proxy_for"] == "college_tier"
    assert any(r["candidate_id"] == "CAND-2002" for r in steps["score"]["outputs"]["ranking"])


def test_outreach_waits_for_campaign_approval_then_sends_notice_first(kernel):
    run_id, steps = _run(kernel)
    assert steps["send_notices"]["status"] == "pending" and not kernel.mocks.records("mail", "message")
    decide_open(kernel, action="sourcing.campaign_approve", user="USR-110", run_id=run_id)
    messages = kernel.mocks.records("mail", "message")
    assert len(messages) == 2 and all("reply 'stop'" in m["data"]["body"] for m in messages)


def test_asking_a_model_about_a_pointer_is_refused(kernel):
    _run(kernel)
    pointer = kernel.sor.people("sourced")[0]["id"]
    run_id = kernel.orchestrator.start("sourcing_assess", subject_id=pointer, inputs={}, principal=kernel.principal("USR-110"))
    assert kernel.orchestrator.steps(run_id)["extract"]["status"] == "refused"
    assert not kernel.store.query("SELECT 1 FROM model_calls WHERE run_id=?", (run_id,))


def test_objection_suppresses_and_deletes_interest_upgrades(kernel):
    _run(kernel)
    first, second = kernel.sor.people("sourced")[:2]
    kernel.orchestrator.start("sourcing_reply", subject_id=first["id"], inputs={"reply": "objection"}, principal=kernel.principal("USR-110"))
    assert kernel.sor.person(first["id"]) is None and kernel.dpdp.is_suppressed(first["attrs"]["public_url"])
    kernel.orchestrator.start("sourcing_reply", subject_id=second["id"], inputs={"reply": "interest"}, principal=kernel.principal("USR-110"))
    upgraded = kernel.sor.person(second["id"])
    assert upgraded["processing_mode"] == "full" and kernel.dpdp.consents(second["id"])
