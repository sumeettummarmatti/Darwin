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

    if person_id is None:
        return {**base, "reply": "I can only act for employees with a record. Please use the console."}
    subject = kernel.sor.person(person_id)

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
        if run["status"] == "completed":
            reply = (f"Booked: {slots['days']} day(s) of {slots['leave_type']} leave from {slots['start_date']}. "
                     f"Balance after: {evaluation.get('balance_after')}. ({evaluation.get('policy')} {', '.join(evaluation.get('rule_ids', []))})")
        else:
            route = evaluation.get("route")
            who = "your manager" if route == "manager" else "the HR Head as a policy exception"
            reply = (f"I've sent {slots['days']} day(s) of {slots['leave_type']} leave from {slots['start_date']} to {who} — "
                     f"{evaluation.get('reason')}. ({evaluation.get('policy')} {', '.join(evaluation.get('rule_ids', []))})")
        return {**base, "run_id": run_id, "slots": slots, "reply": reply}

    kind = "leave_balance" if intent == "helpdesk.leave_balance" else "policy"
    run_id = kernel.orchestrator.start("helpdesk", subject_id=person_id, principal=user, channel=channel,
                                       inputs={"person_id": person_id, "question": text, "kind": kind})
    run = kernel.orchestrator.run(run_id)
    steps = kernel.orchestrator.steps(run_id)
    step = steps["leave_balance" if kind == "leave_balance" else "answer"]
    out = step["outputs"] or {}
    if step["status"] != "done":
        return {**base, "run_id": run_id, "reply": "I'm not confident enough to answer that from policy. I've passed it to HR with the clauses I found.",
                "escalated": True}
    return {**base, "run_id": run_id, "reply": out.get("answer"), "citations": out.get("citations", []),
            "tier": step["tier"], "cost_inr": round(run["cost_inr"], 5), "retrieval_support": out.get("retrieval_support")}
