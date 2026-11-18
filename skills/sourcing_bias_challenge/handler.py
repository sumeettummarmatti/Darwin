"""Fair-hiring challenge: surface proxies, decide nothing."""


def run(ctx):
    rationales = {r["candidate_id"]: r.get("rationale", "") for r in ctx.input("args.ranking") or []}
    return {"flags": ctx.challenge_rationales(rationales)}
