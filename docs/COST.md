# Cost — method, measurements, projection

**Rule we follow:** no number appears here unless it came out of `make bench`. Assumptions are labelled as assumptions.

## Method

Every model call goes through `core/router/router.py`, which records tokens in and out, the tier, the model, and the rupee cost from the active profile's rate card (`config/routing.yaml`). Connector calls are metered at their declared per-call cost (zero for the mocks). A run's cost is the sum over its steps; the dashboard reports p50 and p95 over completed runs, and every rupee drills to the step and the audit entry that spent it.

```
cost per completed run = Σ model calls (tokens_in × rate_in + tokens_out × rate_out)
                       + Σ connector calls × declared cost
monthly projection     = measured ₹/run (p50) × assumed runs per month + assumed hosting
```

**Tier ladder.** Tier 0 is code (rules engine, date maths, routing, entitlements, scoring) and is the default. Tier 1 is a small model, the default *model* tier. A skill moves to tier 2 only when its declared `escalate_when` expression fires on the structured output, or after a schema violation and one retry, and the reason is recorded with the call. Tier 3 requires a per-skill opt-in. A run that would exceed its `budget_inr_per_run` downgrades, then hands to a human.

**What the simulated provider means for these numbers.** The default `sim` profile runs in process. Token counts are estimated at about four characters per token, and rupees come from a declared rate card in the range of hosted open-weight models. Replace the rate card with an invoice rate, or switch to `openai_compatible`, and re-run `make bench`: every figure recomputes. The *shape* — what share of steps ever reach a model — does not depend on the provider.

## Measured (make bench, sim profile)

| Line | Completed / runs | ₹/run p50 | ₹/run p95 | Tier-0 share of steps |
|---|---|---|---|---|
| Onboarding | 9 / 9 | ₹0.0070 | ₹0.0225 | 83% |
| Exit | 8 / 8 | ₹0.0073 | ₹0.0081 | 93% |
| Leave | 40 / 40 | ₹0.0000 | ₹0.0000 | 100% |
| Helpdesk | 32 / 32 | ₹0.0024 | ₹0.0278 | 25% |
| Sourcing | 1 / 1 | ₹0.0156 | ₹0.0156 | 91% |

Helpdesk p95 is the Form 16 question: retrieval support was low, tier 1's confidence fell under 0.7, and the router moved to tier 2 — the measured trigger, logged with the call.

## Prativaad: measured, and shrunk once already

| | Value |
|---|---|
| Fault corpus | 16 planted defects, 4 clean steps (`tests/fault_corpus/cases.yaml`) |
| Caught by the deterministic layer | 88% |
| Caught by rules + model | 88% |
| Model-only catches | 0 |
| Judgement-only defects caught | 0 of 2 |
| False alarms on clean steps | 0% |
| Cost in the bench week | ₹0.0806, 21% of total run cost |

Two honest findings:

1. **The model layer adds nothing on the simulated provider.** The two defects no rule can see (a laptop for a withdrawn offer; a second outreach inside the cooling-off window) are exactly what a real model would be asked about, and the simulated reviewer does not catch them. With a real tier-1 model, re-run the corpus; if it still adds under 20% over the rules, the plan (`PLAN.md` §10) is to shrink the model layer to the pre-filter and say so.
2. **Overhead.** Running the model review before every irreversible step cost 46% of run spend. It now reviews the plan once per run, which measured 21% in the bench week. It stays under its cap (8% of each run's *budget*), but as a share of very cheap runs it is high, and we report that rather than redefine the denominator.

## Projection at TBO's volumes (assumptions)

Volumes are placeholders until TBO shares figures (`config/costs.yaml`): about 2,500 employees, 40 joiners and 38 leavers a month, 900 leave requests, 3,750 helpdesk questions. Hosting is assumed at ₹6,500 a month for one small VM.

| Line | Runs / month (assumed) | Measured ₹/run | ₹ / month incl. hosting share |
|---|---|---|---|
| Onboarding | 40 | ₹0.0070 | ₹55 |
| Exit | 38 | ₹0.0073 | ₹53 |
| Leave | 900 | ₹0.0000 | ₹1,237 |
| Helpdesk | 3,750 | ₹0.0024 | ₹5,164 |
| **Total** | | | **≈ ₹6,510** |

Nearly all of it is the assumed hosting. Inference at these volumes is a few rupees a month on the declared rate card. If a real provider's rates were ten times higher, inference would be about a hundred rupees a month. The design choice that makes this true is that 83–100% of steps in the transactional lines never reach a model; the helpdesk, whose job is answering in words, is the exception at 25%.

## Calibrating the escalation thresholds

Thresholds (`confidence < 0.7` for helpdesk, `< 0.8` for ID checks) are declared per skill. The calibration method in `DESIGN.md` §11.2 — run about 200 instances, compare tier-1 outputs to a tier-2 reference and human adjudication, plot accuracy against threshold, pick the knee — needs a real model to mean anything. It has not been run, and no calibration curve is claimed.
