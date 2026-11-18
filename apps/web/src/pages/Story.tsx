import { useState } from "react";
import { api } from "../api";
import { useApp } from "../context";

type Beat = { title: string; body: string; action: string; run: (ctx: ReturnType<typeof useApp>) => Promise<void> | void };

const plusDays = (iso: string, n: number) => { const d = new Date(iso); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

const BEATS: Beat[] = [
  {
    title: "Meera's offer is accepted",
    body: "Onboarding starts on its own. Entitlements resolve by rule. Before ordering a laptop, Prativaad notices an open allocation from Meera's contract stint two years ago; the kernel reads the return ledger, confirms it was returned, and only then allocates. No confidence score would have caught it, because the plan was never uncertain.",
    action: "Start onboarding",
    run: async ({ user, setUser, go }) => {
      if (!user.roles.includes("hr_business_partner")) setUser("USR-101");
      const r = await api.post("/api/runs", { workflow: "onboarding", subject_id: "EMP-4821", user_id: "USR-101" });
      go(`runs/${r.run_id}`);
    },
  },
  {
    title: "Her ID scan is too faint to read",
    body: "The small model is unsure, so the router escalates one tier on the measured trigger. Still unsure, it stops: Priya gets a packet with the draft, the reason and one question. Thirty seconds of her time instead of a wrong PAN in payroll.",
    action: "Open Priya's decisions",
    run: ({ setUser, go }) => { setUser("USR-101"); go("inbox"); },
  },
  {
    title: "The IT asset system goes down",
    body: "Retries reuse the same idempotency key, the outbox holds the intent, and the circuit breaker opens. Bring the system back and the queue drains. Read-back finds exactly one laptop.",
    action: "Break assets, start a joiner",
    run: async ({ go, toast }) => {
      await api.post("/api/mocks/chaos", { system: "assets", mode: "down" });
      const r = await api.post("/api/runs", { workflow: "onboarding", subject_id: "EMP-6000", user_id: "USR-103" });
      toast("The asset system is down. Restore it from Guardrails → Break a TBO system.");
      go(`runs/${r.run_id}`);
    },
  },
  {
    title: "Meera asks what to bring on day one",
    body: "In chat. The answer quotes clause ONB-C1 and the pack version. Then she asks about Form 16, which the clauses only partly cover: confidence falls under the threshold, the router moves up a tier and logs why.",
    action: "Open chat as Meera",
    run: ({ setUser, go }) => { setUser("USR-4821"); go("chat"); },
  },
  {
    title: "A notice-period amendment is drafted",
    body: "Priya's draft quietly drops the statutory-floor guard for fixed-term contracts. Prativaad generates adversarial cases, finds a Karnataka contract with ten days' notice resolving below the floor, blocks activation and proposes the regression test.",
    action: "Review the draft",
    run: ({ go }) => go("policies/notice_period"),
  },
  {
    title: "Rahul resigns, and asks to leave early",
    body: "The agent prepares: notice from the pack, settlement preview, gratuity by rule (four years two months is not eligible). It cannot accept. One line in his letter is a grievance about his manager; it is routed to the ethics officer untouched, with no summary.",
    action: "Submit Rahul's resignation",
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
    title: "Two approvals, then a buyout",
    body: "Acceptance is sequential: his manager Rohan, then Priya. The early release is a second reserved decision for Deepa. Each produces a receipt holding a hash of exactly what was on screen. Then Prativaad objects again: the card revocation was scheduled for the old last day. Rescheduled, logged.",
    action: "Decide as Rohan",
    run: ({ setUser, go }) => { setUser("USR-111"); go("inbox"); },
  },
  {
    title: "Ask an agent to accept it anyway",
    body: "The drill makes an agent attempt every reserved action, every forbidden verb and every route-only matter. The kernel refuses each with 403 and an audit entry. The UI has no button for it, and that is not the reason it fails.",
    action: "Run the drill",
    run: ({ go }) => go("governance"),
  },
  {
    title: "Payroll sign-off, then the last day",
    body: "Vikram signs off the settlement. Move the clock past the last working day: the card is revoked at 18:00, email suspended rather than deleted, retention clocks start, and the statutory set is held back with its rule cited.",
    action: "Decide as Vikram",
    run: ({ setUser, go }) => { setUser("USR-104"); go("inbox"); },
  },
  {
    title: "Talent: the platform says no to profiling",
    body: "A patent names an inventor who never gave TBO anything. Under DPDP there is no legitimate-interests basis, so she is stored as a pointer: a public link, nothing derived, no model call. A restricted employer is blocked with its clause ID, and campaign approval is reserved.",
    action: "Open Talent",
    run: ({ go }) => go("talent"),
  },
  {
    title: "Someone edits the audit log",
    body: "Change one historic row directly in the database. Verification breaks at that entry. Restore it and the chain is whole again.",
    action: "Open the audit chain",
    run: ({ go }) => go("audit"),
  },
  {
    title: "The dashboard closes the week",
    body: "₹ per completed run at p50 and p95, automation rate, escalations, refusals, Prativaad's precision and cost. Every figure drills to the rows behind it.",
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
        <p>Every feature in one story, in order. Each step opens the real screen; nothing here is a recording. Three of the most important moments are refusals.</p>
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
