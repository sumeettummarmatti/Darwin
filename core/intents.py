"""The intent API — one entry point behind every conversational surface.

Web chat, Slack and Teams are thin adapters over ``handle``; the kernel cannot
tell them apart except by the ``channel`` field in the audit log. Intent
recognition is rules-first (the ``intents`` pack); no model is needed to
recognise "I want to resign".
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from core.audit import AuditEntry

if TYPE_CHECKING:
    from core.kernel import Kernel

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def parse_leave(text: str, today: date) -> dict[str, Any]:
    """Deterministic slot filling for leave requests. Defaults are explicit and echoed back."""
    lower = text.lower()
    leave_type = "sick" if "sick" in lower else "earned" if ("earned" in lower or "vacation" in lower) else "casual"
    days = 1
    match = re.search(r"(\d+|" + "|".join(_NUMBERS) + r")\s+(?:working\s+)?days?", lower)
    if match:
        token = match.group(1)
        days = int(token) if token.isdigit() else _NUMBERS[token]
    elif " and " in lower and any(d in lower for d in _WEEKDAYS):
        days = sum(1 for d in _WEEKDAYS if d in lower)
    start = today + timedelta(days=1)
    if "today" in lower:
        start = today
    for index, name in enumerate(_WEEKDAYS):
        if name in lower:
            ahead = (index - today.weekday()) % 7 or 7
            start = today + timedelta(days=ahead)
            break
    iso = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if iso:
        start = date.fromisoformat(iso.group(0))
    return {"leave_type": leave_type, "days": days, "start_date": start.isoformat()}


def handle(kernel: "Kernel", user_id: str, text: str, channel: str = "web") -> dict[str, Any]:
    user = kernel.principal(user_id)
    profile = next((u for u in kernel.users() if u["id"] == user_id), {})
    person_id = profile.get("person_id")
    decision = kernel.pdp.evaluate("intents", {"text": text}, actor=user.label)
    intent = decision.outputs.get("intent")
    base = {"intent": intent, "rule_ids": decision.rule_ids, "policy": decision.pack_ref, "channel": channel}
    kernel.audit.append(AuditEntry(actor=user.label, action="intent.received", kind="step", outcome="ok",
                                   policy_versions=[decision.pack_ref], rule_ids=decision.rule_ids,
                                   inputs={"channel": channel, "intent": intent, "chars": len(text)}))

    if intent == "route_only":
        action = decision.outputs["action"]
        role = kernel.registry.reserved.route_only[action]
        item = kernel.queue.create(
            kind="route_only", title=f"Route only · {action}", action=action, approver_roles=[role],
            question=f"Acknowledge receipt by the {role.replace('_', ' ')}; the matter is handled outside the platform.",
            packet={"summary": "Route-only matter received through chat. The platform has not classified, scored or summarised it.",
                    "matter_text": text, "visible_to": [role], "reported_by": user.id, "channel": channel,
                    "platform_did": ["matched a route-only lexicon rule", "stopped", "handed off"],
                    "platform_did_not": ["classify", "summarise", "recommend", "notify anyone named"],
                    "clauses": [{"pack": decision.pack_ref, "rule_ids": decision.rule_ids}]})
        return {**base, "reply": f"Thank you for telling us. This has been passed, as you wrote it, to the {role.replace('_', ' ')} — "
                                 "no one else, and no automated system has assessed it. They will contact you directly.",
                "queue_id": item["id"]}

    first_name = (profile.get("name") or "there").split()[0]
    if intent == "greeting":
        return {**base, "tier": 0, "reply": (
            f"Hi {first_name}! I can check your leave balance, book leave, tell you where your joining stands, "
            "and answer HR policy questions like what to bring on day one. Anything sensitive, like a complaint, "
            "goes privately to the right person.")}

    if person_id is None:
        return {**base, "reply": "I can only act for employees with a record. Please use the console."}
    subject = kernel.sor.person(person_id)

    if intent == "self.profile":
        return {**base, "tier": 0, "reply": _profile_reply(subject),
                "citations": [{"source": "system_of_record", "field": "employee record"}]}

    if intent == "onboarding.status":
        return {**base, "tier": 0, **_onboarding_status(kernel, person_id, subject)}

    if intent == "exit.resign":
        hrbp = kernel.principal(subject["attrs"].get("hrbp_id", "USR-101"))
        run_id = kernel.orchestrator.start("exit", subject_id=person_id, principal=hrbp, channel=channel,
                                           inputs={"person_id": person_id, "letter_text": text, "requested_last_day": None})
        return {**base, "run_id": run_id,
                "reply": "Your resignation has been received. I have prepared the notice-period and settlement details for your manager "
                         "and HR. Nothing is final until they accept it — you will hear back here."}

    if intent == "leave.apply":
        slots = parse_leave(text, date.fromisoformat(kernel.clock.today()))
        run_id = kernel.orchestrator.start("leave", subject_id=person_id, principal=user, channel=channel,
                                           inputs={"person_id": person_id, **slots})
        run = kernel.orchestrator.run(run_id)
        steps = kernel.orchestrator.steps(run_id)
        evaluation = (steps["evaluate"]["outputs"] or {})
        days = slots["days"]
        day_word = "day" if days == 1 else "days"
        # The rule reference travels as a citation, so the reply itself stays plain.
        rules = [{"clause": f"leave rules ({', '.join(evaluation.get('rule_ids', []))})", "pack": evaluation.get("policy")}]
        if run["status"] == "completed":
            left = evaluation.get("balance_after")
            left_text = f" You have {left:g} {slots['leave_type']} days left." if isinstance(left, (int, float)) else ""
            reply = f"Done. {days} {day_word} of {slots['leave_type']} leave booked from {slots['start_date']}.{left_text}"
        else:
            route = evaluation.get("route")
            who = "your manager" if route == "manager" else "the HR Head as an exception"
            reply = (f"I've sent your request for {days} {day_word} of {slots['leave_type']} leave from {slots['start_date']} "
                     f"to {who} ({evaluation.get('reason')}). You'll hear back here.")
        return {**base, "run_id": run_id, "slots": slots, "reply": reply, "citations": rules}

    kind = "leave_balance" if intent == "helpdesk.leave_balance" else "policy"
    run_id = kernel.orchestrator.start("helpdesk", subject_id=person_id, principal=user, channel=channel,
                                       inputs={"person_id": person_id, "question": text, "kind": kind})
    run = kernel.orchestrator.run(run_id)
    steps = kernel.orchestrator.steps(run_id)
    step = steps["leave_balance" if kind == "leave_balance" else "answer"]
    out = step["outputs"] or {}
    if step["status"] != "done":
        return {**base, "run_id": run_id, "escalated": True, "reply": (
            "I couldn't answer that confidently from HR policy, so I've passed it to HR and they'll reply here. "
            "I can help with leave, your joining, notice periods and other policy questions.")}
    return {**base, "run_id": run_id, "reply": out.get("answer"), "citations": out.get("citations", []),
            "tier": step["tier"], "cost_inr": round(run["cost_inr"], 5), "retrieval_support": out.get("retrieval_support")}


# ── answers from the record (tier 0: no model) ────────────────────────────────

def _profile_reply(subject: dict[str, Any]) -> str:
    a = subject.get("attrs", {})
    parts = [f"You're {subject.get('display_name')}"]
    if a.get("role_title"):
        parts[0] += f", {a['role_title']}"
    if a.get("org_unit"):
        parts[0] += f" in {a['org_unit']}"
    lines = [parts[0] + "."]
    if a.get("manager_name"):
        lines.append(f"Your manager is {a['manager_name']}.")
    if a.get("buddy_name"):
        lines.append(f"Your buddy is {a['buddy_name']}.")
    if a.get("status") == "pre_joining" and a.get("date_of_joining"):
        lines.append(f"You join on {a['date_of_joining']}.")
    return " ".join(lines)


_ONBOARDING_ITEMS = [("allocate_laptop", "Laptop"), ("issue_access_card", "Access card"),
                     ("create_account", "Email account"), ("schedule_induction", "Induction")]
_DONE_WORD = {"allocate_laptop": "issued", "issue_access_card": "issued", "create_account": "created", "schedule_induction": "booked"}
_STEP_WORDS = {"done": "ready", "skipped": "not needed", "awaiting_human": "waiting for HR", "scheduled": "scheduled",
               "pending": "not started yet", "running": "in progress", "failed": "delayed, HR is on it",
               "refused": "on hold, HR is on it"}


def _onboarding_status(kernel: "Kernel", person_id: str, subject: dict[str, Any]) -> dict[str, Any]:
    row = kernel.store.one("SELECT id FROM workflow_runs WHERE workflow='onboarding' AND subject=? ORDER BY created_at DESC LIMIT 1",
                           (person_id,))
    if not row:
        when = subject.get("attrs", {}).get("date_of_joining")
        return {"reply": "Your joining hasn't started yet. HR starts it once your offer is accepted"
                         + (f", ahead of your first day on {when}." if when else ".")}
    steps = kernel.orchestrator.steps(row["id"])
    lines = []
    for step_id, label in _ONBOARDING_ITEMS:
        st = steps.get(step_id)
        if not st:
            continue
        word = _DONE_WORD[step_id] if st["status"] == "done" else _STEP_WORDS.get(st["status"], st["status"].replace("_", " "))
        out = st.get("outputs") or {}
        serial = (out.get("response") or {}).get("serial") if isinstance(out.get("response"), dict) else None
        if st["status"] == "scheduled" and st.get("scheduled_for"):
            word = f"scheduled for {str(st['scheduled_for'])[:10]}"
        lines.append(f"{label}: {word}{f' ({serial})' if serial and step_id == 'allocate_laptop' else ''}.")
    waiting = any(s["status"] == "awaiting_human" for s in steps.values())
    tail = " One item is waiting for HR to check something; you don't need to do anything." if waiting else ""
    return {"reply": "Here's where your joining stands. " + " ".join(lines) + tail, "run_id": row["id"],
            "citations": [{"source": "onboarding process", "field": "joining status"}]}
