# SETU — Progress Log

Running log. Newest session at the top. Update at the end of every working session: what shipped, what was decided, what was reversed, what is open.

**Rule:** no number enters this file unless it came out of `make bench`. Estimates are labelled as estimates.

---

## Status at a glance

| | |
|---|---|
| **Phase** | 0 — Round 1 submission |
| **Next gate** | Gate 0: 6-page architecture doc + 5-min video submitted |
| **Blocking unknowns** | Round 1 deadline · team size · TBO volumes · mock API contracts |
| **Kernel decision pending** | Temporal vs own Postgres state machine (Phase 1, task 1.1) |
| **Lines of production code** | 0 — deliberately. Phase 0 is a writing and filming job |

### Gate status

| Gate | What it proves | State |
|---|---|---|
| 0 | Round 1 submitted, no unprovable claims | ⬜ open |
| 1 | Vertical slice: one step through all 7 governed-flow steps | ⬜ |
| 2 | Onboarding end to end, real ₹/run and automation rate | ⬜ |
| 3 | Reserved-decision drill clean | ⬜ |
| 4 | **Exit line added with zero `core/` commits** | ⬜ |
| 5 | Every published number reproducible by `make bench`; 3 unseen requirements rehearsed | ⬜ |

### Measurements

Empty until Gate 2. Do not pre-fill.

| Workflow | ₹/run p50 | ₹/run p95 | Automation rate | Cycle time p50 | Escalation rate | Measured on |
|---|---|---|---|---|---|---|
| Onboarding | — | — | — | — | — | — |
| Exit | — | — | — | — | — | — |
| Leave | — | — | — | — | — | — |
| Helpdesk | — | — | — | — | — | — |

| Prativaad | Value | Measured on |
|---|---|---|
| Objections per 100 workflows | — | — |
| Objection precision (upheld by human) | — | — |
| Catch rate on fault corpus | — | — |
| False-clear rate on fault corpus | — | — |
| Cost overhead (% of workflow) | — | — |

---

## Decisions

Append-only. If a decision is reversed, add a new row rather than editing the old one — the reversal is the useful information.

| # | Date | Decision | Reason | Reversed? |
|---|---|---|---|---|
| D1 | 2026-11-18 | Depth line is **onboarding**; **exit** is the second line | TBO's mock APIs are an onboarding toolkit; exit is the mirror image and carries the richest governance surface | — |
| D2 | 2026-11-18 | **Kernel-first, demo-second** | Governance + extensibility = 40%; bolting them on afterwards is visible to judges | — |
| D3 | 2026-11-18 | Agents have **no network egress**; the kernel is the only path out | Makes the non-negotiable guardrails structurally enforceable rather than aspirational | — |
| D4 | 2026-11-18 | Prativaad (devil's advocate) as a kernel component at gates A/B/C | The real risk in agentic HR is a *confidently wrong* plan, which confidence thresholds do not catch | — |
| D5 | 2026-11-18 | Prativaad capped at 8% of workflow budget; deterministic pre-filter runs first | An unbounded critic is a cost disaster, and judges will probe exactly that | — |
| D6 | 2026-11-19 | **Talent intelligence (PARAKH) is the extensibility proof, not a fourth depth line** | Brief penalises shallow coverage; a differently-shaped line is a stronger test of the extension model than exit (which is onboarding backwards) | — |
| D7 | 2026-11-19 | **No live sourcing or mail vendor.** `sourcing_mock` + `mail_mock`, synthetic profiles only | Competition rule: synthetic dataset and mock APIs only, no real personal data in any tool or model | — |
| D8 | 2026-11-19 | Sourced people with no lawful basis are **`pointer_only`** — no profile, no score, no model call | DPDP offers only consent or narrow legitimate uses; no GDPR-style legitimate-interests basis exists for non-applicants | — |
| D9 | 2026-11-19 | No-raid guard checks **TBO's** non-solicit obligations, not the candidate's freedom to move | Post-employment non-competes are void under s.27 Indian Contract Act; non-solicit clauses binding TBO are enforceable | — |
| D10 | 2026-11-19 | ICP scoring is **deterministic**; the model only returns claims with character spans | Satisfies the cost rule, the explainability guardrail and invented-qualification defence with one mechanism | — |
| D11 | 2026-11-19 | `core/` freeze CI check and the cost meter both land in **week 1**, not later | "Zero core commits" is unverifiable after the fact; a late cost meter produces estimates dressed as measurements | — |
| D12 | 2026-11-19 | Phase 0 is **documents and video only** — no production code until Gate 0 | Round 1 is shortlisted on design, governance and cost logic. Writing kernel code now optimises for a round we have not reached | — |

---

## Open questions

Owner `TBO` means we proceed on a stated assumption and swap in the real answer when it arrives.

| # | Question | Owner | Working assumption |
|---|---|---|---|
| Q1 | Round 1 deadline, team size, submission portal | TBO | Unknown — **highest priority to resolve**; the whole plan is relative until this lands |
| Q2 | Headcount, monthly hires, exits, leave and helpdesk volumes | TBO | Public estimate: ~2,500 employees, Gurgaon HQ, ~72% of headcount in South Asia. Labelled as our assumption on the slide |
| Q3 | Mock API contracts: schemas, auth, rate limits, idempotency support on their side | TBO | Connector SDK absorbs differences; contract tests from day one |
| Q4 | Which policies are in the sample pack; jurisdictions beyond India | TBO | India only for statutory rules in the demo |
| Q5 | Live extension test time box | TBO | Rehearsing to < 25 minutes |
| Q6 | IdP — demo login or real SSO expected? | TBO | Demo login; SSO documented as a connector, not built |
| Q7 | Self-hosting available during judging, or hosted endpoints expected? | TBO | Hosted OpenAI-compatible endpoints; self-hosting costed at real GPU-hour prices if used |
| Q8 | Is the sourcing line wanted at all? Legal's position on first contact with non-applicants under DPDP | TBO | Build the governance mechanisms; present the lawful-basis question as open, not solved |
| Q9 | IP and participation terms | TBO | Marked "to be confirmed before launch" in the brief |
| Q10 | Temporal vs own Postgres state machine | Us | Decide in the week-1 spike, hard date, no extension |

---

## Risks being actively watched

Only the ones that could change what we do this week. Full list in `DESIGN.md` §20.

| Risk | Current read | Trigger to act |
|---|---|---|
| Round 1 deadline closer than we think | **Unquantified — Q1 is blocking** | Resolve Q1 before anything else |
| Gate 1 slips | Not started | > 3 days late ⇒ cut PARAKH, protect Gates 4 and 5 |
| Gate 4 fails (exit needs core changes) | Not started | Stop feature work, fix the kernel |
| Prativaad adds little over the deterministic pre-filter | Unmeasured | < 20% improvement on fault corpus ⇒ shrink it, say so on the slide |
| Over-engineering the kernel, under-building the demo | Live concern given D2 | Experience is still 10%; `DESIGN.md` §16 drop order is pre-agreed |

---

## Session log

### 2026-11-19 — Talent intelligence added; planning docs written

**Shipped**
- `DESIGN.md` §4.3 — master story: one week at TBO covering every feature, with a beat-to-section coverage map. Source for the video and finale run sheet.
- `DESIGN.md` §9.5 — PARAKH: ICP scoring, lawful-basis gate, `pointer_only`, no-raid guard, governed outreach, effort table, drop rule.
- Cross-references updated: §2 service-line table, §3 scope, §16.11, §21 traceability, §22 asks, §24 sources.
- `PLAN.md` — phase plan with six gates, ownership map, critical path, pre-agreed change triggers.
- `CLAUDE.md` — ten invariants, extension-point rules, PARAKH-specific rules, PR checklist.
- `PROGRESS.md` — this file.

**Decided** — D6 through D12.

**Devil's-advocate findings that changed the design**
1. The live-data version of sourcing is forbidden outright by the data rule. Reframed to mock connectors; stated on the slide rather than letting a judge find it.
2. DPDP has no legitimate-interests basis, so the standard European sourcing design has no lawful basis in India. This would have read as *disqualifying* to a governance-weighted panel. Inverted into the `pointer_only` gate, which turns the biggest liability into the most distinctive governance feature.
3. "Poaching" risk sits on TBO's side, not the candidate's — non-competes are void, non-solicit clauses binding TBO are not. The guard was redesigned to check TBO's obligations and surface the clause ID.
4. A third depth line would cost the depth mark the brief explicitly rewards. Reframed PARAKH as the extension-model test case.
5. My own §19 week plan opened with kernel code while the actual next deliverable is the Round 1 document and video. Corrected in `PLAN.md` as Phase 0 with Gate 0.

**Open** — Q1 is blocking. Everything in `PLAN.md` is relative until the Round 1 deadline is known.

**Next session**
1. Resolve Q1 (deadline, team size, portal).
2. Draft `docs/ARCHITECTURE_6PAGE.md` against the §19 page map.
3. Draft `docs/DEMO_SCRIPT.md` video beat sheet from §4.3.
4. One architecture diagram good enough to be the only diagram.

---

### 2026-11-18 — Problem statement decoded; design doc written

**Shipped**
- Decoded all 7 pages of the TBO brief (`Building_Software_Faster.pdf`, mangled font encoding) into the compressed brief at `DESIGN.md` §1: eight objectives, non-negotiable guardrails, cost and model rule, three rounds, evaluation weights, rules.
- `DESIGN.md` v0.1 — 24 sections: service-line choice, two walkthroughs, four-plane architecture, governed action flow, governance kernel, compliance mapping, extension model, Prativaad, cost and routing, safe failure, data model, surfaces, dashboard, creative add-ons, stack, repo layout, round plan, risks, traceability matrix, asks of TBO.

**Decided** — D1 through D5.

**Key reading of the brief** — governance + extensibility (40%) equals automation + cost combined, and the brief states outright that a clever demo an HR team could not safely run, or TBO developers could not extend, will not win. Hence kernel-first.

**Open** — Q1 through Q7, Q9, Q10.
