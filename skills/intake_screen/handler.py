"""Route-only screening. A word match, by design: anything smarter would be classification."""


def run(ctx):
    text = ctx.input("args.text") or ""
    decision = ctx.policy("intents", {"text": text})
    route_only = decision.outputs.get("intent") == "route_only"
    if not route_only:
        # A resignation letter matches IN-001 first; screen each sentence for route-only triggers too.
        for sentence in [s for s in text.replace("\n", ". ").split(".") if s.strip()]:
            d = ctx.policy("intents", {"text": sentence})
            if d.outputs.get("intent") == "route_only":
                decision, route_only = d, True
                break
    return {
        "route_only": route_only,
        "action": decision.outputs.get("action") if route_only else None,
        "rule_id": decision.rule_ids[0] if route_only and decision.rule_ids else None,
    }
