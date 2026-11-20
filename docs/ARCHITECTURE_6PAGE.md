# HR Autopilot — architecture (Round 1, six pages)

*Challenge 2: an AI-native HR platform for TBO. Every claim below points to code in this repository and, where it is a number, to `make bench`.*

---

## Page 1 — What we chose, and the one claim

**Depth line: onboarding.** The brief's own example — a hire is recorded, then people chase IT, Admin and Finance — and the mock APIs TBO supplies are an onboarding toolkit. **Second line: exit**, the mirror image, which carries the richest governance surface (resignation acceptance, buyouts, payroll sign-off, gratuity, DPDP retention). **Third: talent intelligence (FairHire)**, a deliberately differently-shaped line — external data, outbound contact, no employee record — built to test whether the extension model survives a shape it was not designed for. Leave and helpdesk run on the same kernel.

**The claim:** agents have no network egress. They return *proposed actions*. A governance kernel (Gatekeeper) decides whether each one happens, executes it exactly once, verifies it, prices it and writes it down. That one constraint makes the guardrails enforceable rather than aspirational.

```
 Experience   web console · chat · dashboard                    one intent API (core/intents.py)
 Agents       skills = manifest + handler, no HTTP/DB/connector  propose, never act (skills/)
 Gatekeeper        orchestrator · policy decision point · reserved gate · outbox + read-back
              PII proxy · model router + cost meter · hash-linked audit · kill switch · Devil's Advocate
 Data         system of record · policy packs · workflow defs · vault · connector SDK
 External     ticketing · assets · access cards · directory · payroll · ATS/sourcing · mail
```

**What a TBO developer touches to add a line:** a workflow (YAML), a policy pack (YAML with tests), maybe a skill. Not `core/`. The exit line, FairHire and two rehearsal lines in this repository were committed without touching `core/`; CI fails any `service-line` PR that does.

## Page 2 — Agents and the governed action flow

| Agent / skill | Tier | Job |
|---|---|---|
| `policy.compute` | 0 (code) | Every statutory and policy number: notice, gratuity, encashment, entitlements, leave, ICP score |
| `onboarding.extract_id` | 1 → 2 on a measured trigger | Is the uploaded ID legible and does it match? Unsure ⇒ human |
| `exit.prepare_packet` | 1 → 2 | Prose around rule-computed values for the human deciding |
| `helpdesk.answer` | 1 → 2 | Phrase an answer from retrieved clauses; cite clause + pack version |
| `sourcing.extract_claims` | 1 → 2 | Claims from résumés, each with a verbatim quote; no quote ⇒ discarded |
| `devils_advocate.review` | 1 | The judgement-shaped residue of the devil's-advocate check, once per run |
| `intake.screen` | 0 | Route-only lexicon for POSH / grievance / whistleblower |

**Every action walks one path** (`core/executor.py`, `core/orchestrator.py`):

1. **Propose** — a workflow step or a skill's `propose()`, limited to the step's scope.
2. **Devil's Advocate gate A** — irreversible actions only: deterministic checks first (duplicate effect, PII in payload, entitlement invariants, reserved leakage, stale policy, compensation), then a tier-1 review of the plan once per run, capped at 8% of the run budget.
3. **Policy check** — RBAC as `principal ∩ agent capability ∩ step scope`, org-unit scope, DPDP purpose of every PII token in the payload.
4. **Reserved?** — agents get `403 RESERVED` with an audit entry; reserved workflow steps become a human task with a context packet.
5. **Idempotency** — the intent is committed to the outbox under a templated key before the call.
6. **Execute** — through the connector, behind a breaker; retries reuse the key; a timeout is read back before any retry.
7. **Verify** — read back by key and expect exactly one record. A `200` is not evidence.

Each step writes an audit entry: actor (and on whose behalf), inputs as tokens, policy versions and rule IDs, prompt version, model, tier, tokens, ₹, outcome.

**Low confidence is treated as reserved.** When a skill's declared `escalate_when` still fires at its highest permitted tier, the run stops and asks one plain question, with the draft attached.

## Page 3 — Governance: policy as configuration

**Policy packs** (`policies/*.yaml`) are versioned, effective-dated and evaluated by a small, safe expression language (no `eval`; comprehensions, attribute access and imports fail at load). A pack **refuses to load** without tests, with a failing test, or with a rule that reads a prohibited criterion. Every audit entry names `pack@version` and the rule IDs that fired, so a March run replays under March's rules.

**Reserved-decision registry** (`policies/reserved_decisions.v4.yaml`) — configuration HR changes from the console, no deployment, its own tests must pass. It holds 18 reserved actions with approver roles and sequential modes, 3 route-only matters, and the agent verb allow-list. `approve`, `accept`, `reject_candidate`, `sign_off` and `decide` can never be granted: a workflow or skill that tries fails validation at load time.

**Route only, never decide.** POSH, grievance and whistleblower matters are detected by a word list and handed to the named role untouched; the packet records that the platform did not classify, summarise or recommend.

**Approval receipts** hash the exact packet the approver saw and store a snapshot. Approval binds to the hash: a packet that changed after display is refused as stale.

**Audit chain** — append-only, each entry carrying the previous hash. Editing any row breaks verification at that row (demonstrable in the console).

**Kill switch** — global, workflow, skill or connector; a database row, no restart. Paused runs park with context. A workflow whose escalation rate crosses its threshold pauses itself.

**Devil's Advocate gates B and C.** Gate B attacks a policy draft: it runs the pack's tests, generates every combination of the pack's declared adversarial inputs, checks its stated properties (for example "fixed-term notice is never below the state floor") and proposes regression tests. Gate C is the governance lint inside `hrx validate`.

## Page 4 — Compliance by design

| Requirement | Mechanism | Demonstrated by |
|---|---|---|
| DPDP purpose limitation | PII stored as rows with purpose tags; cross-purpose reads and payloads refused | Personal data → cross-purpose read; `test_purpose_limitation_*` |
| DPDP retention | Clocks start at exit; sweep deletes expired fields; statutory set held with rule cited | Exit golden run; retention table |
| DPDP access / correction | Access bundle includes every run, decision and model call about the person | `/api/dpdp/access/{id}` |
| What reaches a model | PII proxy strips undeclared and prohibited fields; names → `«PERSON_1»`; PAN/bank → vault placeholders; identifiers scrubbed from text | Payload viewer per call; `test_model_never_sees_raw_identifiers` |
| No lawful basis | `pointer_only`: link and date only; the proxy refuses any model call about the person; objection ⇒ suppression + deletion | Talent page; `test_asking_a_model_about_a_pointer_is_refused` |
| Fair hiring | Arithmetic scoring over span-backed claims; `hire.reject_candidate` reserved; gate D proxy-bias flags | Talent ranking |
| Explainability | Every action explained from the audit log, never by asking a model | Run view → audit narration |
| Access control | Triple intersection; org-unit scope | Same agent, two HRBPs, different outcomes |
| Labour law as rules | Notice (with statutory floor guard), gratuity (5 years, 15/26, ceiling), encashment, EPF, F&F timeline in tested packs | Policy packs; the model's imprecise gratuity prose next to the rule's number |
| TBO's own obligations | No-raid guard checks non-solicit clauses binding TBO and names the clause | Talent → blocked |

## Page 5 — Models, routing and cost

**Tier ladder.** Tier 0 (code) is the default for every rule-decidable step. Tier 1 (small or open-weight) is the default model tier. Tier 2 runs only on a **measured** trigger declared per skill — `confidence < threshold` over the structured output, or a schema violation after one retry — and the reason is logged with the call. Tier 3 needs a per-skill opt-in. A run that would exceed its budget downgrades, then hands to a human.

**Vendor independence.** One adapter layer (`core/router/adapters.py`); profiles in `config/routing.yaml`. The demo runs a simulated in-process profile, so no real data leaves the machine and runs are reproducible; `openai_compatible` points at any hosted or self-hosted open-weight model. Swapping is a config change; the suite stays green.

**Measured on the synthetic dataset** (`make bench`, simulated provider at a declared rate card):

| | Onboarding | Exit | Leave | Helpdesk |
|---|---|---|---|---|
| ₹ per completed run, p50 | 0.0070 | 0.0073 | 0.0000 | 0.0024 |
| Steps with no human touch | 98% | 81% | 90% | 100% |
| Steps at tier 0 | 83% | 93% | 100% | 25% |

**Projection** at placeholder volumes (2,500 staff; 40 joiners, 38 leavers, 900 leave requests and 3,750 questions a month — assumptions until TBO shares figures) is about ₹6,500 a month, almost entirely the assumed hosting. Inference is a few rupees a month at the declared rates, because most steps never reach a model.

**Threshold justification method.** Run about 200 instances per skill, compare tier-1 output with a tier-2 reference and human adjudication, plot accuracy against threshold and choose the knee. This needs a real model and has not been run; no curve is claimed.

## Page 6 — Extension model, live-test readiness, and Devil's Advocate in one panel

**Five extension points**, each with a contract and a validator: workflow, skill, connector, policy pack, reserved-registry entry. `hrx scaffold workflow <name>` writes a workflow, a pack with an empty `tests:` block (which `hrx validate` refuses) and a test spec. `hrx validate` enforces idempotency keys, model-free deterministic steps, no reserved verbs for agents, known reserved actions, and runs the governance lint. `hrx test` replays synthetic runs under an injected retry storm and fails on any duplicate side effect.

**Rehearsed, cold, in the repository.** *Leave encashment on exit, capped at 30 days, Finance sign-off above ₹50,000*: validate refused the untested pack; the lint caught a first draft paying money with no reserved step; green under the retry storm. *Probation confirmation*: a new reserved action through registry v4; its workflow test caught a window bug in the first rule. Both commits touch no `core/` file. `docs/DEVGUIDE.md` is the script.

**Devil's Advocate, measured honestly.** On a corpus of 16 planted defects and 4 clean steps, the deterministic layer catches **88% with no false alarms**. On the simulated provider the model layer adds nothing and costs 21% of run spend; it was already cut from every irreversible step to once per run when it measured 46%. With a real model we re-measure; under 20% added value, it shrinks to the deterministic pre-filter, and we will say so.

### Assumptions we state rather than hide

Demo login, not an IdP · India as the sole statutory jurisdiction · placeholder volumes · simulated model provider for the demo · statutory values marked *illustrative* await counsel · TBO's mock APIs replaced by our own stand-ins until the starter kit arrives (connectors absorb the difference).

### What we need from TBO

Volumes for the projection · the mock API contracts and seed data · the policy corpus and jurisdictions in scope · round dates and the live-test time box · whether a real IdP is expected · model and hosting constraints during judging · Legal's position on first contact with non-applicants under DPDP, which we treat as open, not solved.
