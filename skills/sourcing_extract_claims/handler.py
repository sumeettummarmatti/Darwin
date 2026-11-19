"""Claims with spans. A claim whose quote cannot be found verbatim in the source is discarded."""


def run(ctx):
    candidates = ctx.input("args.candidates") or []
    candidates = [{"id": c.get("candidate_id") or c.get("id"), "display_name": c.get("display_name"),
                   "resume_text": c.get("resume_text") or ""} for c in candidates]
    texts = {c["id"]: c["resume_text"] for c in candidates}
    # The model sees ids and résumé text only; names in the text become placeholders.
    out = ctx.ask_model({"args.candidates": [{"id": c["id"], "resume_text": c["resume_text"]} for c in candidates]},
                        names=[c["display_name"] for c in candidates if c.get("display_name")])
    kept, discarded = [], []
    for claim in out.get("claims", []) if isinstance(out.get("claims"), list) else []:
        if not isinstance(claim, dict):
            continue
        text = texts.get(claim.get("candidate"), "")
        quote = str(claim.get("quote") or "")
        start = text.find(quote) if quote else -1
        if start < 0:
            discarded.append({**claim, "reason": "quote not found verbatim in the source — discarded"})
            continue
        kept.append({**claim, "span": [start, start + len(quote)], "source": "ats_resume"})
    return {"claims": kept, "discarded": discarded, "rationales": out.get("rationales", {}), "confidence": out.get("confidence", 0)}
