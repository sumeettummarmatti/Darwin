"""Grounded helpdesk answers. Retrieval is keyword scoring over policy clauses (tier 0);
the model phrases the answer and reports how well the clauses support it."""

import re


def _terms(text):
    return set(re.findall(r"[a-z0-9]+", (text or "").lower())) - {"the", "a", "i", "do", "to", "on", "my", "what", "is", "of", "for", "in", "need", "me", "how"}


def run(ctx):
    question = ctx.input("args.question") or ""
    asked = _terms(question)
    scored = []
    for pack in ctx.manifest.get("retrieval_packs", []):
        for clause in ctx.clauses(pack):
            keywords = " ".join(clause.get("keywords", []))
            overlap = asked & (_terms(keywords) | _terms(clause.get("title", "")))
            phrase_hits = sum(1 for k in clause.get("keywords", []) if k in question.lower())
            score = (len(overlap) + 2 * phrase_hits) / max(len(asked), 1)
            if score > 0:
                scored.append((min(score, 1.0), clause))
    scored.sort(key=lambda s: -s[0])
    top = scored[:2]
    support = round(top[0][0], 2) if top else 0.0
    retrieved = [{"clause": c["id"], "pack": c["pack"], "title": c.get("title"), "text": c["text"]} for _, c in top]
    out = ctx.ask_model({"args.retrieved": retrieved, "args.retrieval_support": support})
    return {**out, "retrieval_support": support}
