# Developer guide — adding a workflow without touching `core/`

This is the Round 2 developer guide and the script for the live extension test. It walks through a real addition that is in the repository: **leave encashment on exit, capped at thirty days, Finance sign-off above ₹50,000** (`workflows/leave_encashment.v1.yaml`, `policies/leave_encashment.v1.yaml`, commit `leave_encashment: add line cold with hrx`).

You will touch `workflows/`, `policies/` and `tests/`. You will not touch `core/`. If you think you need to, stop: that is a design finding to raise, not a change to make quietly.

---

## 0. The five extension points

| Point | Lives in | You write | The kernel derives |
|---|---|---|---|
| Workflow | `workflows/<name>.vN.yaml` | steps, dependencies, idempotency keys, reserved flags, budget | orchestration, retries, audit, metering, approvals |
| Policy pack | `policies/<name>.vN.yaml` | rules, derived values, guards, **tests** | evaluation, versioning, rule IDs in every audit entry |
| Reserved registry | `policies/reserved_decisions.vN.yaml` | which actions only a named human may decide | 403 for agents, approver routing, receipts |
| Skill | `skills/<dir>/manifest.yaml` + `handler.py` | declared inputs and outputs, tier, escalation trigger | PII minimisation, routing, metering, token scope |
| Connector | `connectors/<dir>/manifest.yaml` + `connector.py` | action → external call, read-back | outbox, retries, breaker, verification |

Most new lines are a workflow and a pack. Reuse `policy.compute` for anything a rule can decide.

## 1. Scaffold

```console
$ ./hrx scaffold workflow leave-encashment
hrx scaffold workflow leave-encashment
  ✓ workflows/leave_encashment.v1.yaml
  ✓ policies/leave_encashment.v1.yaml
  ✓ tests/workflows/leave_encashment.spec.yaml
  ℹ the pack ships with an empty tests: block — hrx validate will refuse it until you add tests
  ℹ review policies/reserved_decisions for the reserved action this line needs
```

## 2. Validate early — the pack is refused

```console
$ ./hrx validate
  ✗ [pack] policies/leave_encashment.v1.yaml (leave_encashment): pack has no tests — refusing to load
1 error(s)
```

This is deliberate. A rule without a test does not reach production.

## 3. Write the rules — in the pack, never in a prompt or an `if`

```yaml
pack: leave_encashment
jurisdiction: IN
version: 1
effective_from: 2026-01-01
owner: finance_controller
tables:
  cap_days: { default: 30 }
  finance_signoff_above_inr: { default: 50000 }
derive:
  - { id: LE-001, name: encashable_days, expr: "min(earned_leave_balance, lookup('cap_days', 'default'))" }
  - { id: LE-002, name: amount, expr: "round(basic_monthly / 26 * encashable_days)" }
  - { id: LE-003, name: needs_finance_signoff, expr: "amount > lookup('finance_signoff_above_inr', 'default')" }
guards:
  - { id: LE-G1, assert: "earned_leave_balance >= 0", error: "negative leave balance" }
tests:
  - { name: "capped at thirty days", given: { earned_leave_balance: 45, basic_monthly: 52000 },
      expect: { encashable_days: 30, amount: 60000, needs_finance_signoff: true } }
  - { name: "exactly ₹50,000 is not above the threshold", given: { earned_leave_balance: 25, basic_monthly: 52000 },
      expect: { amount: 50000, needs_finance_signoff: false } }
  - { name: "negative balances are refused", given: { earned_leave_balance: -2, basic_monthly: 52000 },
      expect_error: "negative" }
```

The expression language is a whitelist: arithmetic, comparisons, `and/or/not`, `x if c else y`, dotted dictionary access, and functions such as `min`, `max`, `round`, `lookup`, `get`, `days_between`, `add_days`, `completed_months`, `contains`. No comprehensions, no attribute access, no imports — they fail when the pack loads.

## 4. Write the workflow — and let the lint catch you

A first draft that pays money with no human gate:

```yaml
  - id: pay
    connector: payroll
    action: prepare_settlement           # declared money: true in the connector manifest
    needs: [compute]
    idempotency_key: "encash:{{subject.id}}:pay:v1"
```

```console
$ ./hrx validate
  ✗ governance lint C-MONEY leave_encashment@v1:pay: payroll.prepare_settlement moves money to or for a person
    and no reserved: step precedes it — comparable actions are reserved (payroll.sign_off / finance approval)
```

Add the reserved step. Its condition reads the pack's output; the threshold itself stays in the pack:

```yaml
  - id: finance_sign_off
    reserved: true
    action: payroll.sign_off                     # must exist in the reserved registry
    when: "steps.compute.needs_finance_signoff == True"
    needs: [compute]
    question: "Sign off a leave encashment of ₹{{steps.compute.amount}} ({{steps.compute.encashable_days}} days) for {{subject.display_name}}?"
    packet_from: [compute]

  - id: pay
    connector: payroll
    action: prepare_settlement
    needs: [compute, finance_sign_off]           # a skipped step counts as satisfied
    args: { employee_ref: "{{subject.id}}", leave_encashment: "{{steps.compute.amount}}", total: "{{steps.compute.amount}}",
            bank_account_token: "{{subject.bank_account_token}}" }
    idempotency_key: "encash:{{subject.id}}:pay:v1"
```

What validation enforces at load time, so you cannot ship it wrong:

- every side-effecting connector step has a templated, unique `idempotency_key` (add a `:vN` suffix);
- a `deterministic: true` step cannot use a model skill;
- no agent step may carry `approve`, `accept`, `reject_candidate`, `sign_off` or `decide`;
- every `reserved:` step names an action the registry knows; every `route_only:` step names a route-only action;
- `foreach:` steps key each item separately; dependencies exist and have no cycles; every template parses.

The governance lint adds what judgement says (money without a reserved step, irreversible without compensation, prompts that contain a rule, budgets, tier-0 share).

## 5. Test — golden runs and a retry storm

```console
$ ./hrx test --workflow leave_encashment --runs 6
  ✓ leave_encashment: 6/6 runs completed under an injected retry storm
  ✓ leave_encashment: no duplicate side effects (12 keyed effects verified by read-back)
  ✓ audit chain: 77 entries verified
pass
```

`hrx test` injects 500s on every external system, approves reserved decisions with simulated humans (labelled as such in each receipt), fast-forwards the clock past scheduled steps, and checks that no idempotency key produced more than one record in any system. Add a pytest for the behaviour you care about (`tests/workflows/test_leave_encashment.py`).

## 6. Run it

The new workflow appears in the console under **Workflows → Start a run** with no restart (`/api/runs` loads definitions from disk). It is metered, audited and governed like every other line.

---

## Adding a skill

```console
$ ./hrx scaffold skill payslip-explain
```

Rules for skills:

- Declare `inputs:` precisely. The PII proxy strips everything else before a model sees it; `ctx.input()` refuses undeclared fields.
- `kind: deterministic` skills cannot call `ctx.ask_model()`.
- Model skills declare `model_tier` (1 is the default), `escalate_to_tier` and an `escalate_when` expression over their structured output — a *measured* trigger, never "this seems hard". Tier 3 needs `tier3_opt_in` with a reason.
- Prompts are versioned files (`prompt.vN.md`). Never put a rule in a prompt; the lint flags "30 days"-shaped text.
- A handler gets a `SkillContext`: declared inputs, `policy()`, `ask_model()`, `propose()`, `needs_human()`, `challenge_rationales()`, `is_suppressed()`. No HTTP client, no database, no connector. Proposals go through the kernel and are limited to the step's `may_propose` list.
- Ship a `simulated.py` so the skill runs offline and in the bench.

## Adding a connector

```console
$ ./hrx scaffold connector expense-system
```

Declare each action's `side_effect`, `irreversible`, `money`, `compensation` and `capability` in the manifest. In `execute`, always pass the idempotency key to the system as its client reference: `read_back` uses it to verify post-state and to recognise a call that timed out after committing. Implement `prior_effects` if a duplicate is possible across different keys (Prativaad uses it). Spares for the live test are pre-registered in `connectors/_spares/` (calendar, e-signature).

## Changing a policy safely

Draft the new version in the console (**Rules → Suggest a change**) and press **Check this change**. Gate B runs the pack's own tests, then generates every combination of its `adversarial:` input domains and checks its `properties:` hold; it shows what changes against the active version and proposes regression tests. Activation writes `policies/<name>.vN+1.yaml` and hot-reloads — only if gate B is clean.

## Changing the reserved list

**Safety controls → Only a person can do these → Edit the list**. The registry's own `tests:` must pass or the new version will not load (try adding `it.assets.allocate` without updating the test that says agents may allocate laptops).

## Editing on screen vs in files

| Change | Where |
|---|---|
| A rule (notice, leave, gratuity…) | On screen: **Rules → Suggest a change → Check this change → Make it live** (new version, tests and gate B must pass) |
| Who approves what | On screen: **Safety controls → Edit the list** (the list's own tests must pass) |
| Pause a workflow, skill or connector | On screen: **Safety controls → Emergency stop** |
| Add, remove or reorder workflow steps; make a step need approval | **File**: edit `workflows/<line>.vN.yaml` (prefer a new version), run `hrx validate && hrx test`, restart. No console editor yet |
| A new skill or connector | **File**: new folder under `skills/` or `connectors/` |

Example — add "collect issued materials" to exit, with no code:

```yaml
  - id: collect_materials
    title: Collect issued materials
    connector: it.ticketing
    action: open_ticket
    needs: [accept_resignation]
    args: { summary: "Collect issued materials from {{subject.display_name}} by {{facts.last_working_day}}" }
    idempotency_key: "exit:{{subject.id}}:materials:v1"
    compensation: close_ticket
```

Then add `collect_materials` to `mark_exited`'s `needs:`.

## Checklist before you open a PR

- [ ] `./hrx validate` green, `./hrx test --workflow <name>` green, `make test` green
- [ ] No file in `core/` changed (label the PR `service-line`; CI enforces it)
- [ ] Pack has tests; no rule in a prompt; no model in a deterministic step
- [ ] Reserved actions in the registry; idempotency keys on every side effect
- [ ] Synthetic data only, fixtures included
