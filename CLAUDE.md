# CLAUDE.md — working rules for this repo

Read this before writing any code in SETU. `DESIGN.md` is the architecture; `PLAN.md` is the order; this file is the set of rules you do not get to break.

This is a hackathon entry judged on **governance (20%), extensibility (20%), automation depth (20%), cost (15%), engineering quality (15%), experience (10%)**. A clever shortcut that breaks an invariant below costs more than the feature is worth. One wrong automation is disqualifying.

---

## The ten invariants

Violating any of these is a bug, not a trade-off. If a task seems to require it, stop and say so instead.

1. **Agents have no network egress.** An agent returns *proposed actions* as structured objects. The kernel executes them. Never give a skill an HTTP client, an SMTP client, a DB write or a connector handle.
2. **Everything reaches the outside world through `core/`.** No exceptions, no fast path, no "just for the demo."
3. **Reserved verbs are never granted.** `approve`, `accept`, `reject_candidate`, `sign_off`, `decide` cannot be in a skill's `capabilities` or a workflow step with an agent principal. Validation must fail at load time, not at run time.
4. **Every side-effecting action carries an idempotency key**, templated in the workflow definition. No key, no execution.
5. **Policy lives in `policies/*.yaml`, never in a prompt and never in an `if`.** If you are about to encode a notice period, a leave rule, an eligibility check or a statutory timeline in Python or in prompt text, you are in the wrong file.
6. **A step marked `deterministic: true` must not call a model.** The validator enforces it. Rule-based work in a model call is a scored failure, not a style preference.
7. **All model calls go through the router and the PII proxy.** Never import a provider SDK outside `core/router/`. Never construct a prompt containing a raw PII field.
8. **A `pointer_only` record is never profiled, scored, ranked, enriched, or sent to a model.** Not even to "check if they're relevant." See §PARAKH below.
9. **Every kernel step emits an audit entry** with actor, inputs, policy pack versions, rule IDs, prompt version, model ID, tokens, INR, outcome. An action with no audit entry did not happen correctly.
10. **Synthetic data only.** No real personal data in any tool, model, log, test fixture, screenshot or commit — including while debugging. This is a stated competition rule, not a preference.

---

## Where code goes

```
core/        kernel. FROZEN during service-line work. CI blocks PRs labelled
             `service-line` that touch it.
workflows/   declarative YAML. A new service line lives mostly here.
skills/      agent skills: manifest.yaml + handler. Additive only.
connectors/  external adapters implementing the SDK interface.
policies/    rule packs + reserved registry. Must ship `tests:`.
tools/hrx/   scaffold | validate | test
tests/       policy · contract · property · chaos · replay · fault_corpus
bench/       cost + automation measurement harness
```

**Before adding a file, ask which extension point it belongs to.** If the answer is "none, it needs to go in `core/`", that is a design finding — raise it rather than quietly widening the kernel. The whole product claim is that service lines do not require core changes.

---

## Adding a service line

The expected diff shape, in order:

1. `policies/<line>.vN.yaml` — rules, with `tests:` populated. **A pack with no tests does not load.**
2. `policies/reserved_decisions.vN.yaml` — new reserved entries if the line has decisions with legal, financial or human consequence.
3. `workflows/<line>.vN.yaml` — steps, dependencies, idempotency keys, `compensation:`, `reserved:` flags, `budget_inr_per_run`.
4. `skills/<new>/` — only if an existing skill cannot be reused.
5. `connectors/<new>/` — only if a genuinely new external system.
6. `tests/workflows/<line>.spec` — golden run + retry storm.

Then `hrx validate && hrx test`. If you touched `core/`, explain why in the PR body; the default answer is that you should not have.

---

## Cost rules

- **Tier 0 (code) is the default.** Reach for a model only when a rule genuinely cannot decide. Target ≥ 70% of steps at tier 0.
- **Tier 1 (small/open-weight) is the default model tier.** Classification, extraction, drafting, packet assembly.
- **Tier 2 only on a measured trigger** declared in the skill manifest — confidence, retrieval support, complexity or self-consistency disagreement. Never "this seems hard."
- **Tier 3 needs an explicit per-skill opt-in.** Target < 1% of calls.
- Every model call is metered. Never bypass the meter to "test quickly" — an unmetered call is an unexplainable rupee later.
- Skill manifests declare `inputs:` precisely. The PII proxy strips everything undeclared, so a wide manifest is a privacy bug and a cost bug at once.

---

## Prompts and models

- Prompts are versioned assets with golden tests. Changing a prompt means bumping `prompt_version` and re-running the suite.
- **Never put a rule in a prompt.** Not even as a reminder, not even as "for context." The model explains; the rules engine decides. We intend to demo the model getting a statutory detail wrong while the platform behaves correctly — do not accidentally fix that by smuggling the rule into the prompt.
- Structured output only. Schema violation after one retry is an escalation, not a parse-and-hope.
- No provider SDK imports outside `core/router/`. Changing vendor must stay a config change.

---

## Safe failure

- Retries use the **same** idempotency key. Never regenerate a key on retry.
- Verify post-state by reading back. A `200` is not evidence.
- Every step that can fail declares `compensation:`.
- When unsure, **stop**: route to the human queue with a context packet containing the computed values, the clauses applied, the conflict, and the single question a human needs to answer. "Please review" is not a context packet.
- Low confidence is treated exactly like a reserved decision. Uncertainty is a reason to halt, not to proceed carefully.

---

## PARAKH — the sourcing module, extra rules

This is the highest-risk code in the repo. India's DPDP Act offers only consent or a narrow list of legitimate uses, with no GDPR-style legitimate-interests basis, so a person who never gave us their data has no lawful basis for us to process it.

- A record whose source basis is `none` is **`pointer_only`**: store the public URL, source ID, timestamp, role hypothesis. Nothing derived.
- For a `pointer_only` record it is forbidden to: build a profile, compute a score, assign a rank, enrich contact details, infer attributes, or make **any** model call about that person.
- The only permitted action is a notice-first first contact inside a **human-approved campaign**. Individual sends are automated; campaign approval is reserved.
- Reply with interest ⇒ record a consent artefact and upgrade. Objection ⇒ permanent suppression list **and delete the pointer**. Silence ⇒ pointer expires.
- `prohibited_criteria` in an ICP pack (age, gender, caste, religion, marital/family status, disability, name origin, college tier, employment gaps, photograph) are stripped by the proxy before any model sees them. A scoring rule referencing one fails pack validation.
- Scores are **deterministic arithmetic** over extracted claims. The model returns claims with character spans; **a claim with no span is discarded**. The model never produces a score.
- `hire.reject_candidate` is reserved. Agents rank and explain. Humans reject.
- The no-raid guard checks **TBO's** obligations, not the candidate's freedom — post-employment non-competes are void in India; non-solicit clauses binding TBO are not. A block must surface the clause ID to the recruiter.
- No live sourcing or mail vendor. `sourcing_mock` and `mail_mock` only, synthetic profiles only. Do not add a real vendor SDK even behind a flag.

---

## Testing

| Kind | What it must cover |
|---|---|
| Policy | Every pack's `tests:` block; statutory-floor violations must fail |
| Contract | Each connector against the TBO mocks |
| Property | Idempotency: N retries ⇒ one side effect. Use Hypothesis |
| Chaos | 500s, timeouts, duplicate delivery, clock skew, mid-run process kill |
| Replay | Historical runs reproduce under their recorded pack versions |
| Fault corpus | Planted defects in `tests/fault_corpus/` — measures Prativaad, not the happy path |

A feature without a test that would fail if the feature broke is not done.

---

## Commits and PRs

Finalists are questioned **individually** about the parts they built, so commit history is evidence.

- Scoped commits, imperative subject, one concern each.
- Never co-mingle a `core/` change with a service-line change in one commit.
- PR body states: what extension points it touched, whether `core/` changed and why, and which tests cover it.
- Label service-line PRs `service-line` so the `core/` freeze check runs.
- Record every library and model added, with its licence, in `README.md`. Non-commercial licences fail CI.
- Declare AI coding assistant usage in `README.md` — which tool, for what. This is a competition rule.

---

## Working style

- **Code simple and readable over clever.** An intuitive implementation beats a compact one; a judge reading this repo for ten minutes is the audience for engineering quality.
- Run the devil's-advocate pass on any design decision before implementing it: what has to be true for this to be wrong, what breaks under retry or concurrency, and what a sceptical reviewer asks first.
- If a mechanism underperforms, **report it and shrink it**. An honest negative result on Prativaad scores better than a defended one.
- Update `PROGRESS.md` at the end of each working session: what shipped, what decided, what reversed, what is open.
- Do not invent measurements. A number that did not come out of `make bench` does not go in a document.
- When blocked by a missing TBO input (volumes, mock contracts, dates), state the assumption in `PROGRESS.md` under open questions and keep moving.

---

## Quick checklist before opening a PR

- [ ] No new network call outside `core/`
- [ ] Idempotency key on every side-effecting action; retries reuse it
- [ ] `compensation:` declared where failure is possible
- [ ] No rule in a prompt; no model in a `deterministic: true` step
- [ ] Policy pack has `tests:`; they pass
- [ ] Reserved verbs absent from agent capabilities
- [ ] Audit entry emitted per kernel step, with cost
- [ ] Skill manifest `inputs:` is minimal
- [ ] No real personal data anywhere, fixtures included
- [ ] `hrx validate && hrx test` green
- [ ] `PROGRESS.md` updated
