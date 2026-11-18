# Demo script — five-minute video and finale run sheet

Everything runs from the console (`make up`, open http://localhost:8000). **Demo story** walks the beats in order; each button opens the real screen. Before recording: `Reset` in the top bar for a fresh dataset.

## Five-minute video

| Time | Beat | Screen | Say (short) |
|---|---|---|---|
| 0:00 | The chase | Overview | "Today an HRMS records the hire, then people chase IT, Admin and Finance. Here the agents chase, the kernel enforces the law, and every rupee and decision is on this page." |
| 0:30 | One architecture | README diagram | "Agents have no network egress. They propose; the kernel decides, executes once, verifies and writes it down." |
| 0:50 | Meera joins | Story 1 → run rail | "Entitlements by rule. Before ordering a laptop Prativaad finds an open allocation from her contract stint two years ago; the kernel reads the return ledger and only then allocates. No confidence score would have caught that." |
| 1:30 | Unsure ⇒ stop | Story 2 → Decisions | "Her ID scan is faint. The small model escalates one tier on a measured trigger, is still unsure, and stops. Priya gets one question." |
| 1:55 | No two laptops | Guardrails → break *assets* (down) → start a joiner → Restore | "Same key on every retry, outbox holds the intent, breaker opens, read-back finds exactly one laptop." |
| 2:25 | Rahul resigns | Story 6 → run | "The agent prepares. Gratuity at four years two months: the rule says not eligible — the model's prose says otherwise, and the rule's number is the one that acts. The grievance line goes to the ethics officer untouched." |
| 3:00 | The kernel says no | Guardrails → Run the drill | "An agent attempts every reserved action. Every one: 403, with an audit entry." |
| 3:25 | Receipts | Decisions as Rohan → approve; Receipts → re-hash | "The receipt hashes exactly what he saw." |
| 3:45 | Policy argues back | Policy packs → notice period → Draft → Ask Prativaad | "The draft drops a statutory guard. Gate B finds a Karnataka 10-day contract below the floor and writes the test." |
| 4:10 | Talent | Talent → Source → Ask the model about a pointer | "A patent inventor never gave us anything: a pointer, no profile, no model call. A restricted employer: blocked with the clause." |
| 4:35 | Cost | Overview | "Paise per run. In onboarding, exit and leave, 83–100% of steps never touch a model." |
| 4:50 | Ask | — | "Now give us your requirement." |

## Finale run sheet

1. `Reset`. Acting as Priya.
2. Story beats 1–9 as above, switching users with the top bar: Rohan (USR-111) and Priya for acceptance, Deepa (USR-103) for the buyout, Vikram (USR-104) for payroll sign-off, Ishaan (USR-107) for the route-only acknowledgement, Ananya (USR-110) for the campaign.
3. **+1 week** in the top bar (twice if needed) to pass Rahul's last working day: card revoked at 18:00, email suspended, retention clocks started. Personal data → retention table.
4. Audit chain → edit a row → verification breaks → restore.
5. Guardrails → model provider → `sim_alt`; run `make test` in a terminal — still green.
6. **Live extension test:** `./hrx scaffold workflow <their-requirement>` → write the pack rules and tests → `./hrx validate` (expect the governance lint to catch something) → `./hrx test --workflow <name>` → start a run in the console. Rehearsed on leave encashment; see `docs/DEVGUIDE.md`.

## Scripted behaviours of the simulated provider (say so if asked)

The `sim` profile is deterministic. To exercise the defences on demand it is scripted to:

- give an imprecise gratuity explanation ("about four years and 240 days") in the exit packet, so the rule's number visibly wins;
- invent a patent claim for CAND-2004 whose quote is not in the résumé, so the span check discards it;
- write "top-tier institute" into CAND-2002's rationale, so gate D flags a college-tier proxy;
- return low confidence for Meera's faint ID scan (scan quality 0.42) at tiers 1 and 2;
- never raise Prativaad objections of its own, which is why the fault corpus reports no model-only catches.

With a real provider, the kernel's behaviour is the same: the model's text never changes a computed value, and a claim without a span never reaches the scorer.

## Prepared answers

- *Can an agent accept a resignation?* The drill. Then the load-time check: a workflow granting `accept` to an agent cannot be deployed.
- *What personal data reached the model?* Personal data page: the exact outbound payload next to what the kernel held.
- *Is this cost real?* `make bench`, and every rupee drills to its audit entry. On the simulated provider the rate card is declared, not invoiced, and we say so.
- *What if we change provider?* `sim_alt` swap, suite green. `openai_compatible` is a config block.
- *What if the policy is wrong?* Pack tests, compliance CI, gate B, and the version in every audit entry.
- *How do we know Prativaad is worth it?* We don't yet: rules catch 88% of planted defects; on the simulated provider the model layer adds nothing. Measure with a real model; shrink if it still adds under 20%.
