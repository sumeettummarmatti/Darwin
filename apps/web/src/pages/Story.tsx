import { useState } from "react";
import { api } from "../api";
import { useApp } from "../context";

type Beat = { title: string; body: string; action: string; run: (ctx: ReturnType<typeof useApp>) => Promise<void> | void };

const plusDays = (iso: string, n: number) => { const d = new Date(iso); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

const BEATS: Beat[] = [
  {
    title: "Meera joins: onboarding starts",
    body: "Her laptop, email and access card are worked out from the rules. SETU notices an old laptop under her name, checks it was returned, and only then orders a new one.",
    action: "Start onboarding",
    run: async ({ user, setUser, go }) => {
      if (!user.roles.includes("hr_business_partner")) setUser("USR-101");
      const r = await api.post("/api/runs", { workflow: "onboarding", subject_id: "EMP-4821", user_id: "USR-101" });
      go(`runs/${r.run_id}`);
    },
  },
  {
    title: "The AI isn't sure about her ID",
    body: "When the AI isn't confident, it doesn't guess. It asks Priya one clear question.",
    action: "Open Priya's approvals",
    run: ({ setUser, go }) => { setUser("USR-101"); go("inbox"); },
  },
  {
    title: "The laptop system crashes",
    body: "SETU keeps retrying safely. When the system comes back, there is still exactly one laptop, not two.",
    action: "Crash it and start a joiner",
    run: async ({ go, toast }) => {
      await api.post("/api/mocks/chaos", { system: "assets", mode: "down" });
      const r = await api.post("/api/runs", { workflow: "onboarding", subject_id: "EMP-6000", user_id: "USR-103" });
      toast("The laptop system is down. Fix it from Safety controls, then Restore.");
      go(`runs/${r.run_id}`);
    },
  },
  {
    title: "Meera asks a question in chat",
    body: "The answer comes with the rule it's based on. A harder question goes to a bigger AI model, and the reason is recorded.",
    action: "Open chat as Meera",
    run: ({ setUser, go }) => { setUser("USR-4821"); go("chat"); },
  },
  {
    title: "Someone writes a bad rule change",
    body: "The change quietly breaks the legal minimum notice. SETU's checker finds a case that proves it and blocks the change.",
    action: "See the bad change",
    run: ({ go }) => go("policies/notice_period"),
  },
  {
    title: "Rahul resigns",
    body: "SETU works out his notice and final pay from the rules, but it can't accept the resignation. His complaint about his manager goes straight to the ethics officer. The AI never summarises it.",
    action: "Rahul resigns",
    run: async ({ boot, go }) => {
      const r = await api.post("/api/runs", {
        workflow: "exit", subject_id: "EMP-3310", user_id: "USR-101", channel: "slack",
        inputs: { letter_text: "I am resigning to join another company. I would like my last day to be earlier if possible. Separately, my manager has been bullying me in reviews.",
                  requested_last_day: plusDays(boot.clock, 20) },
      });
      go(`runs/${r.run_id}`);
    },
  },
  {
    title: "His managers approve",
    body: "First Rohan, then Priya, then Deepa for the early exit. When the last day moves, SETU moves the access-card cancellation too.",
    action: "Decide as Rohan",
    run: ({ setUser, go }) => { setUser("USR-111"); go("inbox"); },
  },
  {
    title: "Try to make the AI approve",
    body: "The AI tries every action it isn't allowed to do. Every one is blocked, by the system itself rather than the screen.",
    action: "Open Safety controls",
    run: ({ go }) => go("governance"),
  },
  {
    title: "Payroll signs off, last day arrives",
    body: "Vikram approves the final pay. Move the date forward: card cancelled, email suspended, and his data set to be deleted later.",
    action: "Decide as Vikram",
    run: ({ setUser, go }) => { setUser("USR-104"); go("inbox"); },
  },
  {
    title: "Hiring, done fairly",
    body: "People who never applied are only saved as a link. Applicants are scored by plain maths. The AI can rank, but only a person can reject.",
    action: "Open Hiring",
    run: ({ go }) => go("talent"),
  },
  {
    title: "Someone secretly edits the history",
    body: "Change one old entry and SETU spots it straight away.",
    action: "Open the history log",
    run: ({ go }) => go("audit"),
  },
  {
    title: "See the numbers",
    body: "How much ran automatically, what it cost and what was blocked. Click any number to see what's behind it.",
    action: "Open the dashboard",
    run: ({ go }) => go("overview"),
  },
];

export default function Story() {
  const app = useApp();
  const [done, setDone] = useState<number[]>([]);
  const [busy, setBusy] = useState<number | null>(null);

  async function play(i: number) {
    setBusy(i);
    try { await BEATS[i].run(app); setDone((d) => Array.from(new Set([...d, i]))); }
    catch (e: any) { app.toast(e.message); }
    finally { setBusy(null); }
  }

  return (
    <>
      <div className="page-head">
        <h1>One week at TBO</h1>
        <p>Click the steps in order. Each one does the real thing and opens the screen where it happens.</p>
      </div>
      <section className="panel panel-pad">
        <div className="beats">
          {BEATS.map((b, i) => (
            <div key={b.title} className={`beat ${done.includes(i) ? "done" : ""}`}>
              <div>
                <h3>{b.title}</h3>
                <p>{b.body}</p>
              </div>
              <button className={`btn ${i === Math.min(done.length, BEATS.length - 1) ? "primary" : ""}`} onClick={() => play(i)} disabled={busy !== null}>
                {busy === i ? "Working…" : b.action}
              </button>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
