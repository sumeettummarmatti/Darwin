# SETU — Progress Log

Running log. Newest session at the top. Update at the end of every working session: what shipped, what was decided, what was reversed, what is open.

**Rule:** no number enters this file unless it came out of `make bench`. Estimates are labelled as estimates.

---

## Status at a glance

| | |
|---|---|
| **Phase** | Build (Phases 1–5 compressed into one session on the user's instruction — see D13) |
| **Next gate** | Real model provider + TBO's mock contracts; then re-run `make bench` and the fault corpus |
| **Blocking unknowns** | Round deadlines · TBO volumes · TBO mock API contracts · real model provider for calibration |
| **Kernel decision** | Own durable state machine on SQLite (D14); workflow format unchanged |
| **Tests** | 78 passing (`make test`); `hrx validate` and `hrx test` green |

### Gate status

| Gate | What it proves | State |
|---|---|---|
| 0 | Round 1 submitted, no unprovable claims | ⬜ open — documents exist (DESIGN, docs/*); 6-pager and video not produced |
| 1 | Vertical slice: one step through all 7 governed-flow steps | ✅ every connector step: Prativaad → authorize → outbox → connector → read-back → audit → ₹ |
| 2 | Onboarding end to end, real ₹/run and automation rate | ✅ on the simulated provider (rates are a declared card, see COST.md) |
| 3 | Reserved-decision drill clean | ✅ `/api/drill`, `tests/test_governance.py` |
| 4 | **Exit line added with zero `core/` commits** | ✅ exit commit touches no `core/` file; PARAKH needed two kernel additions first (D17) |
| 5 | Every published number reproducible by `make bench`; 3 unseen requirements rehearsed | 🟨 bench ✅; one rehearsal (leave encashment) of three |

### Measurements

From `make bench`, sim profile, synthetic dataset (bench/results/latest.md). Rupees use the declared rate card.

| Workflow | ₹/run p50 | ₹/run p95 | Automation rate | Cycle time p50 | Escalation rate | Measured on |
|---|---|---|---|---|---|---|
| Onboarding | ₹0.0070 | ₹0.0225 | 98% | demo clock (not meaningful) | 11% | 9 runs |
| Exit | ₹0.0073 | ₹0.0081 | 81% | demo clock | 0% | 8 runs |
| Leave | ₹0.0000 | ₹0.0000 | 90% | demo clock | 0% | 40 runs |
| Helpdesk | ₹0.0024 | ₹0.0278 | 100% | demo clock | 0% | 32 runs |

| Prativaad | Value | Measured on |
|---|---|---|
| Objections per run (bench week) | 71 over 90 runs, mostly low-severity compensation advisories | bench |
| Objection precision (upheld by human) | 100% of resolved (resolutions are mostly kernel read-back verifications) | bench |
| Catch rate on fault corpus | 88% (rules); 88% (rules + model) | 16 planted, sim |
| False-alarm rate on clean steps | 0% | 4 clean |
| Cost overhead | 21% of run cost (cap: 8% of run budget) | bench |

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
| D12 | 2026-11-19 | Phase 0 is **documents and video only** — no production code until Gate 0 | Round 1 is shortlisted on design, governance and cost logic. Writing kernel code now optimises for a round we have not reached | Reversed by D13 |
| D13 | 2026-11-19 | Build the platform now, overnight, kernel-first | Explicit instruction from the team lead to build and push through the night. Reverses D12 | — |
| D14 | 2026-11-19 | Own durable state machine on SQLite instead of Temporal | Zero-setup `make up` for judges; state in the same DB as the record; every step persisted before and after acting so a killed process resumes (tested). Schema is plain SQL that ports to Postgres | — |
| D15 | 2026-11-19 | Default model provider is an in-process **simulated** profile with a declared rate card | No real data may reach any model; reproducible bench; provider swap stays a config change (`openai_compatible` profile exists). All rupee figures are labelled as rate-card based | — |
| D16 | 2026-11-19 | Our own record is written through the same governed executor (`hr.record` connector) | No back door: idempotency, read-back and audit apply to our writes too | — |
| D17 | 2026-11-19 | Kernel additions before PARAKH: fan-out (`foreach`) steps, read-only actions, nested PII scrubbing, gate-D and suppression hooks for skills, SoR operations for sourced people | A differently-shaped line found real gaps. Made as separate `core:` commits before the line so the line itself touches no `core/` file | — |
| D18 | 2026-11-19 | Prativaad model residue runs once per run, not before every irreversible step | Measured 46% of run spend with no catches on the sim provider; now 21%. Deterministic checks still run on every irreversible step | — |
| D19 | 2026-11-19 | Deterministic vault tokens (keyed HMAC of field + value) | Lets the kernel link a new hire to a prior contractor record (duplicate laptop) without anything outside the vault seeing the PAN | — |
| D20 | 2026-11-19 | Asset linkage uses a dedicated identity-key token, not the PAN token | Passing the PAN token to the asset system would itself breach purpose limitation | — |

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

### 2026-11-19 (night) — the platform, built

**Shipped** (all pushed to `main`, scoped commits, `core/` changes separate from service lines)
- Kernel (VIDHI): safe policy language and packs that refuse to load untested; reserved registry with load-time and run-time enforcement; hash-linked audit; PII proxy and deterministic vault; model router with measured escalation and per-call ₹ metering; governed executor (outbox, same-key retries, read-back verification, breaker); human queue with context packets and hash-bound receipts; durable orchestrator (scheduled steps, fan-out, saga, kill-switch parking, workflow circuit breaker); Prativaad gates A–D; DPDP retention, DSR, consent, suppression; intent API; metrics with drill-downs.
- Service lines on extension points: onboarding, exit, leave, helpdesk, PARAKH (sourcing, reply, assess-probe), leave encashment (added cold with hrx as the extension rehearsal).
- Console (React + Vite): overview, demo story, workflows with the run rail, decisions and receipts, chat, talent, guardrails, policy packs with gate-B review, personal-data payload viewer, audit chain.
- `hrx` scaffold / validate / test; `make bench` + fault corpus; 78 tests; Makefile, Dockerfile, CI with core-freeze and licence audit; README, DEVGUIDE, GOVERNANCE, COST, DEMO_SCRIPT.

**Found and fixed along the way** (each in its own commit)
- Bad facts crashed evaluation instead of failing closed; audit hash broke on SQLite int→REAL round trip; names scrubbed before emails left the domain visible; Prativaad crashed when it could not read to verify (now waits); a crashing skill stalled its run (now routes to a human); a band exception approved without a band broke payroll templating (found by the bench).

**Honest results** — Prativaad's model layer adds nothing on the sim provider; overhead 21% of (very small) run cost. Helpdesk is 25% tier 0 by nature. Cycle times are demo-clock artefacts.

**Open**
1. Run the bench and fault corpus against a real tier-1 model (`openai_compatible`), then decide on Prativaad's model layer (PLAN §10 trigger: < 20% added ⇒ shrink).
2. Two more cold rehearsals of the live extension test (only leave encashment done).
3. Round 1 6-pager and video (`docs/DEMO_SCRIPT.md` has the beat sheet).
4. Threshold calibration curve needs a real model — not claimed.
5. Slack/Teams adapters: the chat surface uses the intent API, but no Bolt adapter is wired (no real workspace allowed).


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
