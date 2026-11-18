# Governance — for an HR or legal reader

What the platform will never let an agent do, how that is enforced, and how to check it without reading code.

## 1. Reserved decisions

`policies/reserved_decisions.v4.yaml` (the highest version loads) lists every action only a named person may decide, with the approver roles and whether approvals are sequential. HR edits it in the console; a new version loads only if its tests pass, and it takes effect immediately with no deployment.

| Action | Approver(s) |
|---|---|
| `exit.accept_resignation` | reporting manager → HR business partner (sequential) |
| `exit.notice_buyout_agree` | HR Head |
| `exit.set_release_date` | reporting manager |
| `hire.final_decision` | hiring manager → HR Head |
| `hire.offer_approve` | HR Head → Finance Controller |
| `hire.reject_candidate` | hiring manager |
| `comp.change_salary_grade_role` | HR Head → Finance Controller |
| `policy.grant_exception` | HR Head |
| `discipline.terminate` | HR Head → Legal |
| `discipline.pip_initiate` | HR business partner |
| `payroll.sign_off`, `statutory.file` | Finance Controller |
| `onboarding.document_verify` | HR business partner |
| `leave.manager_approve` | reporting manager |
| `sourcing.campaign_approve` | Talent Acquisition Lead |
| `sourcing.add_source` | Legal → DPO |
| `sourcing.restricted_exception` | Legal → HR Head |
| `probation.confirm` | reporting manager |

**How it is enforced.** Every proposed action is classified by the kernel before anything else. An agent attempting a reserved action, or any action whose verb is `approve`, `accept`, `reject_candidate`, `sign_off` or `decide`, gets `403 RESERVED` and an audit entry — whatever the UI shows. A workflow or skill that grants one of those verbs to an agent fails validation when it loads, so it cannot be deployed. A human approver must hold the required role; sequential approvals must come in order.

**Check it:** Guardrails → *Run the drill*. An agent attempts every reserved action, every forbidden verb and every route-only matter; each comes back refused, with the audit entry number.

## 2. Route only, never decide

POSH complaints go to the POSH committee; grievances and whistleblower reports go to the ethics officer. Detection is a deterministic word list (`policies/intents.v1.yaml`, rules RO-001–003), which *routes* without reading for merit. The platform does not classify, summarise, recommend or notify anyone named; the hand-off packet records exactly that. In chat-reported matters, the reporter's words are visible only to the routed role.

## 3. Approval receipts

Every human decision produces a receipt: approver, roles, time, channel, note, the policy pack versions in force, and a SHA-256 hash of the exact packet the approver was shown, plus a snapshot of it. The approval binds to that hash: if the packet changed after it was displayed, the approval is refused as stale. **Check it:** Decisions → Receipts → *Re-hash the stored snapshot*.

## 4. Audit chain

One entry per kernel step: actor (and who an agent acted for), action, inputs (tokens, never raw PII), policy versions and rule IDs, prompt version, model, tier, tokens, rupees, latency, outcome. Each entry carries the hash of the previous one. **Check it:** Audit chain → *Edit a historic row in the database* — verification breaks at that entry.

## 5. Access control

`effective permission = the principal's role permissions ∩ the agent's capability allow-list ∩ the workflow step's scope`. Never a union. Principals act only on people inside their org units. The same onboarding agent acting for two HR business partners gets different outcomes (`tests/test_governance.py::test_rbac_same_agent_two_principals_different_outcomes`).

## 6. Kill switch and circuit breakers

Four scopes — global, one workflow, one skill, one connector — each a row in a table: no code change, no restart. Paused runs park in the decision queue with their context so HR can finish them by hand, and resume when released. A workflow whose escalation rate crosses its threshold (`policies/circuit_breakers.v1.yaml`) is paused by the kernel itself. Connectors that keep failing open a breaker; their pending actions wait in the outbox.

## 7. DPDP Act 2023

| Requirement | Mechanism |
|---|---|
| Purpose limitation | Every PII field is a row with purpose tags (`policies/dpdp.v1.yaml`). A read or a connector payload for another purpose is refused and audited (Personal data → *Attempt the cross-purpose read*). |
| Minimisation before any model call | The PII proxy strips undeclared fields and prohibited criteria, replaces names with placeholders and PAN/bank/Aadhaar with vault placeholders, and scrubs identifiers from free text. The payload viewer shows the exact outbound payload next to what the kernel held. |
| Retention | Clocks start at the exit event; fields whose purpose has ended are deleted by the sweep; statutory fields are held back with the holding rule cited. |
| Access and correction | `GET /api/dpdp/access/{person}` returns everything held, every run and decision about the person, and every model call (tokenised). Corrections write to the record and the audit chain. Erasure is refused, with the rule, for held fields. |
| Consent | Consent artefacts per purpose; sourcing replies with interest record one. |
| People who never gave us anything | `pointer_only`: a public link and the date, nothing derived. The proxy refuses any model call about them. Objection ⇒ permanent suppression and the pointer deleted. Silence ⇒ expiry. |

**An open question we do not pretend to have closed:** even a notice-first first contact is processing, and DPDP has no legitimate-interests basis for non-applicants. Our position is to minimise to the public identifier, give notice at first contact, suppress instantly on objection, require a human-approved campaign, and route the lawful basis for any new source to Legal and the DPO as a reserved decision. This is for TBO's counsel to decide.

## 8. Labour law as rules

Notice periods, gratuity (five years' continuous service, 15/26 of monthly wages per completed year with part years over six months counted, statutory ceiling), leave encashment, EPF on final wages and the F&F timeline live in tested packs (`notice_period.in.v4`, `settlement.in.v2`, `leave_encashment.v1`). Values marked *illustrative* (state notice floors, retention periods) are placeholders for counsel. A pack change that breaks a statutory floor fails its tests, fails CI and is blocked by Prativaad gate B.

## 9. Fair hiring

Scores are arithmetic in `policies/icp.senior_platform_engineer.v2.yaml` over claims the model extracted with a verbatim quote; a claim without one is discarded. Prohibited criteria (age, gender, caste, religion, marital and family status, disability, name origin, college tier, employment gaps, photographs) are stripped by the proxy, and a scoring rule that reads one fails to load. Prativaad gate D flags phrases that smuggle one back in. Agents rank and explain; rejection is reserved to the hiring manager. TBO's own non-solicit obligations are checked before anyone enters a campaign, and a block names the clause.
