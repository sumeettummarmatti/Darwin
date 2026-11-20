# Try HR Autopilot: a click-by-click script

This walks you through **every feature**, in story order. Each step tells you:

- **Do:** what to click
- **You'll see:** what appears on screen
- **What it means:** why it matters, in plain words

Takes about 30–40 minutes if you do everything. Parts 1–6 are the main story; Parts 7–11 are extra checks.

---

## Before you start

**Open:** http://localhost:8000 (on your Mac), or the live site once it's redeployed.
If a page looks old, press **Cmd+Shift+R**.

### The top bar

| Thing | What it does |
|---|---|
| **You are** (dropdown) | Pick which person you're pretending to be. Approvals only work for the right person. |
| **Date** (clock) | The demo's "today". Things scheduled for the future wait for this date. |
| **+1 day / +30 days** | Move the date forward to make scheduled things happen. |
| **Reset** | Wipe everything back to the start. Use it before a fresh run-through. |

### The people you'll switch between

| Person | Role | Why you'll use them |
|---|---|---|
| **Priya Raman** | HR Business Partner | Default person. Starts processes, approves second. |
| **Rohan Das** | Engineering Manager | Rahul's manager. Must approve the resignation first. |
| **Deepa Krishnan** | HR Head | Approves the early-exit buyout and rule exceptions. |
| **Vikram Shah** | Finance Controller | Signs off final pay. |
| **Ananya Rao** | Talent Acquisition Lead | Runs hiring, approves outreach. |
| **Ishaan Bose** | Ethics Officer | Receives complaints. |
| **Meera Iyer** | New joiner | Asks questions in Chat. |
| **Rahul Menon** | Employee who resigns | Asks for leave, resigns in Chat. |
| **Tanvi Kulkarni** | Employee | Reports harassment in Chat. |

### Colours you'll keep seeing

| Colour | Means |
|---|---|
| **Blue** circle | Done automatically, no person needed |
| **Maroon** circle | A person decided |
| **Dashed** circle | Waiting (for a date or a retry) |
| **Red outline** | Blocked |
| **Yellow tag** | A rule was used |

**Press Reset now.**

---

## Part 1: Meera joins (onboarding)

### 1.1 Start it
**Do:** Sidebar → **Start here** → step 1 → **Start onboarding**.

**You'll see:** You jump to **Processes**. A row of circles appears: *Work out laptop and kit → Probation and first-day terms → Check the uploaded ID scan → Open IT ticket → Allocate laptop → Issue access card → Create email account → Set up payroll → …*. Most turn blue within seconds. One, **Check the uploaded ID scan**, turns maroon and the process says **Waiting for a person**.

**What it means:** HR Autopilot ran a whole joining checklist by itself. It only stopped where it wasn't sure.

### 1.2 Look at a step done by rules
**Do:** Click the first circle, **Work out laptop and kit**.

**You'll see:** "Worked out by rules. No AI." and a table (laptop class, software, access zones).

**What it means:** Which laptop Meera gets comes from a written rule, not from the AI's guess. Rules are cheap, exact and the same every time.

### 1.3 The AI wasn't sure about her ID
**Do:** Look at the maroon box under the circles (or go to **Approvals**).

**You'll see:**
- A tag **The AI wasn't sure**
- A question: *"Meera Iyer's ID scan could not be read reliably… is it legible and does the name match?"*
- *"The AI wasn't sure enough even after trying the bigger model, so HR Autopilot stopped instead of guessing."*
- **AI's answer**: confidence (e.g. 0.52), legible yes/no, name matches yes/no, its reasoning
- *"Why you're seeing this: The AI was only 52% sure (it needs 80%), even with the bigger model."*

**What it means:** The small AI tried, wasn't confident, so HR Autopilot tried a bigger AI. Still not confident, so it **stopped and asked a person one clear question**. It never guesses on important things.

### 1.4 See what the AI was actually sent
**Do:** Click the **Check the uploaded ID scan** circle → click **See exactly what the AI was sent**.

**You'll see:** The **Privacy** page with two columns: **What HR Autopilot has** (Meera's real name) and **What the AI got** (her name replaced with a blue **«PERSON_1»** tag). Under it: "N fields removed before sending".

**What it means:** The AI never sees real names, PAN or bank numbers. They're swapped for placeholders, and fields the AI doesn't need are removed.

### 1.5 Approve it
**Do:** Go back (**Processes** → the onboarding row) → **Use the AI's answer**.

**You'll see:** The box disappears. The rest of the circles turn blue. The process says **Finished**, about 92% automatic, with a tiny cost like ₹0.06.

**What it means:** One click from a person and the whole joining is done: laptop, card, email, payroll and welcome email.

### 1.6 The old laptop (the Devil's Advocate catches a duplicate)
**Do:** Click the **Allocate laptop** circle.

**You'll see:** A card titled **Possible duplicate**:
- **The charge:** "This person already has an open allocation (ASS-…) from 2024-03-04. Doing this again could create a duplicate."
- **Evidence:** the old allocation number
- **Defence:** "HR Autopilot checked the other system first: return ledger shows LT-B907 returned on 2024-09-14…"
- **Verdict:** **Upheld**, "Taken seriously and dealt with before anything happened."

Then: "Done once, record ASS-…".

**What it means:** Meera worked here on contract two years ago and a laptop is still on her name. Before ordering a new one, the **Devil's Advocate** raised a concern. HR Autopilot **read** the return records, confirmed the old laptop came back, and only then ordered one. A normal system would never have asked.

### 1.7 See the full history
**Do:** Scroll down → **Show the full history of this process**.

**You'll see:** A numbered list like "Started onboarding", "Checked the entitlements rules", "Asked the AI: extract id", "Sent to a person: low confidence", "The Devil's Advocate reviewed it before acting", "Assets: allocate · checked afterwards: exactly one record", each with who did it and when.

**What it means:** Every single thing is written down: who, what, when and why. That's what an auditor would ask for.

---

## Part 2: A system crashes

### 2.1 Crash the laptop system
**Do:** **Start here** → step 3 → **Crash it and start a joiner**.

**You'll see:** A message "The laptop system is down…". A new onboarding starts. It goes blue up to **Allocate laptop**, which shows a dashed circle (retrying).

**What it means:** The laptop system is broken. HR Autopilot doesn't give up and doesn't spam it. It waits and retries.

### 2.2 See it from Safety controls
**Do:** Sidebar → **Safety controls** → look at **Break a system (for testing)**.

**You'll see:** A red tag **Laptops broken**, maybe also "HR Autopilot stopped calling Laptops for now". Under **Recent calls to these systems**: failed calls.

**What it means:** After a few failures HR Autopilot stops calling the broken system for a bit (so it doesn't make things worse) and tries again later.

### 2.3 Fix it
**Do:** Make sure **Laptops** is selected → **Fix it**. Go back to **Processes** and open that new onboarding.

**You'll see:** **Allocate laptop** turns blue within a few seconds. Click it: "Done once, record …".

**What it means:** Even after all those retries there is **exactly one** laptop, not three. Every retry carried the same "receipt number", so the laptop system knew it was the same order.

### 2.4 Try the nastier failures (optional)
In **Break a system**, pick **Laptops**, then try each **How it breaks** option → **Break it** → start a new onboarding from **Processes** (Start → Onboarding → pick a joiner → Start):

| Option | What happens to a normal system | What HR Autopilot does |
|---|---|---|
| Fails 3 times | Gives up or double-orders | Retries, one laptop |
| Saves, then times out | Thinks it failed, orders again → **two laptops** | Checks first, finds the saved one, stops |
| Says OK, saves nothing | Thinks it worked → **zero laptops** | Checks afterwards, sees nothing, retries |
| Down until fixed | Errors out | Waits until you press Fix it |

Press **Fix it** when done.

---

## Part 3: Chat

### 3.1 Meera's day-one question
**Do:** **Start here** → step 4 → **Open chat as Meera** → click **What do I need to bring on day one?**

**You'll see:** An answer, plus tags: **Source: ONB-C1…** and **Used AI** or **No AI needed**.

**What it means:** The answer is based on a real written rule and shows which one. Nothing made up.

### 3.2 A harder question
**Do:** Click **When will I get my Form 16 for this year?**

**You'll see:** An answer (or "I'm not confident enough… I've passed it to HR"). It may use the bigger AI.

**What it means:** When the rules only partly cover a question, HR Autopilot either moves up to the bigger AI (and records why) or hands it to a person.

### 3.3 Rahul's leave balance
**Do:** Change **talking as** to **Rahul Menon** → **How many casual leaves do I have?**

**You'll see:** "Your current balance: 4 casual, 21 earned, 7 sick." Tag: **No AI needed**.

**What it means:** A balance is just a number from the records. No AI is used and it costs ₹0.

### 3.4 Book leave automatically
**Do:** Click **I need leave next Monday and Tuesday**.

**You'll see:** "Done. 2 days of casual leave booked from … You have 2 casual days left." Tag: **Source: leave rules (LV-…)**.

**What it means:** The rule says up to 3 casual days can be booked automatically, so HR Autopilot booked it, put it in the calendar and updated the balance.

### 3.5 Leave that needs a manager
**Do:** Click **Book 9 days of earned leave from 2026-12-21**.

**You'll see:** "I've sent your request for 9 days… to your manager (longer than the auto-booking limit or short notice). You'll hear back here."

**What it means:** Over the limit, so the rules send it to a person. The AI doesn't decide.

### 3.6 A harassment report
**Do:** Change **talking as** to **Tanvi Kulkarni** → **I have been harassed by a colleague after the offsite**.

**You'll see:** A reply that it's been passed on. A maroon tag **Passed to a person. The AI didn't read it.**

**What it means:** Sensitive matters go **straight** to the ethics/POSH officer. The AI doesn't summarise, judge or classify them, because a summary itself could be wrong or leak.

**Also try:** as Tanvi, **What is the notice period?** (answered from the rules) and **Apply leave tomorrow** (short notice, so it goes to her manager).

---

## Part 4: Someone writes a bad rule

### 4.1 Open the rule
**Do:** **Start here** → step 5 → **See the bad change** (or **Rules** → **Notice period**).

**You'll see:** "Notice period, version 4". A **Tests** list (all **Pass**) and **The rule file** (folded, click **Show the file** to see it).

**What it means:** Every HR rule is a readable file with its own tests. If a test fails, the rule isn't used.

### 4.2 Suggest the change
**Do:** **Suggest a change**.

**You'll see:** **Your change** with an editable rule file. **Make it live** is greyed out.

**What it means:** This is a prepared edit someone wrote. It looks harmless but quietly removes the legal minimum notice for fixed-term contracts.

### 4.3 Let the Devil's Advocate attack it
**Do:** **Check this change**.

**You'll see:**
- Red: **"Blocked: 27 cases break the rules."** The Devil's Advocate tried 135 test cases; 72 would get a different answer than today.
- Cards titled **Ends up below the legal minimum**: *Case: employment type fixed_term · grade L2 · state IN-KA · contract notice days 10*, *Your change gives: notice days 10…*, Verdict **Can't go live**.
- "The Devil's Advocate wrote a test that catches this." → **Add to the tests**.

**What it means:** The Devil's Advocate made up lots of realistic employees and found one (a fixed-term worker in Karnataka) where the new rule breaks the law. It **blocks** the change and writes a test so the mistake can never sneak back.

**Do:** **Add to the tests** → toast "Test added…". Then **Cancel** (don't make it live).

---

## Part 5: Rahul resigns

### 5.1 He resigns
**Do:** Press **Reset** if you want a clean slate (optional). **Start here** → step 6 → **Rahul resigns**.

**You'll see:** An **Exit: Rahul Menon** process. Blue: *Check the letter for complaints → Work out notice period → Estimate final pay → Prepare summary for managers*. Maroon: *Pass complaint to the ethics officer* and *Accept resignation*.

**What it means:** His letter says he wants to leave early and that his manager bullied him. HR Autopilot did the maths but **can't accept the resignation itself**.

### 5.2 The complaint
**You'll see** (the box under the circles): **Passed on to you · Grievance: complaint**. "HR Autopilot only passed this on. It did **not** classify, summarise, recommend, notify the person named." The **Got it** button is greyed out with "Only the ethics officer can decide this."

**What it means:** The bullying line went to the ethics officer untouched. Not even Priya (HR) can close it. **Optional:** switch **You are** to **Ishaan Bose** → **Approvals** → **Got it**.

### 5.3 The numbers HR Autopilot worked out
**Do:** Click **Work out notice period** and **Estimate final pay**.

**You'll see:** Notice days 60, last working day, shortfall days, gratuity eligible **no** (about 4 years 4 months; you need 5), leave encashment, settlement total.

**What it means:** All of this comes from the rules, not the AI. The AI only writes the summary sentence for the managers.

### 5.4 Priya can't go first
**Do:** **Approvals** (as Priya) → **Accept resignation** → **Approve**.

**You'll see:** A red message: *"next approval must come from role 'reporting_manager'"*.

**What it means:** The order matters: manager first, then HR. The system enforces it, not just the screen.

### 5.5 Let the AI try to approve
**Do:** Switch **You are** to **Rohan Das** → **Approvals** → **Let the AI try to approve**.

**You'll see:** Red: *"Blocked. The AI isn't allowed to decide this. Only a person can, and the attempt is in the history log."*

**What it means:** Even if someone wired the AI to click "approve", the system itself refuses. It's not just a hidden button.

### 5.6 Rohan approves
**Do:** Look at the card first: **AI suggestion. You decide.**, then 6 key figures (last working day, notice days, shortfall, buyout amount ₹…, settlement total ₹…, gratuity no). Click **Show all the numbers** if curious. Then **Approve**.

**You'll see:** "Approval saved. Waiting for the next person."

### 5.7 Priya approves
**Do:** Switch to **Priya Raman** → **Approvals** → **Approve**.

**You'll see:** "Decision saved, with a receipt." Next, a **Notice-period buyout** approval appears for the HR Head.

### 5.8 Deepa agrees to the early exit
**Do:** Switch to **Deepa Krishnan** → **Approvals** → the buyout item → **Approve**.

**You'll see:** The process moves on. Open the process (**Processes** → Exit) and click **Cancel access card on the last day**.

**You'll see:** A **Wrong date** card: "This is scheduled for … but the date it depends on is now …". Verdict **Upheld**. The card cancellation now shows the new, earlier date.

**What it means:** The last day moved earlier, but the access card was still set to be cancelled on the old date. That's a security hole (he'd keep building access). The Devil's Advocate noticed and **rescheduled it automatically**.

### 5.9 Receipts
**Do:** **Approvals** → **Past decisions**.

**You'll see:** Round **Approved** stamps for each decision, with who and when. Click **Check it wasn't changed** → **Matches what they saw**.

**What it means:** Each approval saves a fingerprint of exactly what the person saw. If anyone changes the numbers later, the check fails.

### 5.10 Payroll signs off
**Do:** Switch to **Vikram Shah** → **Approvals** → **Payroll sign-off** → **Approve**.

**What it means:** Money is paid only after the finance controller signs. The AI can draft, never sign.

### 5.11 The last day arrives
**Do:** Press **+30 days** (twice if his last day is still ahead). Open the Exit process.

**You'll see:** *Cancel access card on the last day*, *Suspend email after the last day*, *Raise laptop recovery*, *Mark exited*, *Schedule data deletion* all turn blue. The process says **Finished**.

**What it means:** Scheduled steps waited for the right date, then ran by themselves. Email is suspended, not deleted, in case it's needed.

---

## Part 6: Hiring (fair sourcing)

### 6.1 Find candidates
**Do:** Sidebar → **Hiring** → **Find candidates**. Wait ~15 seconds.

**You'll see:** "Senior platform engineer". Three boxes appear.

### 6.2 People found online, never applied
**You'll see:** Links like `https://papers.example/…`, `https://code.example/…`, tagged **Link only**, with their company.

**What it means:** These people never applied. Under Indian privacy law (DPDP) we have no right to profile them, so HR Autopilot **only stores the link**. No profile, no score, no AI.

### 6.3 Ask the AI about one of them
**Do:** Click **Ask the AI about them** on any link.

**You'll see:** Red: **Blocked:** (reason).

**What it means:** Even asking the AI "is this person good?" is refused for people who never agreed.

### 6.4 Can't approach
**You'll see:** Red boxes: **Northwind Channel Partners: TBO has a non-solicit obligation…**, **Acme Client Corp…**, each with the agreement number and "Only Legal + HR Head can make an exception." Matching links show **Can't approach**.

**What it means:** TBO promised these companies not to poach their staff. HR Autopilot checks TBO's promises and names the exact clause.

### 6.5 Applicants, ranked
**Scroll down. You'll see:** a table with Name, Score (e.g. **97 / 100**), Must-haves **Yes/No**, and **Proof from the CV**: quotes like "7 years building distributed systems", "Bengaluru", "Languages: Go, Python."

**What it means:**
- Applicants **did** apply, so they can be scored.
- The AI only pulls out facts, and **each fact must be an exact quote** from the CV.
- The **score is plain maths** from a rules file (production scale 30%, open source 20%, …). The AI never gives the score.
- Must-haves: at least 4 years, and based in Karnataka, Haryana or remote India.

### 6.6 The AI tries to reject someone
**You'll see:** For applicants marked **No**: *"The AI suggested rejecting. Blocked: only a hiring manager can reject."*

**What it means:** The AI can rank and explain. Rejecting a human is reserved for a person.

### 6.7 Made-up facts and bias (simulator only)
**Do:** **Safety controls** → **Switch AI** → **Simulator** → back to **Hiring** → **Search again**.

**You'll see:**
- **Made-up facts, thrown away**: a claim like "holds three granted patents in consensus". It isn't in the CV, so it was ignored.
- On one applicant: **Possible bias** card. The AI's note says "top-tier institute", which can be a hidden stand-in for college tier. **Flagged for the reviewer**.

**What it means:** If the AI invents something, it's thrown out because there's no exact quote. If its explanation sneaks in a biased phrase, the Devil's Advocate flags it, and the score never used it anyway.
*(These two are scripted into the simulator. Real Groq usually behaves, so they don't show up there.)* Switch back to **Groq** after if you like.

### 6.8 Outreach messages
**Do:** In **Outreach messages** → **Approve as Ananya** → **Approve**. Back on **Hiring**.

**You'll see:** **Approved** and "N messages sent".

**What it means:** Messages to people found online only go out after a named person approves the campaign. Each message says who we are and how to say stop.

### 6.9 They reply
**Do:** On one link → **They replied: interested**. On another → **They replied: stop**.

**You'll see:**
- Interested → tag changes to **Agreed to be contacted**.
- Stop → toast "They said stop. Link deleted, and they'll never be contacted again." The link disappears.

**What it means:** Consent unlocks normal processing. "Stop" means stop forever.

---

## Part 7: Safety controls

### 7.1 Try to make the AI break the rules
**Do:** **Safety controls** → **Run the test**.

**You'll see:** A stamp **26/26 BLOCKED** and "Every attempt was blocked by the system itself…". Click **See every attempt**: Exit: accept resignation, Payroll: sign off, Hire: reject candidate… all **Blocked**, each with a reason.

**What it means:** The AI tried every forbidden action at once. All refused, all recorded.

### 7.2 Emergency stop
**Do:** In **Emergency stop**: **One process** → **Leave** → reason "testing" → **Pause**.

**You'll see:** "Paused: Leave" with a **Resume** button.

**Then:** **Chat** → as **Rahul** → **I need leave next Monday and Tuesday**.

**You'll see:** It doesn't book. It waits, and an item appears in **Approvals** (as Priya) tagged **Paused** → "I'll finish it by hand".

**What it means:** If something goes wrong, HR can freeze one process (or one AI helper, one system, or everything) instantly, with no code change. Work in progress waits for a person.

**Do:** **Resume** when done.

### 7.3 Only a person can do these
**You'll see:** A table: Exit: accept resignation → reporting manager, then HR business partner; Payroll: sign off → finance controller; Hire: reject candidate → hiring manager; …

**Do (try to break it):** **Edit the list** → find the test line `- { action: exit.accept_resignation, principal: agent, expect: refuse }` → change `refuse` to `permit` → **Save**.

**You'll see:** Red: **Not saved:** …

**What it means:** HR can change who approves what without a developer. But the list has its own tests, so nobody (not even HR by mistake) can quietly let the AI accept resignations. **Cancel** after.

### 7.4 Real AI or simulator
**You'll see:** **Real AI (optional)**: Groq key box, and **Switch AI**: Simulator / Simulator (second vendor) / Groq.

**What it means:** The AI provider is a setting. Switching changes nothing else: same rules, same safety.

**Try:** paste a fake key like `gsk_fake123` → **Save key** → red "Groq didn't accept the key…", and HR Autopilot keeps working on the simulator.

---

## Part 8: Privacy

### 8.1 Every AI call
**Do:** **Privacy**. Click any row on the left (e.g. **Extract claims**, **Extract id**, **Welcome draft**).

**You'll see:** **What HR Autopilot has** vs **What the AI got**: names become **«PERSON_1»**, plus "N fields removed before sending" (click to see which and why: "not needed for this task", or banned criteria like college tier). **What the AI said back** (folded). If the bigger AI was used: why.

**What it means:** You can prove for every single AI call exactly what left the building.

### 8.2 When data gets deleted
**Do:** Scroll to **When data gets deleted**. (Needs Rahul's exit finished, Part 5.) Press **+30 days** a couple of times → **Delete what's due now**.

**You'll see:** Rows like Rahul · bank account · delete on …, some marked **Kept because: the law requires it**. A message "Deleted N. Kept N because the law requires it."

**What it means:** When someone leaves, a deletion clock starts for each piece of their data. Data that's no longer needed is deleted; data the law says to keep (tax, PF) is kept, with the reason.

### 8.3 "What do you have on me?"
**Do:** Pick **Rahul Menon** → **Show their data**.

**You'll see:** Everything HR Autopilot holds about him, including every automatic decision.

**What it means:** Under DPDP anyone can ask this. HR Autopilot can answer in one click.

### 8.4 Using data for the wrong reason
**Do:** **Let the AI try**.

**You'll see:** Red **Blocked.** and the reason (bank details are for payroll only).

**What it means:** Each piece of data is tagged with what it's for. The onboarding AI asking for bank details "for logistics" is refused.

---

## Part 9: History log (tamper test)

**Do:** Sidebar → **History log**.

**You'll see:** Green: **"Untouched. All N entries check out."** and a list of everything that happened.

**Do:** **Secretly edit an old entry**.

**You'll see:** Red: **"Someone changed entry 10."** "Every entry after it can no longer be trusted until it's put back."

**Do:** **Put it back** → green again.

**What it means:** Each entry is locked to the one before it (like a chain). Change one and the chain breaks, so nobody can quietly rewrite history, not even someone with database access.

**Try:** the **Everything** dropdown to filter: Approvals, AI use, Devil's Advocate, Other systems…

---

## Part 10: Dashboard

**Do:** Sidebar → **Dashboard**.

**You'll see:**
- **Blocked:** number of actions the AI tried that weren't allowed
- **Decided by a person:** approvals and how fast people decided; "History log is untouched"
- **Caught by the Devil's Advocate:** concerns raised, and how many were right
- **By process:** Exit, Helpdesk, Leave, Onboarding, Sourcing: finished, cost per run, % fully automatic, % sent to a person

**Do:** Click any number (e.g. **Blocked**).

**You'll see:** **Behind the number**: the actual rows (what was blocked and why). Click a row to open that process.

**Do:** **Show cost details**.

**You'll see:** How much was rules versus AI, the slowest runs' cost, and a **monthly estimate** for TBO's size.

**What it means:** Every number is measured from real runs, never typed in. You can always click through to the proof.

---

## Part 11: Other processes (quick)

**Do:** **Processes** → **Start** dropdown. Besides Onboarding and Exit you'll find:

| Process | Try it | What to look for |
|---|---|---|
| **Leave** | Pick an employee → Start | Booked by rules, or sent to manager |
| **Helpdesk** | Start | Answers "What do I need to bring on day one?" from the rules |
| **Leave encashment** | Pick an employee → Start | Payout worked out by rules, then finance sign-off |
| **Probation confirmation** | Pick an employee → Start | Review date by rules; confirming is a manager's decision |

The last two were added as new processes **without changing the engine**: just a rules file and a recipe file. That's the extensibility story.

---

## For developers (terminal)

| Command | What it shows |
|---|---|
| `make test` | All 89 tests: rules, safety, retries, crashes, hiring |
| `.venv/bin/python -m tools.hrx validate` | Every recipe and rule checked: tests present, no AI where rules should decide, no forbidden powers |
| `make bench` | Re-measures every number on the dashboard |

---

## If something looks wrong

| You see | Do this |
|---|---|
| Old labels or layout | **Cmd+Shift+R** |
| "This page could not be shown" | **Try again**, or tell me the page and what you clicked |
| Approve button greyed out | Wrong person. Change **You are** at the top |
| Nothing in Approvals | Switch person: each person only sees their own |
| Everything messy | **Reset** and start again |
| Groq key rejected | Make a new key at console.groq.com, or use the simulator |

---

**In one line:** the AI suggests, the rules decide, people approve, and everything is checked, done once and written down.
