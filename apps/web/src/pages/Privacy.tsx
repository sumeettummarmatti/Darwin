import { useState } from "react";
import { api, fmtInr, fmtTime } from "../api";
import { usePoll } from "../hooks";

function Val({ v }: { v: any }) {
  if (v !== null && typeof v === "object") {
    // Nested payloads (retrieved clauses, candidate lists) scroll inside their cell.
    const text = JSON.stringify(v, null, 1);
    return <pre>{text.split(/(«[^»]+»)/g).map((part, i) => part.startsWith("«") ? <span key={i} className="tok">{part}</span> : part)}</pre>;
  }
  const s = typeof v === "string" ? v : JSON.stringify(v);
  if (s && s.includes("«")) {
    return <span>{s.split(/(«[^»]+»)/g).map((part, i) => part.startsWith("«") ? <span key={i} className="tok">{part}</span> : part)}</span>;
  }
  if (typeof v === "string" && v.startsWith("tok_")) return <span className="tok">{v}</span>;
  return <span>{s}</span>;
}

export default function Privacy({ arg }: { arg: string | null }) {
  const [calls] = usePoll<any[]>("/api/model-calls?limit=60", 4000);
  const [selId, setSelId] = useState<string | null>(arg);
  const sel = (calls || []).find((c) => c.id === selId) || (calls || [])[0];

  return (
    <>
      <div className="page-head">
        <h1>What personal data reaches a model</h1>
        <p>Every model call, side by side: what the kernel held, and the exact payload that left it. Undeclared fields are stripped, names become placeholders, and PAN and bank details never leave the vault.</p>
      </div>
      <div className="split">
        <section className="panel">
          <table className="t">
            <tbody>
              {(calls || []).map((c) => (
                <tr key={c.id} className={`click ${sel?.id === c.id ? "sel" : ""}`} onClick={() => setSelId(c.id)}>
                  <td><b className="mono" style={{ fontSize: 13 }}>{c.skill}</b>
                    <div className="small muted">tier {c.tier} · {c.model} · {fmtInr(c.inr, 5)} · {fmtTime(c.at)}</div></td>
                </tr>
              ))}
              {!(calls || []).length && <tr><td className="empty">No model calls yet. Run onboarding or ask the helpdesk something.</td></tr>}
            </tbody>
          </table>
        </section>
        {sel ? (
          <section className="panel panel-pad stack">
            <div className="row">
              <h2 style={{ margin: 0 }}>{sel.skill}</h2>
              <span className="tag agent">tier {sel.tier}</span><span className="tag">{sel.provider}:{sel.model}</span>
              <span className="tag">region: {sel.region}</span><span className="tag">prompt v{sel.prompt_version}</span>
            </div>
            <div className="small muted">Why this tier: {sel.escalation_reason} · {sel.tokens_in} tokens in, {sel.tokens_out} out · {fmtInr(sel.inr, 5)}</div>
            <div className="grid g2">
              <div>
                <h2>Held by the kernel</h2>
                <div className="kv">
                  {Object.entries(sel.source_record || {}).filter(([k]) => k !== "…withheld").map(([k, v]) => <span key={k} style={{ display: "contents" }}><div className="k">{k}</div><div><Val v={v} /></div></span>)}
                </div>
                {sel.source_record?.["…withheld"]?.length > 0 && (
                  <p className="small muted">Also in scope but never offered to this skill: {sel.source_record["…withheld"].length} fields ({sel.source_record["…withheld"].slice(0, 6).join(", ")}…)</p>
                )}
              </div>
              <div>
                <h2>Sent to the model</h2>
                <div className="kv">
                  {Object.entries(sel.outbound_payload || {}).map(([k, v]) => <span key={k} style={{ display: "contents" }}><div className="k">{k}</div><div><Val v={v} /></div></span>)}
                </div>
                {sel.stripped_fields?.length > 0 && (
                  <div className="stack small" style={{ marginTop: 10 }}>
                    {sel.stripped_fields.slice(0, 8).map((s: any, i: number) => <div key={i}><span className="tag seal">stripped</span> <span className="mono">{s.field}</span> — {s.reason}</div>)}
                  </div>
                )}
              </div>
            </div>
            <div>
              <h2>Model response</h2>
              <pre className="code" style={{ maxHeight: 220 }}>{JSON.stringify(sel.response, null, 2)}</pre>
            </div>
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
  return (
    <div className="grid g2" style={{ marginTop: 16 }}>
      <section className="panel panel-pad">
        <h2>Retention clocks</h2>
        <p className="sub">Started by the exit event. Fields whose purpose has ended are deleted; statutory fields are held back with the rule cited.</p>
        <div className="row" style={{ marginBottom: 10 }}>
          <button className="btn" onClick={async () => { setSweep(await api.post("/api/dpdp/sweep")); reload(); }}>Run the retention sweep now</button>
          <span className="small muted">Fast-forward the clock first to see deletions.</span>
        </div>
        {sweep && <div className="notice small" style={{ marginBottom: 10 }}>As of {sweep.as_of}: deleted {sweep.deleted.length} field(s), held {sweep.held.length} under statutory rules.</div>}
        <table className="t small">
          <thead><tr><th>Person</th><th>Field</th><th>Delete on</th><th>Hold</th></tr></thead>
          <tbody>
            {(schedule || []).slice(0, 14).map((r: any) => (
              <tr key={r.person_id + r.field}><td>{r.display_name || r.person_id}</td><td className="mono">{r.field}</td>
                <td>{r.deleted_at ? <span className="tag ok">deleted</span> : r.retention_until}</td><td className="small">{r.statutory_hold_rule || "—"}</td></tr>
            ))}
            {!(schedule || []).length && <tr><td colSpan={4} className="muted">No clocks running. Complete an exit to start them.</td></tr>}
          </tbody>
        </table>
      </section>
      <section className="panel panel-pad stack">
        <div>
          <h2>Access request</h2>
          <p className="sub">A data principal asks what we hold. Answered from the record, including every automated decision about them.</p>
          <div className="row">
            <input value={person} onChange={(e) => setPerson(e.target.value)} aria-label="Person ID" />
            <button className="btn" onClick={async () => setBundle(await api.get(`/api/dpdp/access/${person}`))}>Answer the request</button>
          </div>
          {bundle && <pre className="code" style={{ marginTop: 10, maxHeight: 260 }}>{JSON.stringify(bundle, null, 2)}</pre>}
        </div>
        <div>
          <h2>Purpose limitation</h2>
          <p className="sub">The onboarding agent asks for Meera's bank account to plan logistics. Bank details are tagged for payroll only.</p>
          <button className="btn seal" onClick={async () => setCross(await api.post("/api/dpdp/cross-purpose", {}))}>Attempt the cross-purpose read</button>
          {cross && <div className={cross.outcome === "refused" ? "refusal" : "notice"} style={{ marginTop: 10 }}><b>{cross.outcome}</b> — {cross.reason} (audit #{cross.audit_seq})</div>}
        </div>
      </section>
    </div>
  );
}
