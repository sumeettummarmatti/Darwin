"""Generic policy evaluation. Every statutory number in HR Autopilot is produced here, by rule."""


def run(ctx):
    pack = ctx.input("args.pack")
    facts = ctx.input("args.facts") or {}
    decision = ctx.policy(pack, facts)
    return {**decision.outputs, "policy": decision.pack_ref, "rule_ids": decision.rule_ids}
