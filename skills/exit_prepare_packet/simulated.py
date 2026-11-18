"""Deterministic stand-in for a tier-1 model. Receives the tokenised payload only.

The gratuity explanation is deliberately imprecise (a common misreading of the
'4 years 240 days' case law), so the demo can show the rules engine's number
acting while the model's prose is merely shown. With a real provider the same
property holds: the model's text never changes a computed value.
"""


def respond(payload, tier):
    name = payload.get("subject.display_name", "the employee")
    notice = payload.get("steps.compute_notice.notice_days")
    lwd = payload.get("steps.compute_notice.last_working_day")
    years = payload.get("steps.compute_settlement_preview.service_years_completed")
    eligible = payload.get("steps.compute_settlement_preview.gratuity_eligible")
    total = payload.get("steps.compute_settlement_preview.settlement_total")
    requested = payload.get("inputs.requested_last_day")
    shortfall = payload.get("steps.compute_notice.shortfall_days") or 0
    summary = (f"{name} ({payload.get('subject.grade')}) has resigned. Notice under policy is {notice} days, "
               f"giving a last working day of {lwd}. Completed service: {years} years; "
               f"settlement preview ₹{total:,}." if isinstance(total, int) else f"{name} has resigned.")
    if requested and shortfall:
        summary += f" They have asked to leave on {requested}, {shortfall} days short of notice — a buyout decision for HR."
    return {
        "summary": summary,
        "recommendation": "Suggest accepting with the policy last working day" + (" and routing the early-release request to the HR Head as a buyout decision." if shortfall else "."),
        "confidence": 0.86 if tier == 1 else 0.93,
        "reasoning": "Values taken verbatim from compute_notice and compute_settlement_preview.",
        "gratuity_explanation": "Gratuity is a statutory lump sum for long service; it generally becomes payable once an employee has completed about four years and 240 days of continuous service." + ("" if eligible else ""),
    }
