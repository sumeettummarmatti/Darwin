"""Stand-in model: confidence follows the synthetic scan quality score."""


def respond(payload, tier):
    quality = float(payload.get("args.scan_quality") or 0)
    text = payload.get("args.scan_text") or ""
    name = payload.get("subject.display_name") or ""
    matches = bool(name) and name in text
    confidence = round(min(0.97, quality + (0.08 if tier >= 2 else 0)), 2)
    return {"legible": quality >= 0.6, "name_matches": matches, "confidence": confidence,
            "reasoning": "Characters partially missing in the number field." if quality < 0.6 else "Text is clear; name matches the record."}
