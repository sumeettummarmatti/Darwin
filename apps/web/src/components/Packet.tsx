import { useState } from "react";
import { api } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";
import { Hearing } from "./Hearing";
import { More, Pretty, humanize, plainAction, plainReason } from "./Pretty";

function Value({ v }: { v: any }) {
  if (v !== null && typeof v === "object") return <Pretty v={v} />;
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
          <div className="small muted" style={{ marginBottom: 4 }}><b>{humanize(step)}</b></div>
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

// The handful of figures a decider actually weighs; everything else sits under "Show all the numbers".
const KEY_FIGURES = ["last_working_day", "notice_days", "shortfall_days", "buyout_amount", "settlement_total", "gratuity_eligible",
  "days", "leave_type", "start_date", "end_date", "balance", "balance_after", "encashment_amount", "review_date", "laptop_class", "outcome", "system", "step", "attempts", "last_error"];

function KeyFigures({ computed }: { computed: Record<string, any> }) {
  const flat: [string, any][] = [];
  for (const [step, values] of Object.entries(computed || {})) {
    if (step.includes("packet") || values === null || typeof values !== "object") continue;
    for (const [k, v] of Object.entries(values)) if (!HIDDEN.has(k) && !k.startsWith("_") && typeof v !== "object") flat.push([k, v]);
  }
  const picked = KEY_FIGURES.flatMap((k) => flat.filter(([fk]) => fk === k).slice(0, 1));
  const shown = picked.length ? picked : flat.slice(0, 6);
  if (!shown.length) return null;
  return <div className="kv">{shown.map(([k, v]) => <Pair key={k} k={k} v={v} />)}</div>;
}

function Pair({ k, v }: { k: string; v: any }) {
  const money = typeof v === "number" && /(amount|total|encashment|salary|_inr|pay$)/.test(k);
  return (<><div className="k">{humanize(k)}</div><div>{money ? `₹${v.toLocaleString("en-IN")}` : <Value v={v} />}</div></>);
}

const OPTIONS: Record<string, { label: string; decision: string; kind?: string }[]> = {
  reserved: [{ label: "Approve", decision: "approve", kind: "seal" }, { label: "Reject", decision: "reject" }],
  route_only: [{ label: "Got it", decision: "acknowledge", kind: "seal" }],
  low_confidence: [{ label: "Use the AI's answer", decision: "accept_draft", kind: "primary" }, { label: "Stop the process", decision: "abort" }],
  policy_violation: [{ label: "I fixed it by hand", decision: "provide", kind: "primary" }, { label: "Stop the process", decision: "abort" }],
  schema: [{ label: "Use the AI's answer", decision: "accept_draft", kind: "primary" }, { label: "Stop the process", decision: "abort" }],
  objection: [{ label: "Agree, don't do it", decision: "skip_step", kind: "seal" }, { label: "Disagree, go ahead", decision: "proceed" }],
  failure: [{ label: "Try again", decision: "retry", kind: "primary" }, { label: "Undo and stop", decision: "compensate" }, { label: "I did it by hand", decision: "mark_done" }],
  refused: [{ label: "I did it by hand", decision: "mark_done", kind: "primary" }, { label: "Stop the process", decision: "abort" }],
  paused: [{ label: "I'll finish it by hand", decision: "finish_by_hand", kind: "primary" }],
  system_down: [{ label: "Got it, keep waiting", decision: "acknowledge", kind: "primary" }, { label: "Undo and stop", decision: "compensate" }],
};

export const KIND_LABEL: Record<string, string> = {
  reserved: "Needs approval", route_only: "Passed on to you", low_confidence: "The AI wasn't sure", policy_violation: "Rule problem",
  schema: "The AI's answer was unclear", objection: "Devil's Advocate objected", failure: "A system failed", refused: "Blocked", paused: "Paused", system_down: "A system is down",
};
const role = (r: string) => humanize(r).toLowerCase().replace(/\bhr\b/g, "HR");

/** A context packet: what a human needs, and nothing that makes them dig. */
export function Packet({ item, onDecided }: { item: any; onDecided?: (result: any) => void }) {
  const { user, toast } = useApp();
  const [note, setNote] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const p = item.packet || {};
  const [reg] = usePoll<any>("/api/reserved", 0);
  const sequential = (reg?.entries || []).some((e: any) => e.action === item.action && e.mode === "sequential");
  // An open item that already has approvals is a sequential one: only the next role may act.
  const approvals = item.approvals || [];
  const nextRole: string | null = approvals.length > 0 ? item.approver_roles[approvals.length] ?? null : null;
  const canDecide = nextRole ? user.roles.includes(nextRole) : (item.approver_roles || []).some((r: string) => user.roles.includes(r));

  async function decide(decision: string) {
    setBusy(true); setError(null);
    try {
      const result = await api.post(`/api/queue/${item.id}/decide`, {
        user_id: user.id, decision, note, values, context_hash: item.context_hash, channel: "web",
      });
      toast(result.status === "decided" ? "Decision saved, with a receipt." : "Approval saved. Waiting for the next person.");
      onDecided?.(result);
    } catch (e: any) {
      setError(e.message);
    } finally { setBusy(false); }
  }

  async function agentTries() {
    const r = await api.post(`/api/queue/${item.id}/agent-attempt`);
    setError(r.refused ? "Blocked. The AI isn't allowed to decide this. Only a person can, and the attempt is in the history log." : "The AI was not blocked. This is a bug.");
  }

  return (
    <div className="stack">
      <div>
        <div className="row" style={{ marginBottom: 6 }}>
          <span className={`tag ${item.kind === "reserved" || item.kind === "route_only" ? "seal" : item.kind === "objection" ? "rule" : "warn"}`}>
            {KIND_LABEL[item.kind] || humanize(item.kind)}
          </span>
          {item.action && <span className="small">{plainAction(item.action)}</span>}
          <span className="small muted">· decided by {(item.approver_roles || []).map(role).join(sequential ? ", then " : " or ")}</span>
        </div>
        <h2 style={{ fontSize: 20, margin: "4px 0 6px" }}>{item.question}</h2>
        {p.summary && p.summary !== item.title && !p.platform_did_not && <p style={{ margin: 0, color: "var(--ink-2)" }}>{p.summary}</p>}
      </div>

      {p.subject && Object.keys(p.subject).length > 0 && (
        <div className="row small">{Object.entries(p.subject).filter(([k]) => !["display_name", "id", "org_unit"].includes(k)).map(([k, v]) => <span key={k} className="tag">{humanize(k)}: {String(v)}</span>)}</div>
      )}

      {p.matter_text && <div className="refusal"><b>In their own words</b><br />{p.matter_text}</div>}
      {p.platform_did_not && (
        <div className="notice small">
          HR Autopilot only passed this on. It did <b>not</b> {p.platform_did_not.join(", ")}.
        </div>
      )}

      {p.objections?.length > 0 && (
        <div className="hearings">{p.objections.map((o: any, i: number) => <Hearing key={i} c={{ ...o, gate: "A" }} />)}</div>
      )}

      {p.recommendation && (
        <div className="notice">
          <div className="small muted">AI suggestion. You decide.</div>
          {p.recommendation.text}
        </div>
      )}

      {p.computed && Object.keys(p.computed).length > 0 && (
        <>
          <KeyFigures computed={p.computed} />
          <More label="Show all the numbers"><ComputedTable computed={p.computed} /></More>
        </>
      )}
      {p.draft && Object.keys(p.draft).length > 0 && <ComputedTable computed={{ "AI's answer": p.draft }} />}
      {p.reason && <div className="small muted">Why you're seeing this: {plainReason(p.reason)}</div>}

      {item.approvals?.length > 0 && (
        <div className="small">Already approved by {item.approvals.map((a: any) => a.name).join(", then ")}.</div>
      )}

      {item.status === "open" ? (
        <div className="stack" style={{ borderTop: "1px solid var(--line-2)", paddingTop: 12 }}>
          {Object.entries(p.decision_fields || {}).map(([k, t]) => (
            <label key={k} className="field">{humanize(k)} (optional)
              <input type={t === "date" ? "date" : "text"} value={values[k] || ""} onChange={(e) => setValues({ ...values, [k]: e.target.value })} />
            </label>
          ))}
          <label className="field">Note (optional)
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. checked with the manager" />
          </label>
          <div className="row">
            {(OPTIONS[item.kind] || OPTIONS.reserved).map((o) => (
              <button key={o.decision} className={`btn ${o.kind || ""}`} disabled={busy || !canDecide} onClick={() => decide(o.decision)}>{o.label}</button>
            ))}
            <span className="spacer" />
            {item.kind === "reserved" && <button className="btn ghost small" onClick={agentTries}>Let the AI try to approve</button>}
          </div>
          {!canDecide && <div className="small muted">Only the {nextRole ? role(nextRole) : item.approver_roles.map(role).join(" or ")} can decide this. Change "You are" at the top.</div>}
          {p.clauses?.length > 0 && (
            <More label="Which rules were used">
              <div className="row small">{p.clauses.map((c: any) => <span key={c.pack} className="tag rule">{humanize(c.pack.split("@")[0])} {c.rule_ids?.join(", ")}</span>)}</div>
            </More>
          )}
        </div>
      ) : (
        <div className="row"><span className="tag ok">Decided: {humanize(item.decision?.decision || "")}</span></div>
      )}
      {error && <div className="refusal">{error}</div>}
    </div>
  );
}
