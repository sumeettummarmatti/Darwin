// Record every feature of HR Autopilot as video, scenario by scenario.
//
// Drives the real console with Playwright (your installed Chrome) against a running
// server and writes one .webm per scenario, plus checks.json listing every check
// with pass/fail. Each step shows a caption bar saying what is happening and why.
//
//   PLAYWRIGHT_CORE=/path/to/node_modules/playwright-core \
//   node docs/evidence/record_demo.mjs --base http://localhost:8000 --out ~/Desktop/HR_Autopilot_Recordings
//
// Dev tool only (playwright-core, Apache-2.0); not a runtime dependency.

import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_CORE || "playwright-core");

const arg = (name, dflt) => { const i = process.argv.indexOf(`--${name}`); return i > 0 ? process.argv[i + 1] : dflt; };
const BASE = arg("base", "http://localhost:8000");
const OUT = arg("out", path.join(os.homedir(), "Desktop", "HR_Autopilot_Recordings")).replace(/^~/, os.homedir());
const ONLY = arg("only", "");
const CAPTIONS = arg("captions", "on") !== "off";   // off for the narrated cut: the voice explains instead
const HOLD = Number(arg("hold", "1"));                // scale caption pauses (e.g. 0.6 for a tighter cut)
const sleep = (s) => new Promise((r) => setTimeout(r, s * 1000));
const RESULTS = [];

class Demo {
  constructor(page, scenario) { this.page = page; this.scenario = scenario; }

  async api(p, body) {
    const r = body === undefined ? await this.page.request.get(BASE + p) : await this.page.request.post(BASE + p, { data: body });
    return r.json();
  }
  async caption(text, hold = 1.8) {
    if (!CAPTIONS) { await sleep(hold * HOLD); return; }
    await this.page.evaluate((t) => {
      let c = document.getElementById("__cap");
      if (!c) {
        c = document.createElement("div"); c.id = "__cap";
        c.style.cssText = "pointer-events:none;position:fixed;top:0;left:0;right:0;z-index:99999;background:#111a33;color:#fff;" +
          "font:600 17px/1.35 system-ui,sans-serif;padding:12px 22px;box-shadow:0 2px 10px rgba(0,0,0,.25)";
        document.body.appendChild(c);
      }
      c.textContent = t;
    }, text);
    await sleep(hold * HOLD);
  }
  async go(route) { await this.page.goto(`${BASE}/#/${route}`); await this.page.waitForLoadState("networkidle"); await sleep(1); }
  async asUser(id) { await this.page.getByLabel("You are").selectOption(id); await sleep(1); }
  async click(name, { exact = false, nth = 0 } = {}) {
    const l = this.page.getByRole("button", { name, exact }).nth(nth);
    await l.scrollIntoViewIfNeeded(); await l.click(); await sleep(1);
  }
  async clickText(text, nth = 0) {
    const l = this.page.getByText(text, { exact: false }).nth(nth);
    await l.scrollIntoViewIfNeeded(); await l.click(); await sleep(1);
  }
  async expect(what, pattern, timeout = 60) {
    const rx = new RegExp(pattern, "i"); const end = Date.now() + timeout * 1000;
    while (Date.now() < end) {
      const body = await this.page.innerText("body");
      if (rx.test(body)) {
        RESULTS.push({ scenario: this.scenario, check: what, ok: true });
        try { await this.page.getByText(rx).first().scrollIntoViewIfNeeded({ timeout: 2000 }); } catch {}
        await sleep(1.3); return true;
      }
      await sleep(1);
    }
    RESULTS.push({ scenario: this.scenario, check: what, ok: false, missing: pattern });
    return false;
  }
  async clickRow(text) {
    const l = this.page.locator("tr.click", { hasText: text }).first();
    await l.scrollIntoViewIfNeeded(); await l.click(); await sleep(1);
  }
  async scroll(px = 600) { await this.page.mouse.wheel(0, px); await sleep(1); }
}

// ── scenarios ─────────────────────────────────────────────────────────────

async function s01_onboarding(d) {
  await d.api("/api/demo/reset", {});
  await d.go("story");
  await d.caption("1 · Onboarding end to end: Meera joins. One click starts the whole joining checklist.");
  await d.click("Start onboarding");
  await d.caption("Rules work out laptop, access card and email. Most steps finish with no person (blue).", 3);
  await d.expect("ID check stops for a person when the AI is unsure", "The AI wasn't sure");
  await d.caption("Edge case: a faint ID. The AI is only about 50% sure even with the bigger model, so it STOPS and asks one question.", 3);
  await d.expect("plain reason shown", "only \\d+% sure");
  await d.clickText("See exactly what the AI was sent");
  await d.caption("Privacy: what HR Autopilot holds vs what the AI got. The name is replaced by «PERSON_1».", 3);
  await d.expect("name masked before the AI call", "PERSON_1");
  await d.page.goBack(); await sleep(2);
  await d.caption("Priya (HR) checks the document and accepts the AI's answer.");
  await d.click("Use the AI's answer");
  await d.expect("onboarding finishes", "Finished");
  await d.clickText("Allocate laptop");
  await d.caption("Edge case: an old laptop is still on Meera's name. The Devil's Advocate raises it before ordering.", 3);
  await d.expect("duplicate laptop caught", "Possible duplicate");
  await d.expect("checked the return ledger first", "returned on");
  await d.scroll(500);
  await d.caption("It read the return records, confirmed the old laptop came back, then ordered exactly one.", 2.5);
  await d.clickText("Show the full history of this process");
  await d.caption("Every step is in the history log: who, what, when and why.", 2.5);
}

async function s02_system_down(d) {
  await d.go("governance");
  await d.caption("2 · A system goes down: break the laptop system on purpose.");
  await d.page.getByLabel("System").selectOption("assets");
  await d.page.getByLabel("How it breaks").selectOption("down");
  await d.click("Break it");
  await d.expect("laptop system broken", "Laptops broken");
  await d.api("/api/runs", { workflow: "onboarding", subject_id: "EMP-6000", user_id: "USR-103" });
  await d.go("inbox");
  await d.asUser("USR-101");
  await d.caption("A new joiner starts. Laptop ordering can't reach the system...", 2);
  await d.expect("a person is told the system is down, with context", "A system is down");
  await d.caption("A person is told within seconds, with system, step, attempts and last error. Work is held, nothing is done twice.", 3.5);
  await d.go("governance");
  await d.click("Fix it");
  await d.caption("System fixed. HR Autopilot retries with the SAME receipt number and finishes by itself.", 3);
  await sleep(12);
  await d.go("runs");
  await d.clickRow("Onboarding");
  await d.expect("joiner finished after recovery", "Finished");
  await d.clickText("Allocate laptop");
  await d.expect("exactly one laptop", "Done once");
}

async function s03_retries(d) {
  await d.go("governance");
  await d.caption("3 · Retries never duplicate: the system SAVES the order, then times out.");
  await d.page.getByLabel("System").selectOption("assets");
  await d.page.getByLabel("How it breaks").selectOption("timeout_after_commit");
  await d.click("Break it");
  const run = await d.api("/api/runs", { workflow: "onboarding", subject_id: "EMP-6001", user_id: "USR-103" });
  await sleep(10);
  await d.go(`runs/${run.run_id}`);
  await d.caption("A normal system would think it failed and order again, giving two laptops.", 2.5);
  await d.clickText("Allocate laptop");
  await d.expect("one laptop after a timeout-after-save", "Done once");
  await d.caption("HR Autopilot reads back first, finds the saved order, and stops. Still exactly one laptop.", 3);
  await d.go("governance");
  await d.click("Fix it");
}

async function s04_chat(d) {
  await d.go("chat");
  await d.caption("4 · Chat: employees ask and act in plain language.");
  await d.page.getByLabel("Employee").selectOption("USR-4821");
  const say = async (text, rx, what, hold = 2.2) => {
    await d.page.getByLabel("Message").fill(text);
    await d.click("Send");
    await d.expect(what, rx, 75);
    await sleep(hold);
  };
  await say("hi", "I can check your leave balance", "greeting answered");
  await say("what is my name", "You're Meera Iyer", "who-am-I answered from the record");
  await say("when is my latop issued", "where your joining stands", "joining status (typo tolerated)");
  await say("What do I need to bring on day one?", "Source:", "policy answer cites its source");
  await d.caption("Rahul asks about leave: answered from the record, no AI, ₹0.");
  await d.page.getByLabel("Employee").selectOption("USR-3310");
  await say("How many casual leaves do I have?", "casual", "leave balance");
  await say("I need leave next Monday and Tuesday", "Done\\. 2 days", "short leave booked automatically");
  await say("Book 9 days of earned leave from 2026-12-21", "to your manager", "long leave sent to the manager (rule)");
  await d.caption("Edge case: a harassment report goes privately to the POSH committee. The AI never reads or judges it.");
  await d.page.getByLabel("Employee").selectOption("USR-2207");
  await say("I have been harassed by a colleague after the offsite", "didn't read it|passed", "POSH report routed, unread");
}

async function s05_bad_rule(d) {
  await d.go("policies/notice_period");
  await d.caption("5 · Someone writes a bad rule change. Every HR rule is a versioned file with tests.");
  await d.click("Suggest a change");
  await d.caption("This draft quietly drops the legal minimum notice for fixed-term contracts.", 2);
  await d.click("Check this change");
  await d.expect("change blocked", "Blocked: \\d+ case");
  await d.expect("counter-example shown", "legal minimum");
  await d.caption("The Devil's Advocate generated test cases, found a Karnataka fixed-term contract that breaks the law, and blocked it.", 3.5);
  await d.click("Add to the tests");
  await d.caption("It also wrote the test that catches this, so the mistake can never come back.", 2);
  await d.click("Cancel");
}

async function s06_exit(d) {
  await d.go("story");
  await d.caption("6 · Rahul resigns and asks to leave early. His letter also mentions bullying.");
  await d.click("Rahul resigns");
  await d.expect("complaint routed to the ethics officer", "Passed on to you");
  await d.caption("The bullying line goes straight to the ethics officer. HR Autopilot does not summarise or judge it.", 3);
  await d.clickText("Work out notice period");
  await d.expect("notice from the rules", "Notice days");
  await d.go("inbox"); await d.asUser("USR-101");
  await d.clickText("Accept resignation");
  await d.caption("Edge case: Priya (HR) tries to approve first.");
  await d.click("Approve", { exact: true });
  await d.expect("order enforced: manager first", "reporting_manager");
  await d.asUser("USR-111"); await d.go("inbox");
  await d.clickText("Accept resignation");
  await d.caption("Edge case: make the AI try to approve.");
  await d.click("Let the AI try to approve");
  await d.expect("AI blocked from approving", "Blocked\\. The AI isn't allowed");
  await d.caption("Blocked by the system itself, not just a hidden button. Rohan (manager) approves.", 2);
  await d.click("Approve", { exact: true });
  await d.asUser("USR-101"); await d.go("inbox");
  await d.clickText("Accept resignation");
  await d.click("Approve", { exact: true });
  await d.caption("Then Deepa (HR Head) agrees the early-exit buyout.");
  await d.asUser("USR-103"); await d.go("inbox");
  await d.clickText("Notice-period buyout");
  await d.click("Approve", { exact: true });
  await sleep(4);
  await d.go("runs");
  await d.clickRow("Exit");
  await d.clickText("Cancel access card");
  await d.expect("card cancellation rescheduled to the new last day", "Wrong date");
  await d.caption("Edge case: the last day moved but the card was still set for the old date. Caught and rescheduled automatically.", 3.5);
  await d.caption("Vikram (Finance) signs off the final pay. The AI can draft, never sign.");
  await sleep(4);
  await d.asUser("USR-104"); await d.go("inbox");
  await d.clickText("Payroll sign-off");
  await d.click("Approve", { exact: true });
  await d.caption("Move the clock past his last day: card cancelled, email suspended, laptop recovery, data-deletion clocks start.");
  await d.click("+30 days"); await sleep(4); await d.click("+30 days"); await sleep(6);
  await d.go("runs");
  await d.clickRow("Exit");
  await d.expect("exit finished", "Finished");
  await d.go("inbox");
  await d.click("Past decisions");
  await d.caption("Every approval is a receipt with a fingerprint of exactly what the person saw.", 2);
  await d.click("Check it wasn't changed");
  await d.expect("receipt verified", "Matches what they saw");
}

async function s07_hiring(d) {
  await d.api("/api/provider", { profile: "sim", user_id: "USR-101" });
  await d.go("talent");
  await d.caption("7 · FairHire: find and rank candidates fairly (simulator, to show its scripted edge cases).");
  await d.click("Find candidates");
  await d.expect("people found online kept as links only", "Link only");
  await d.caption("People who never applied are stored only as a link. No profile, no score, no AI.", 2.5);
  await d.click("Ask the AI about them");
  await d.expect("AI refused for a person who never applied", "Blocked:");
  await d.expect("no-poach companies blocked with the clause", "Can't approach");
  await d.scroll(900);
  await d.expect("applicants ranked by plain maths", "/ 100");
  await d.expect("made-up fact thrown away", "Made-up facts|holds three granted patents");
  await d.expect("bias phrase flagged", "Possible bias");
  await d.expect("AI's rejection blocked", "only a hiring manager can reject");
  await d.caption("Every score is quoted from the CV. The AI can rank, never reject.", 2.5);
  await d.scroll(-3000);
  await d.click("Approve as Ananya");
  await d.click("Approve", { exact: true });
  await d.go("talent");
  await d.caption("Outreach only after Ananya approves. 'Interested' records consent; 'stop' deletes the link forever.");
  await d.click("They replied: interested");
  await d.click("They replied: stop");
  await d.expect("replies handled", "Agreed to be contacted|never be contacted");
  await d.api("/api/provider", { profile: "groq", user_id: "USR-101" });
}

async function s08_safety(d) {
  await d.go("governance");
  await d.caption("8 · Safety controls: make the AI try every action it is not allowed to do.");
  await d.click("Run the test");
  await d.expect("every forbidden action blocked", "(\\d+)/\\1");
  await d.page.getByText("See every attempt").click(); await sleep(2);
  await d.caption("All blocked by the system itself, each with a reason and a history-log entry.", 2.5);
  await d.caption("Emergency stop: pause the Leave process instantly, with no code change.");
  await d.page.getByLabel("What to pause").selectOption("workflow");
  await d.page.getByLabel("Which one").selectOption("leave");
  await d.page.getByPlaceholder("Why? (optional)").fill("recording the demo");
  await d.click("Pause", { exact: true });
  await d.expect("leave paused", "Paused: Leave");
  await d.click("Resume");
  await d.caption("Edge case: try to edit the approvals list so the AI may accept resignations.");
  await d.click("Edit the list");
  const box = d.page.getByLabel("Approval list");
  const text = (await box.inputValue()).replace("{ action: exit.accept_resignation, principal: agent, expect: refuse }",
    "{ action: exit.accept_resignation, principal: agent, expect: permit }");
  await box.fill(text);
  await d.click("Save", { exact: true });
  await d.expect("unsafe edit refused", "Not saved");
  await d.caption("Refused: the list's own tests fail. HR can change who approves, but nobody can quietly let the AI decide.", 3);
  await d.click("Cancel");
}

async function s09_privacy(d) {
  await d.go("privacy");
  await d.caption("9 · Privacy: every AI call, what was actually sent, and where it was hosted.");
  await d.expect("hosting shown", "Sent to");
  await d.scroll(1400);
  await d.click("Delete what's due now");
  await d.expect("retention sweep ran", "Deleted \\d+");
  await d.caption("Data no longer needed is deleted; data the law says to keep is kept, with the reason.", 2.5);
  await d.page.getByLabel("Person").selectOption("EMP-3310");
  await d.click("Show their data");
  await d.caption("'What do you have on me?' answered in one click, including every automatic decision.", 2.5);
  await d.click("Let the AI try");
  await d.expect("wrong-purpose read blocked", "Blocked\\.");
  await d.caption("The onboarding AI asked for bank details 'for logistics'. Bank details are for payroll only, so it is blocked.", 3);
}

async function s10_history_dashboard(d) {
  await d.go("audit");
  await d.caption("10 · History log: try to secretly rewrite history.");
  await d.expect("chain intact", "Untouched");
  await d.click("Secretly edit an old entry");
  await d.expect("tampering detected", "Someone changed entry");
  await d.caption("Each entry is locked to the one before it. One edit breaks the chain and is caught immediately.", 3);
  await d.click("Put it back");
  await d.expect("chain restored", "Untouched");
  await d.go("overview");
  await d.caption("Dashboard: real measured numbers. Blocked actions, human decisions, cost per run, automation, time to finish.", 3);
  await d.expect("dashboard figures", "Fully automatic");
  await d.page.locator(".metric-btn").first().click(); await sleep(2);
  await d.caption("Click any number to see the rows behind it.", 2.5);
  await d.page.getByText("Show cost details").click(); await sleep(2);
  await d.caption("Cost details: rules vs AI, and the monthly estimate.", 3);
}


async function s11_workflows(d) {
  await d.go("workflows/exit");
  await d.caption("11 · Workflows are Lego blocks: the exit process as blocks — rules, AI, other systems, and where a person approves.", 3);
  await d.expect("workflow shown as blocks", "A person approves");
  await d.click("Edit this workflow");
  await d.caption("Edit it as a new version. Add a block: 'Collect issued materials' — one paste, no code.", 2);
  await d.click("Add a block");
  await d.page.getByLabel("Workflow file").evaluate((el) => el.scrollTo(0, 0));
  await d.click("Check this change");
  await d.expect("new block passes the same checks as a release", "Valid\\.");
  await d.scroll(450);
  await d.expect("preview shows the new block", "Collect issued materials");
  await d.caption("Valid: same checks as before any release. Make it live — new processes use it, running ones keep theirs.", 2.5);
  await d.click("Make it live");
  await d.expect("new version live, no restart", "is live");
  await d.caption("Edge case: someone removes a receipt number from a step that changes another system.", 2);
  await d.click("Edit this workflow");
  const box = d.page.getByLabel("Workflow file");
  const text = (await box.inputValue()).replace(/\n\s*idempotency_key: "exit:\{\{subject\.id\}\}:materials:v1"/, "");
  await box.fill(text);
  await d.click("Check this change");
  await d.expect("unsafe workflow refused", "Not valid");
  await d.caption("Refused: no receipt number means a retry could act twice. The engine itself was never touched.", 3);
  await d.click("Cancel");
}

const SCENARIOS = [s01_onboarding, s02_system_down, s03_retries, s04_chat, s05_bad_rule,
  s06_exit, s07_hiring, s08_safety, s09_privacy, s10_history_dashboard, s11_workflows];

const browser = await chromium.launch({ channel: "chrome", headless: true });
fs.mkdirSync(path.join(OUT, "_raw"), { recursive: true });
for (const fn of SCENARIOS) {
  if (ONLY && !fn.name.includes(ONLY)) continue;
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 },
    recordVideo: { dir: path.join(OUT, "_raw"), size: { width: 1440, height: 900 } } });
  const page = await ctx.newPage();
  const d = new Demo(page, fn.name);
  try { await fn(d); await d.caption("✓ done", 1.2); }
  catch (e) { RESULTS.push({ scenario: fn.name, check: "scenario ran to the end", ok: false, error: String(e).slice(0, 300) }); }
  const video = page.video();
  await ctx.close();
  if (video) fs.renameSync(await video.path(), path.join(OUT, `${fn.name}.webm`));
  console.log(fn.name, "recorded");
}
await browser.close();
fs.writeFileSync(path.join(OUT, "checks.json"), JSON.stringify(RESULTS, null, 2));
console.log(`${RESULTS.filter((r) => r.ok).length}/${RESULTS.length} checks passed`);
for (const r of RESULTS) if (!r.ok) console.log("FAIL", JSON.stringify(r));
