"""Stand-in reviewer. It does not invent objections, so on the fault corpus it adds nothing over
the deterministic layer — which is exactly what the bench reports. With a real model, measure again."""


def respond(payload, tier):
    return {"verdict": "CLEAR", "objections": [], "confidence": 0.74}
