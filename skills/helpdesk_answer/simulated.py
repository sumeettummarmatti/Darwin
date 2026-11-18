"""Stand-in model: phrases the top clause; confidence tracks retrieval support.
A mid-tier model is simulated as better at reconciling partial matches."""


def respond(payload, tier):
    clauses = payload.get("args.retrieved") or []
    support = float(payload.get("args.retrieval_support") or 0)
    if not clauses:
        return {"answer": "I could not find a policy clause that answers this. I have passed it to HR.", "citations": [], "confidence": 0.2}
    top = clauses[0]
    answer = top["text"]
    if len(clauses) > 1 and tier >= 2:
        answer += " " + clauses[1]["text"]
    confidence = round(min(0.95, support * 0.95), 2) if tier == 1 else round(min(0.95, support + 0.4), 2)
    return {"answer": answer, "citations": [{"clause": c["clause"], "pack": c["pack"]} for c in clauses[: (2 if tier >= 2 else 1)]],
            "confidence": confidence}
