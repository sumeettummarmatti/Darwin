"""No-raid guard: the constraint is on TBO, not on the candidate's freedom to move."""


def run(ctx):
    cleared_pointers, cleared_applicants, blocked = [], [], []
    for item in ctx.input("args.pointers") or []:
        p = item["pointer"]
        d = ctx.policy("no_raid", {"current_employer": p.get("org_hint")})
        if d.outputs["verdict"] == "clear":
            cleared_pointers.append(item)
        else:
            blocked.append({"ref": p["source_id"], "kind": "pointer", "public_url": p["public_url"], "employer": p.get("org_hint"),
                            "clause": d.outputs["clause"], "reason": d.outputs["reason"], "rules": d.rule_ids,
                            "exception": "sourcing.restricted_exception (reserved to Legal + HR Head)"})
    for a in ctx.input("args.applicants") or []:
        d = ctx.policy("no_raid", {"current_employer": a.get("current_employer")})
        if d.outputs["verdict"] == "clear":
            cleared_applicants.append(a)
        else:
            blocked.append({"ref": a["candidate_id"], "kind": "applicant", "employer": a.get("current_employer"),
                            "clause": d.outputs["clause"], "reason": d.outputs["reason"], "rules": d.rule_ids,
                            "exception": "sourcing.restricted_exception (reserved to Legal + HR Head)"})
    return {"cleared_pointers": cleared_pointers, "cleared_applicants": cleared_applicants, "blocked": blocked}
