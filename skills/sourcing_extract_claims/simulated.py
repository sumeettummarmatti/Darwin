"""Stand-in extractor over the *tokenised* résumé text.

Scripted behaviours, so the demo shows the defences (documented in DEMO_SCRIPT):
* for CAND-2004 it "invents" a patent claim whose quote is not in the text —
  the handler discards it because no verbatim span exists;
* its rationale for CAND-2002 echoes the education line ("top-tier institute"),
  which Devil's Advocate gate D then flags as a college-tier proxy.
"""

import re

LOCATIONS = {"bengaluru": "IN-KA", "bangalore": "IN-KA", "gurugram": "IN-HR", "gurgaon": "IN-HR", "remote, india": "remote_IN",
             "kolkata": "IN-WB", "pune": "IN-MH"}


def _find(pattern, text):
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(0) if m else None


def respond(payload, tier):
    claims, rationales = [], {}
    for c in payload.get("args.candidates", []):
        cid, text = c["id"], c["resume_text"]
        q = _find(r"\d+ years (?:building|running|on|of) distributed systems", text)
        if q:
            claims.append({"candidate": cid, "criterion": "years_distributed", "value": int(q.split()[0]), "quote": q})
        for name, code in LOCATIONS.items():
            q = _find(re.escape(name), text)
            if q:
                claims.append({"candidate": cid, "criterion": "location", "value": code, "quote": q})
                break
        for crit, pat in (("production_scale", r"(?:\d+ (?:million|billion) (?:requests|events)[^.]*|p99 latency[^.]*)"),
                          ("oss_or_patent", r"(?:maintainer of [^.]+|co-inventor on [^.]+|open-source [^.]+)"),
                          ("domain_travel_or_fintech", r"(?:payments platform|travel booking|fintech)")):
            q = _find(pat, text)
            if q:
                claims.append({"candidate": cid, "criterion": crit, "value": True, "quote": q})
        langs = [l for l in ("Go", "Rust", "Java", "Python", "Kotlin") if re.search(rf"\b{l}\b", text)]
        if langs:
            claims.append({"candidate": cid, "criterion": "languages", "value": [l.lower() for l in langs],
                           "quote": _find(r"(?:Languages|Stack): [^.]+", text) or langs[0]})
        if cid == "CAND-2004":
            claims.append({"candidate": cid, "criterion": "oss_or_patent", "value": True, "quote": "holds three granted patents in consensus"})
        rationales[cid] = f"Evidence of {len([x for x in claims if x['candidate'] == cid])} ICP criteria in the résumé."
        if cid == "CAND-2002":
            rationales[cid] += " Graduated from a top-tier institute, which suggests strong fundamentals."
    return {"claims": claims, "rationales": rationales, "confidence": 0.82}
