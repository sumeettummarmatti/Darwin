"""The lawful-basis gate. Runs before anything else touches a sourced person."""


def run(ctx):
    store_fields = sorted(ctx.lookup_policy_table("sourcing_basis", "pointer_store_fields"))
    pointers, eligible, refused, decisions = [], [], [], []
    suppressed = 0
    for signal in ctx.input("args.signals") or []:
        if ctx.is_suppressed(signal["public_url"]):
            suppressed += 1            # objected before: never stored again, not even counted by name
            continue
        d = ctx.policy("sourcing_basis", {"source": signal["source"]})
        decisions.append({"source_id": signal["source_id"], "source": signal["source"], "mode": d.outputs["mode"], "rules": d.rule_ids})
        if d.outputs["mode"] == "pointer_only":
            pointer = {k: signal.get(k) for k in store_fields}      # nothing derived, nothing else kept
            pointers.append({"pointer": pointer, "store_fields": store_fields, "expire_after_days": d.outputs["expire_after_days"]})
        else:
            refused.append({"source_id": signal["source_id"], "reason": d.outputs["note"]})
    for applicant in ctx.input("args.applicants") or []:
        d = ctx.policy("sourcing_basis", {"source": applicant["source"]})
        decisions.append({"source_id": applicant["candidate_id"], "source": applicant["source"], "mode": d.outputs["mode"], "rules": d.rule_ids})
        if d.outputs["may_score"]:
            eligible.append({**applicant, "basis": d.outputs["basis"]})
        else:
            refused.append({"source_id": applicant["candidate_id"], "reason": d.outputs["note"]})
    return {"pointers": pointers, "eligible": eligible, "refused": refused, "suppressed": suppressed, "decisions": decisions}
