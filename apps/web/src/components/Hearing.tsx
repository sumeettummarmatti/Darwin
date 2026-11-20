import { Gavel } from "lucide-react";

export type Charge = {
  gate?: string;
  class: string;
  severity?: string;
  claim: string;
  evidence?: string[] | string;
  suggested_action?: string | null;
  layer?: string;
  resolution?: string | null;
  upheld?: number | boolean | null;
  verdict_override?: { label: string; tone: "seal" | "agent" | "rule" | "ok" };
};

const GATE_NAME: Record<string, string> = {
  A: "Before a permanent action",
  B: "Rule change",
  C: "New process",
  D: "Fair hiring",
};

const CLASS_NAME: Record<string, string> = {
  duplicate_side_effect: "Possible duplicate", pii_overreach: "Personal data about to leak", entitlement_mismatch: "Doesn't match the rules",
  reserved_leakage: "Skipped a person's decision", compensation_coverage: "Can't be undone", policy_version_staleness: "Using old rules",
  date_ordering: "Wrong date", proxy_bias: "Possible bias",
};

function verdict(c: Charge): { label: string; tone: "seal" | "agent" | "rule" | "ok"; note: string } {
  if (c.verdict_override) return { ...c.verdict_override, note: "" };
  if (c.upheld === 1 || c.upheld === true) return { label: "Upheld", tone: "seal", note: "Taken seriously and dealt with before anything happened." };
  if (c.upheld === 0 || c.upheld === false) return { label: "Overruled", tone: "agent", note: "A person looked at it and decided to go ahead." };
  if (c.severity === "low") return { label: "Advisory", tone: "rule", note: "Noted. Not serious enough to stop." };
  return { label: "Awaiting a human", tone: "rule", note: "On hold until a person decides." };
}

/** One Devil's Advocate objection, read as a short hearing: the charge, the evidence, the defence, the verdict. */
export function Hearing({ c }: { c: Charge }) {
  const v = verdict(c);
  const evidence = Array.isArray(c.evidence) ? c.evidence : c.evidence ? [c.evidence] : [];
  // The kernel's resolution repeats the charge before what it found; show only what it found.
  const defence = c.resolution?.includes("— kernel verified:")
    ? "HR Autopilot checked the other system first: " + c.resolution.split("— kernel verified:").pop()!.trim()
    : c.resolution;
  return (
    <article className={`hearing tone-${v.tone}`}>
      <header className="hearing-head">
        <Gavel size={16} />
        <b>{CLASS_NAME[c.class] || c.class.replace(/_/g, " ").replace(/^./, (x) => x.toUpperCase())}</b>
        {c.severity && <span className={`tag ${c.severity === "high" ? "seal" : c.severity === "medium" ? "warn" : ""}`}>{c.severity}</span>}
        <span className="spacer" />
        <span className="small muted">{GATE_NAME[c.gate || "A"] || c.gate}</span>
      </header>
      <div className="hearing-body">
        <div className="hearing-row">
          <span className="hearing-label">The charge</span>
          <p>{c.claim}</p>
        </div>
        {evidence.length > 0 && (
          <div className="hearing-row">
            <span className="hearing-label">Evidence</span>
            <div className="stack" style={{ gap: 2 }}>{evidence.map((e) => <span key={e} className="small">{e}</span>)}</div>
          </div>
        )}
        <div className="hearing-row">
          <span className="hearing-label">Defence</span>
          <p>{defence || (c.suggested_action ? `Suggested fix: ${c.suggested_action.replace(/_/g, " ")}.` : "None offered yet.")}</p>
        </div>
        <div className="hearing-row verdict-row">
          <span className="hearing-label">Verdict</span>
          <div className="row" style={{ gap: 14 }}>
            <span className={`verdict-stamp tone-${v.tone}`}>{v.label}</span>
            {v.note && <span className="small muted">{v.note}</span>}
          </div>
        </div>
      </div>
    </article>
  );
}
