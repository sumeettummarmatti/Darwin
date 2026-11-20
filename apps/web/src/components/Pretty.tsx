// Renders any value as something a person can read: no raw JSON anywhere in the console.

export const humanize = (key: string) =>
  key.replace(/^(args|steps|subject|inputs|facts|plan)\./, "").replace(/[._]/g, " ").replace(/\s+/g, " ").trim().replace(/^./, (c) => c.toUpperCase());

const ISO_DATE = /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?([+-]\d{2}:\d{2}|Z)?)?$/;

function Text({ s }: { s: string }) {
  if (s.startsWith("tok_")) return <span className="tok" title="vault token — the raw value never leaves the vault">{s}</span>;
  if (ISO_DATE.test(s)) {
    const d = new Date(s.length === 10 ? s + "T00:00:00" : s);
    if (!isNaN(d.getTime())) return <span>{s.length === 10 ? d.toLocaleDateString("en-IN", { dateStyle: "medium" }) : d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</span>;
  }
  if (s.includes("«")) return <span>{s.split(/(«[^»]+»)/g).map((p, i) => (p.startsWith("«") ? <span key={i} className="tok">{p}</span> : p))}</span>;
  return <span style={{ whiteSpace: "pre-wrap" }}>{s}</span>;
}

export function Pretty({ v, depth = 0 }: { v: any; depth?: number }) {
  if (v === null || v === undefined || v === "") return <span className="muted">—</span>;
  if (typeof v === "boolean") return <span className={`tag ${v ? "ok" : "warn"}`}>{v ? "yes" : "no"}</span>;
  if (typeof v === "number") return <span style={{ fontVariantNumeric: "tabular-nums" }}>{v.toLocaleString("en-IN", { maximumFractionDigits: 4 })}</span>;
  if (typeof v === "string") return <Text s={v} />;
  if (Array.isArray(v)) {
    if (!v.length) return <span className="muted">none</span>;
    if (v.every((x) => x === null || typeof x !== "object")) {
      return <span className="row" style={{ gap: 4 }}>{v.map((x, i) => <span key={i} className="tag"><Pretty v={x} depth={depth + 1} /></span>)}</span>;
    }
    const shown = v.slice(0, 6);
    return (
      <div className="pretty-list">
        {shown.map((x, i) => <div key={i} className="pretty-item"><Pretty v={x} depth={depth + 1} /></div>)}
        {v.length > shown.length && <div className="small muted">and {v.length - shown.length} more</div>}
      </div>
    );
  }
  const entries = Object.entries(v).filter(([k]) => !k.startsWith("_"));
  if (!entries.length) return <span className="muted">—</span>;
  if (depth > 2) return <span className="small muted">{entries.length} fields</span>;
  return (
    <dl className="pretty-obj">
      {entries.map(([k, x]) => (
        <div key={k} className="pretty-pair">
          <dt>{humanize(k)}</dt>
          <dd><Pretty v={x} depth={depth + 1} /></dd>
        </div>
      ))}
    </dl>
  );
}

/** "employment type fixed term · grade L2 · state IN-KA" — for one-line summaries of a case. */
export const sentence = (o: Record<string, any>) =>
  Object.entries(o || {}).map(([k, v]) => `${humanize(k).toLowerCase()} ${Array.isArray(v) ? v.join(", ") : v === null ? "none" : String(v)}`).join(" · ");

/** "exit.accept_resignation" → "Accept resignation"; "connector.assets.allocate" → "Assets: allocate". */
export function plainAction(action: string | null | undefined): string {
  if (!action) return "";
  const parts = action.replace(/^(connector|drill|step|system|kernel)\./, "").split(".");
  const words = parts.map((p) => p.replace(/_/g, " "));
  const text = words.length > 1 ? `${words.slice(0, -1).join(" ")}: ${words.at(-1)}` : words[0];
  return text.replace(/^./, (c) => c.toUpperCase()).replace(/\bhr\b/gi, "HR");
}

const STATUS: Record<string, string> = {
  done: "Done", completed: "Finished", awaiting_human: "Waiting for a person", waiting: "Waiting for a person",
  scheduled: "Scheduled", running: "Running", pending: "Not started", refused: "Blocked", failed: "Failed",
  rejected: "Rejected", skipped: "Skipped", paused: "Paused", closed: "Closed", cancelled: "Cancelled",
  compensated: "Undone", retrying: "Retrying", ok: "OK", cleared: "Cleared", objected: "Objection raised",
};
export const plainStatus = (s: string | null | undefined) => (s ? STATUS[s] || humanize(s) : "");

/** Technical detail, folded away until someone asks for it. */
export function More({ label = "Show details", children }: { label?: string; children: any }) {
  return (
    <details className="more">
      <summary>{label}</summary>
      <div className="more-body">{children}</div>
    </details>
  );
}

const words = (s: string) => s.replace(/_/g, " ");

/** A history-log action as a short sentence: "policy.evaluate.notice_period" → "Checked the notice period rules". */
export function describeEvent(action: string): string {
  const [head, second, ...rest] = action.split(".");
  const tail = words([second, ...rest].filter(Boolean).join(" "));
  const last = words(action.split(".").at(-1) || "");
  switch (head) {
    case "run": return second === "start" ? `Started ${words(rest.join(" "))}` : `Process ${tail}`;
    case "policy": return `Checked the ${last} rules`;
    case "step": return second === "skip" ? `Skipped ${last} (not needed)` : second === "complete" ? `Finished ${last}` : `Step ${tail}`;
    case "model": return second === "prativaad" ? "The checker asked the AI for a second opinion" : `Asked the AI: ${last}`;
    case "queue": return `Sent to a person: ${last}`;
    case "prativaad": return "The checker reviewed it before acting";
    case "route_only": return `Passed to the right person without the AI reading it: ${last}`;
    case "dpdp": return `Privacy: ${last}`;
    default: return plainAction(action);
  }
}

/** "human:USR-101" → "Priya Sharma"; "agent:exit@v1" → "AI helper"; "kernel" → "SETU". */
export function describeActor(actor: string, users: { id: string; name: string }[] = []): string {
  if (actor.startsWith("human:")) return users.find((u) => u.id === actor.slice(6))?.name || "A person";
  if (actor.startsWith("agent:")) return "AI helper";
  if (actor === "prativaad") return "Checker";
  if (actor.startsWith("system:")) return "Setup";
  return "SETU";
}

/** Router and kernel reasons, in words: "escalate_when 'confidence < 0.8' fired {'confidence': 0.6}" → "the AI was only 60% sure (it needs 80%)". */
export function plainReason(reason: string | null | undefined): string {
  if (!reason) return "";
  const m = reason.match(/'confidence\s*<\s*([\d.]+)'\s*fired\s*\{'confidence':\s*([\d.]+)\}/);
  if (m) {
    const pct = (x: string) => `${Math.round(Number(x) * 100)}%`;
    const tail = /highest permitted tier/.test(reason) ? ", even with the bigger model" : "";
    return `The AI was only ${pct(m[2])} sure (it needs ${pct(m[1])})${tail}.`;
  }
  if (/schema violation/.test(reason)) return "The first answer wasn't in the expected format, so a bigger model tried.";
  const t = reason.match(/escalate_when '([^']+)' fired/);
  if (t) return `A check on the AI's answer (${t[1].replace(/_/g, " ")}) asked for a second look.`;
  return reason.replace(/^measured trigger:\s*/, "").replace(/ — low confidence is treated like a reserved decision/, "");
}

// Friendlier names for step titles that are written for developers in the workflow files.
const STEP_TITLES: Record<string, string> = {
  "Set up payroll (PAN and bank as vault tokens)": "Set up payroll",
  "Suspend (not delete) email after the last working day": "Suspend email after the last day",
  "Compute final settlement by rule": "Work out final pay",
  "Prepare settlement draft in payroll": "Draft final pay in payroll",
  "Start DPDP retention clocks": "Schedule data deletion",
  "Gather public signals (pointer-shaped)": "Find people online",
  "Screen letter for route-only matters": "Check the letter for complaints",
  "Route grievance — and stop": "Pass complaint to the ethics officer",
  "Lawful-basis gate": "Check we may use their data",
  "Store pointers — link only, nothing derived": "Save links only",
  "Suppress permanently and delete the pointer": "Never contact again, delete link",
  "Fetch applicants from the ATS": "Get applicants",
  "Extract claims with evidence spans": "Pull facts from CVs",
  "Extract claims about this person": "Pull facts about this person",
  "Score by ICP rule (no model)": "Score applicants",
  "Prativaad gate D — proxy-bias challenge": "Check for bias",
  "No-raid guard (TBO's obligations)": "Check no-hire agreements",
  "Send notice-first contact (within the approval)": "Send first message",
  "Record applicants with their basis": "Save applicants",
  "Compute notice period by rule": "Work out notice period",
  "Preview settlement by rule (gratuity, encashment)": "Estimate final pay",
  "Resolve entitlements by rule": "Work out laptop and kit",
  "Evaluate against the leave pack": "Check leave rules",
  "Compute encashment by rule": "Work out leave payout",
  "Compute the review date by rule": "Work out review date",
  "Answer from policy clauses": "Answer from the rules",
  "Payroll band exception": "Salary band exception",
  "Revoke access card at 18:00 on the last working day": "Cancel access card on the last day",
  "Prepare decision packet": "Prepare summary for managers",
  "Create email + directory entry": "Create email account",
  "Raise IT provisioning ticket": "Open IT ticket",
  "Manager approval (beyond auto-booking limit)": "Manager approval",
  "Record consent and upgrade the record": "Save their consent",
  "Policy exception (exceeds balance)": "Exception: not enough leave",
  "Probation and day-one terms": "Probation and first-day terms",
};
export const stepTitle = (t: string) => STEP_TITLES[t] || t;
