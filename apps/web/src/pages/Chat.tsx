import { FormEvent, useEffect, useRef, useState } from "react";
import { Hash } from "lucide-react";
import { api } from "../api";
import { useApp } from "../context";
import { humanize } from "../components/Pretty";

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
  // Braces matter: newer browsers return a Promise from scrollIntoView, and React would call it as a cleanup.
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs.length]);

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
      push({ from: "bot", text: `Something went wrong: ${err.message}`, name: "SETU" });
    } finally { setBusy(false); }
  }

  return (
    <>
      <div className="page-head">
        <h1>Chat</h1>
        <p>Employees ask HR things here, like in Slack. Try one of the suggestions.</p>
      </div>
      <section className="panel chat">
        <div className="row panel-pad" style={{ paddingBottom: 12, borderBottom: "1px solid var(--line)" }}>
          <Hash size={18} /><b>ask-hr</b><span className="muted small">talking as</span>
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
                    {m.meta.citations?.length > 0 && <span className="tag rule">Source: {m.meta.citations.map((c: any) => c.clause || humanize(c.field || "")).join(", ")}</span>}
                    {m.meta.tier !== undefined && <span className={`tag ${m.meta.tier ? "agent" : ""}`}>{m.meta.tier ? "Used AI" : "No AI needed"}</span>}
                    {m.meta.queue_id && <span className="tag seal">Passed to a person. The AI didn't read it.</span>}
                    {m.meta.run_id && <button className="btn small ghost" onClick={() => go(`runs/${m.meta.run_id}`)}>Open the process</button>}
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
