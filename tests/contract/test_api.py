"""API contract smoke test over the FastAPI app (in-process)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SETU_VAR", str(tmp_path))
    monkeypatch.setenv("SETU_WORKER", "0")
    from apps.api import server
    server.holder.kernel = None
    with TestClient(server.app) as c:
        yield c
    if server.holder.kernel:
        server.holder.kernel.store.close()
    server.holder.kernel = None


def test_bootstrap_runs_queue_and_metrics(client):
    boot = client.get("/api/bootstrap").json()
    assert {w["name"] for w in boot["workflows"]} >= {"onboarding", "exit", "leave", "helpdesk"}
    run = client.post("/api/runs", json={"workflow": "onboarding", "subject_id": "EMP-4821", "user_id": "USR-101"}).json()
    detail = client.get(f"/api/runs/{run['run_id']}").json()
    assert detail["steps"] and detail["audit"]
    queue = client.get("/api/queue", params={"user_id": "USR-101"}).json()
    item = queue[0]
    decided = client.post(f"/api/queue/{item['id']}/decide", json={"user_id": "USR-101", "decision": "accept_draft",
                                                                  "context_hash": item["context_hash"]}).json()
    assert decided["status"] == "decided"
    m = client.get("/api/metrics").json()
    assert m["workflows"]["onboarding"]["completed"] == 1
    assert client.get("/api/audit/verify").json()["ok"]


def test_chat_intents(client):
    r = client.post("/api/intent", json={"user_id": "USR-4821", "text": "What do I need to bring on day one?"}).json()
    assert r["intent"] == "helpdesk.answer" and r["citations"][0]["clause"] == "ONB-C1"
    r = client.post("/api/intent", json={"user_id": "USR-3310", "text": "How many casual leaves do I have?"}).json()
    assert "casual" in r["reply"] and r["tier"] == 0
    r = client.post("/api/intent", json={"user_id": "USR-2207", "text": "I have been harassed by a colleague"}).json()
    assert r["intent"] == "route_only"
    redacted = client.get("/api/queue", params={"user_id": "USR-101"}).json()
    assert any(i.get("redacted") for i in redacted)


def test_drill_endpoint_refuses_everything(client):
    out = client.post("/api/drill", json={"user_id": "USR-103"}).json()
    assert out["all_refused"]


def test_policy_activation_refuses_path_traversal(client):
    yaml_text = "pack: ../../core/evil\nversion: 9\neffective_from: 2026-01-01\nrules: [{id: R1, then: {x: 1}}]\ntests: [{given: {}, expect: {x: 1}}]\n"
    r = client.post("/api/policies/notice_period/activate", json={"yaml": yaml_text}).json()
    assert r["ok"] is False


MATERIALS_STEP = '''
  - id: collect_materials
    title: Collect issued materials
    connector: it.ticketing
    action: open_ticket
    needs: [accept_resignation]
    args: { summary: "Collect issued materials from {{subject.display_name}}" }
    idempotency_key: "exit:{{subject.id}}:materials:v1"
    compensation: close_ticket
'''


def test_workflow_editor_checks_like_hrx_validate(client):
    blocks = {w["name"]: w for w in client.get("/api/workflows").json()}
    assert any(s["kind"] == "person" for s in blocks["exit"]["steps"])
    src = client.get("/api/workflows/exit/source").json()["yaml"]
    added = src.replace("\nsteps:\n", "\nsteps:\n" + MATERIALS_STEP.lstrip("\n") + "\n", 1)
    ok = client.post("/api/workflows/exit/check", json={"yaml": added}).json()
    assert ok["ok"] and any(s["id"] == "collect_materials" for s in ok["preview"]["steps"])
    # An agent step that tries to accept the resignation itself is refused, exactly as at load time.
    bad = added.replace("connector: it.ticketing\n    action: open_ticket", "connector: hr.record\n    action: accept_resignation", 1)
    assert not client.post("/api/workflows/exit/check", json={"yaml": bad}).json()["ok"]
    # Saving without bumping the version is refused, so running processes keep their version.
    refused = client.post("/api/workflows/exit/activate", json={"yaml": added}).json()
    assert not refused["ok"] and "version" in refused["reason"]
