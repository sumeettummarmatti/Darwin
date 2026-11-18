import { FormEvent, useEffect, useRef, useState } from "react";
import { Hash } from "lucide-react";
import { api, fmtInr } from "../api";
import { useApp } from "../context";

type Msg = { from: "user" | "bot"; text: string; meta?: any; name: string };

const SUGGESTIONS: Record<string, string[]> = {
  "USR-4821": ["What do I need to bring on day one?", "When will I get my Form 16 for this year?", "When is my laptop issued?"],
  "USR-3310": ["How many casual leaves do I have?", "I need leave next Monday and Tuesday", "I want to resign. My manager has been bullying me in reviews.", "Book 9 days of earned leave from 2026-12-21"],
  "USR-2207": ["I have been harassed by a colleague after the offsite", "Apply leave tomorrow", "What is the notice period?"],
};

export default function Chat() {
  const { users, user, setUser, go } = useApp();
  const employees = users.filter((u) => u.person_id);
  const speaker = employees.find((u) => u.id === user.id) || employees[0];
  const [log, setLog] = useState<Record<string, Msg[]>>({});
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const msgs = log[speaker.id] || [];
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [msgs.length]);

  async function send(value: string, e?: FormEvent) {
    e?.preventDefault();
    if (!value.trim()) return;
    setText("");
    setBusy(true);
    const push = (m: Msg) => setLog((l) => ({ ...l, [speaker.id]: [...(l[speaker.id] || []), m] }));
    push({ from: "user", text: value, name: speaker.name });
    try {
      const r = await api.post("/api/intent", { user_id: speaker.id, text: value, channel: "slack" });
      push({ from: "bot", text: r.reply, meta: r, name: "SETU" });
    } catch (err: any) {
      push({ from: "bot", text: `The kernel returned an error: ${err.message}`, name: "SETU" });
    } finally { setBusy(false); }
  }

  return (
    <>
      <div className="page-head">
        <h1>Chat, where people already work</h1>
        <p>A Slack-style surface over the same intent API the console uses. Intents are recognised by rule; answers cite the clause and pack version.</p>
      </div>
      <section className="panel chat">
        <div className="row panel-pad" style={{ paddingBottom: 12, borderBottom: "1px solid var(--line)" }}>
          <Hash size={18} /><b>ask-hr</b><span className="muted small">— speaking as</span>
          <select value={speaker.id} onChange={(e) => setUser(e.target.value)} aria-label="Employee">
            {employees.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </div>
        <div className="log">
          <div className="suggest" style={{ padding: 0, border: 0 }}>
            {(SUGGESTIONS[speaker.id] || []).map((s) => <button key={s} onClick={() => send(s)} disabled={busy}>{s}</button>)}
          </div>
          {msgs.map((m, i) => (
            <div key={i} className={`msg ${m.from}`}>
              <div className="av">{m.from === "bot" ? "से" : m.name.split(" ").map((x) => x[0]).join("")}</div>
              <div>
                <div className="who">{m.name}</div>
                <div className="body">{m.text}</div>
                {m.meta && (
                  <div className="row small" style={{ marginTop: 6 }}>
                    <span className="tag rule">{m.meta.policy} {m.meta.rule_ids?.join(" ")}</span>
                    <span className="tag">intent {m.meta.intent}</span>
                    {m.meta.citations?.map((c: any) => <span key={c.clause || c.field} className="tag rule">{c.clause || c.field} · {c.pack || c.source}</span>)}
                    {m.meta.tier !== undefined && <span className={`tag ${m.meta.tier ? "agent" : ""}`}>tier {m.meta.tier}</span>}
                    {m.meta.cost_inr !== undefined && <span className="tag">{fmtInr(m.meta.cost_inr, 5)}</span>}
                    {m.meta.run_id && <button className="btn small ghost" onClick={() => go(`runs/${m.meta.run_id}`)}>Open run</button>}
                    {m.meta.queue_id && <span className="tag seal">routed only — nothing assessed it</span>}
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={end} />
        </div>
        <form onSubmit={(e) => send(text, e)}>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder={`Message #ask-hr as ${speaker.name}`} aria-label="Message" />
          <button className="btn primary" disabled={busy}>Send</button>
        </form>
      </section>
    </>
  );
}
