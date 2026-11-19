"""ICP scoring is arithmetic in the icp pack. This handler only gathers facts and explains."""

FACTS = ("years_distributed", "location", "production_scale", "oss_or_patent", "domain_travel_or_fintech", "languages")
WEIGHTS = {"production_scale": "w_production_scale", "oss_or_patent": "w_oss_or_patent", "domain_travel_or_fintech": "w_domain",
           "languages": "w_language", "years_distributed": "w_years"}


def run(ctx):
    claims = ctx.input("args.claims") or []
    rationales = ctx.input("args.rationales") or {}
    if not isinstance(rationales, dict):          # real models sometimes return a list of {candidate, text}
        rationales = {r.get("candidate") or r.get("id"): r.get("rationale") or r.get("text", "")
                      for r in rationales if isinstance(r, dict)}
    ranking, below = [], []
    for a in ctx.input("args.applicants") or []:
        mine = [c for c in claims if c["candidate"] == a["candidate_id"]]
        facts = {c["criterion"]: c["value"] for c in mine if c["criterion"] in FACTS}
        d = ctx.policy("icp", facts)
        breakdown = [{"criterion": c["criterion"], "value": c["value"], "weight_rule": WEIGHTS.get(c["criterion"]),
                      "contributes": d.outputs.get(WEIGHTS.get(c["criterion"], ""), None), "evidence": c["quote"],
                      "span": c["span"], "source": c["source"]} for c in mine]
        entry = {"candidate_id": a["candidate_id"], "display_name": a["display_name"], "score": d.outputs["score"],
                 "must_have_met": d.outputs["must_have_met"], "breakdown": breakdown, "rules": d.rule_ids,
                 "rationale": str(rationales.get(a["candidate_id"]) or "")}
        ranking.append(entry)
        if not d.outputs["must_have_met"]:
            below.append(a["candidate_id"])
            # The agent "helpfully" proposes rejecting her. hire.reject_candidate is reserved:
            # the kernel refuses with 403 and records it. A human rejects, with a reason.
            ctx.propose("hire.reject_candidate", {"candidate_id": a["candidate_id"], "reason": "misses must-haves"})
    ranking.sort(key=lambda r: (-int(r["must_have_met"]), -r["score"]))
    for position, r in enumerate(ranking, start=1):
        r["position"] = position
    return {"ranking": ranking, "below_must_haves": below}
