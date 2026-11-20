import { useState } from "react";
import { api, fmtInr, fmtTime } from "../api";
import { usePoll } from "../hooks";
import { More, Pretty, humanize, plainReason } from "../components/Pretty";

function Val({ v }: { v: any }) {
  if (v !== null && typeof v === "object") return <Pretty v={v} />;
  const s = typeof v === "string" ? v : JSON.stringify(v);
  if (s && s.includes("«")) {
    return <span>{s.split(/(«[^»]+»)/g).map((part, i) => part.startsWith("«") ? <span key={i} className="tok">{part}</span> : part)}</span>;
  }
  if (typeof v === "string" && v.startsWith("tok_")) return <span className="tok">{v}</span>;
  return <span>{s}</span>;
}

/** "sourcing.extract_claims@v1" → "Extract claims". */
const skillName = (skill: string) => humanize(String(skill || "").split("@")[0].split(".").pop() || "");

export default function Privacy({ arg }: { arg: string | null }) {
  const [calls] = usePoll<any[]>("/api/model-calls?limit=60", 4000);
  const [selId, setSelId] = useState<string | null>(arg);
  const sel = (calls || []).find((c) => c.id === selId) || (calls || [])[0];

  return (
    <>
      <div className="page-head">
        <h1>Privacy</h1>
        <p>See exactly what the AI was sent. Names and ID numbers are hidden before anything leaves.</p>
      </div>
      <div className="split">
        <section className="panel">
          <table className="t">
            <tbody>
              {(calls || []).map((c) => (
                <tr key={c.id} className={`click ${sel?.id === c.id ? "sel" : ""}`} onClick={() => setSelId(c.id)}>
                  <td><b>{skillName(c.skill)}</b>
                    <div className="small muted">{c.tier >= 2 ? "bigger AI" : "AI"} · {fmtInr(c.inr)} · {fmtTime(c.at)}</div></td>
                </tr>
              ))}
              {!(calls || []).length && <tr><td className="empty">The AI hasn't been used yet. Start an onboarding or ask something in Chat.</td></tr>}
            </tbody>
          </table>
        </section>
        {sel ? (
          <section className="panel panel-pad stack">
            <div className="row">
              <h2 style={{ margin: 0 }}>{skillName(sel.skill)}</h2>
              <span className="small muted">cost {fmtInr(sel.inr)}</span>
            </div>
            <div className="small">Sent to <b>{String(sel.provider).startsWith("sim") || String(sel.region || "").includes("in-process") ? "the built-in simulator (never leaves this server)" : sel.region || humanize(String(sel.provider))}</b> · model {sel.model}</div>
            {sel.tier >= 2 && <div className="small muted">Why the bigger AI: {plainReason(sel.escalation_reason)}</div>}
            <div className="grid g2">
              <div>
                <h2>What HR Autopilot has</h2>
                <div className="kv">
                  {Object.entries(sel.source_record || {}).filter(([k]) => k !== "…withheld").map(([k, v]) => <span key={k} style={{ display: "contents" }}><div className="k">{humanize(k)}</div><div><Val v={v} /></div></span>)}
                </div>
                {sel.source_record?.["…withheld"]?.length > 0 && (
                  <p className="small muted">{sel.source_record["…withheld"].length} other fields weren't offered to the AI at all.</p>
                )}
              </div>
              <div>
                <h2>What the AI got</h2>
                <div className="kv">
                  {Object.entries(sel.outbound_payload || {}).map(([k, v]) => <span key={k} style={{ display: "contents" }}><div className="k">{humanize(k)}</div><div><Val v={v} /></div></span>)}
                </div>
                {sel.stripped_fields?.length > 0 && (
                  <More label={`${sel.stripped_fields.length} fields removed before sending`}>
                    <div className="stack small">
                      {sel.stripped_fields.slice(0, 12).map((s: any, i: number) => <div key={i}><span className="tag seal">Removed</span> {humanize(s.field)}: {/undeclared/.test(s.reason) ? "not needed for this task" : s.reason}</div>)}
                    </div>
                  </More>
                )}
              </div>
            </div>
            <More label="What the AI said back">
              <div className="panel" style={{ padding: 12, background: "#fafbfc" }}><Pretty v={sel.response} /></div>
              <p className="small muted">Model {sel.model} · {sel.tokens_in} tokens in, {sel.tokens_out} out</p>
            </More>
          </section>
        ) : <div className="panel empty">Select a call.</div>}
      </div>
      <Dpdp />
    </>
  );
}

function Dpdp() {
  const [schedule, reload] = usePoll<any[]>("/api/dpdp/schedule", 5000);
  const [person, setPerson] = useState("EMP-3310");
  const [bundle, setBundle] = useState<any>(null);
  const [sweep, setSweep] = useState<any>(null);
  const [cross, setCross] = useState<any>(null);
  const [people] = usePoll<any[]>("/api/people?kind=employee", 0);
  return (
    <div className="grid g2" style={{ marginTop: 16 }}>
      <section className="panel panel-pad">
        <h2>When data gets deleted</h2>
        <p className="sub">The clock starts when someone leaves. Data that's no longer needed is deleted. Data the law says to keep is kept.</p>
        <div className="row" style={{ marginBottom: 10 }}>
          <button className="btn" onClick={async () => { setSweep(await api.post("/api/dpdp/sweep")); reload(); }}>Delete what's due now</button>
          <span className="small muted">Move the date forward first (+30 days).</span>
        </div>
        {sweep && <div className="notice small" style={{ marginBottom: 10 }}>Deleted {sweep.deleted.length}. Kept {sweep.held.length} because the law requires it.</div>}
        <table className="t small">
          <thead><tr><th>Person</th><th>Data</th><th>Delete on</th><th>Kept because</th></tr></thead>
          <tbody>
            {(schedule || []).slice(0, 14).map((r: any) => (
              <tr key={r.person_id + r.field}><td>{r.display_name || r.person_id}</td><td>{humanize(r.field)}</td>
                <td>{r.deleted_at ? <span className="tag ok">Deleted</span> : r.retention_until}</td><td className="small">{r.statutory_hold_rule ? "the law requires it" : "—"}</td></tr>
            ))}
            {!(schedule || []).length && <tr><td colSpan={4} className="muted">Nothing scheduled. This starts after someone leaves.</td></tr>}
          </tbody>
        </table>
      </section>
      <section className="panel panel-pad stack">
        <div>
          <h2>"What do you have on me?"</h2>
          <p className="sub">Anyone can ask. The answer includes every automatic decision made about them.</p>
          <div className="row">
            <select value={person} onChange={(e) => setPerson(e.target.value)} aria-label="Person">
              {(people || []).map((p: any) => <option key={p.id} value={p.id}>{p.display_name}</option>)}
            </select>
            <button className="btn" onClick={async () => setBundle(await api.get(`/api/dpdp/access/${person}`))}>Show their data</button>
          </div>
          {bundle && <div className="panel" style={{ marginTop: 10, padding: 12, maxHeight: 360, overflow: "auto" }}><Pretty v={bundle} /></div>}
        </div>
        <div>
          <h2>Using data for the wrong reason</h2>
          <p className="sub">The onboarding AI asks for Meera's bank details. Bank details are only for payroll.</p>
          <button className="btn seal" onClick={async () => setCross(await api.post("/api/dpdp/cross-purpose", {}))}>Let the AI try</button>
          {cross && <div className={cross.outcome === "refused" ? "refusal" : "notice"} style={{ marginTop: 10 }}><b>{cross.outcome === "refused" ? "Blocked." : "Allowed."}</b> {cross.reason}</div>}
        </div>
      </section>
    </div>
  );
}
