import { useState } from "react";
import { api, short } from "../api";
import { useApp } from "../context";

function Value({ v }: { v: any }) {
  if (v === null || v === undefined) return <span className="muted">—</span>;
  if (typeof v === "boolean") return <span className={`tag ${v ? "ok" : "warn"}`}>{v ? "yes" : "no"}</span>;
  if (typeof v === "number") return <span style={{ fontVariantNumeric: "tabular-nums" }}>{v.toLocaleString("en-IN")}</span>;
  if (Array.isArray(v)) return <span>{v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join(", ")}</span>;
  if (typeof v === "object") return <span className="mono">{JSON.stringify(v)}</span>;
  const s = String(v);
  return s.startsWith("tok_") ? <span className="tok">{s}</span> : <span>{s}</span>;
}

const HIDDEN = new Set(["policy", "rule_ids", "decided_by", "receipt_ids", "decision"]);

export function ComputedTable({ computed }: { computed: Record<string, any> }) {
  return (
    <div className="stack">
      {Object.entries(computed || {}).map(([step, values]) => (
        <div key={step}>
          <div className="small muted" style={{ marginBottom: 4 }}>from <b>{step}</b>{values?.policy ? <> · <span className="tag rule">{values.policy}</span></> : null}</div>
          <div className="kv">
            {typeof values === "object" && values !== null
              ? Object.entries(values).filter(([k]) => !HIDDEN.has(k) && !k.startsWith("_")).map(([k, v]) => (
                  <Pair key={k} k={k} v={v} />
                ))
              : <Pair k={step} v={values} />}
          </div>
        </div>
      ))}
    </div>
  );
}

function Pair({ k, v }: { k: string; v: any }) {
  return (<><div className="k">{k}</div><div><Value v={v} /></div></>);
}

const OPTIONS: Record<string, { label: string; decision: string; kind?: string }[]> = {
  reserved: [{ label: "Approve", decision: "approve", kind: "seal" }, { label: "Reject", decision: "reject" }],
  route_only: [{ label: "Acknowledge receipt", decision: "acknowledge", kind: "seal" }],
  low_confidence: [{ label: "Accept the draft", decision: "accept_draft", kind: "primary" }, { label: "Abort run", decision: "abort" }],
  policy_violation: [{ label: "Mark resolved by hand", decision: "provide", kind: "primary" }, { label: "Abort run", decision: "abort" }],
  schema: [{ label: "Accept the draft", decision: "accept_draft", kind: "primary" }, { label: "Abort run", decision: "abort" }],
  objection: [{ label: "Uphold — skip the action", decision: "skip_step", kind: "seal" }, { label: "Overrule — proceed", decision: "proceed" }],
  failure: [{ label: "Retry with the same key", decision: "retry", kind: "primary" }, { label: "Compensate and abort", decision: "compensate" }, { label: "Mark done by hand", decision: "mark_done" }],
  refused: [{ label: "Done by hand", decision: "mark_done", kind: "primary" }, { label: "Abort run", decision: "abort" }],
  paused: [{ label: "Finish by hand", decision: "finish_by_hand", kind: "primary" }],
};

/** A context packet: what a human needs, and nothing that makes them dig. */
export function Packet({ item, onDecided }: { item: any; onDecided?: (result: any) => void }) {
  const { user, toast } = useApp();
  const [note, setNote] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const p = item.packet || {};
  const canDecide = (item.approver_roles || []).some((r: string) => user.roles.includes(r));

  async function decide(decision: string) {
    setBusy(true); setError(null);
    try {
      const result = await api.post(`/api/queue/${item.id}/decide`, {
        user_id: user.id, decision, note, values, context_hash: item.context_hash, channel: "web",
      });
      toast(result.status === "decided" ? `Decision recorded · receipt ${result.receipt_ids.at(-1)}` : `Approval recorded · waiting for the next approver`);
      onDecided?.(result);
    } catch (e: any) {
      setError(e.message);
    } finally { setBusy(false); }
  }

  async function agentTries() {
    const r = await api.post(`/api/queue/${item.id}/agent-attempt`);
    setError(r.refused ? `Agent attempt refused by the kernel — ${r.reason}` : "Agent attempt was not refused (this would be a bug)");
  }

  return (
    <div className="stack">
      <div>
        <div className="row" style={{ marginBottom: 6 }}>
          <span className={`tag ${item.kind === "reserved" || item.kind === "route_only" ? "seal" : item.kind === "objection" ? "rule" : "warn"}`}>
            {item.kind.replace("_", " ")}
          </span>
          {item.action && <span className="tag rule">{item.action}</span>}
          <span className="small muted">approver: {(item.approver_roles || []).join(" → ")}</span>
        </div>
        <h2 style={{ fontSize: 20, margin: "4px 0 6px" }}>{item.question}</h2>
        {p.summary && <p style={{ margin: 0, color: "var(--ink-2)" }}>{p.summary}</p>}
      </div>

      {p.subject && Object.keys(p.subject).length > 0 && (
        <div className="row small">{Object.entries(p.subject).map(([k, v]) => <span key={k} className="tag">{k.replace("_", " ")}: {String(v)}</span>)}</div>
      )}

      {p.matter_text && <div className="refusal"><b>As written by the reporter</b><br />{p.matter_text}</div>}
      {p.platform_did_not && (
        <div className="notice small">
          The platform did: {p.platform_did.join("; ")}. It did <b>not</b>: {p.platform_did_not.join(", ")}.
        </div>
      )}

      {p.objections?.map((o: any, i: number) => (
        <div key={i} className="objection">
          <b>Prativaad · {o.class.replace(/_/g, " ")}</b> <span className="tag">{o.severity}</span><br />{o.claim}
        </div>
      ))}

      {p.recommendation && (
        <div className="notice">
          <div className="small muted">{p.recommendation.labelled}{p.recommendation.confidence ? ` · confidence ${p.recommendation.confidence}` : ""}</div>
          {p.recommendation.text}
        </div>
      )}

      {p.computed && Object.keys(p.computed).length > 0 && <ComputedTable computed={p.computed} />}
      {p.draft && Object.keys(p.draft).length > 0 && <ComputedTable computed={{ "agent draft": p.draft }} />}
      {p.reason && <div className="small muted">Why it is here: {p.reason}</div>}

      {p.clauses?.length > 0 && (
        <div className="row small"><span className="muted">Clauses applied:</span>
          {p.clauses.map((c: any) => <span key={c.pack} className="tag rule">{c.pack} {c.rule_ids?.join(" ")}</span>)}
        </div>
      )}

      {item.approvals?.length > 0 && (
        <div className="small">Approvals so far: {item.approvals.map((a: any) => `${a.name} (${a.roles.join(", ")})`).join(" → ")}</div>
      )}

      {item.status === "open" ? (
        <div className="stack" style={{ borderTop: "1px solid var(--line-2)", paddingTop: 12 }}>
          {Object.entries(p.decision_fields || {}).map(([k, t]) => (
            <label key={k} className="field">{k.replace(/_/g, " ")} (optional)
              <input type={t === "date" ? "date" : "text"} value={values[k] || ""} onChange={(e) => setValues({ ...values, [k]: e.target.value })} />
            </label>
          ))}
          <label className="field">Note for the receipt
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. confirmed with the manager" />
          </label>
          <div className="row">
            {(OPTIONS[item.kind] || OPTIONS.reserved).map((o) => (
              <button key={o.decision} className={`btn ${o.kind || ""}`} disabled={busy || !canDecide} onClick={() => decide(o.decision)}>{o.label}</button>
            ))}
            <span className="spacer" />
            {item.kind === "reserved" && <button className="btn ghost small" onClick={agentTries}>Let an agent try</button>}
          </div>
          {!canDecide && <div className="small muted">You are acting as {user.name}. This needs {item.approver_roles.join(" or ")} — switch user at the top.</div>}
          <div className="small muted mono">binds to {short(item.context_hash, 26)}</div>
        </div>
      ) : (
        <div className="row"><span className="tag ok">decided · {item.decision?.decision}</span></div>
      )}
      {error && <div className="refusal">{error}</div>}
    </div>
  );
}
