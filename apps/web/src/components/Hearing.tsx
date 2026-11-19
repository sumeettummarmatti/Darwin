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
  A: "Gate A · before an irreversible action",
  B: "Gate B · policy change",
  C: "Gate C · new workflow",
  D: "Gate D · fair hiring",
};

function verdict(c: Charge): { label: string; tone: "seal" | "agent" | "rule" | "ok"; note: string } {
  if (c.verdict_override) return { ...c.verdict_override, note: "" };
  if (c.upheld === 1 || c.upheld === true) return { label: "Upheld", tone: "seal", note: "The objection stood. The risky action was corrected, verified or stopped." };
  if (c.upheld === 0 || c.upheld === false) return { label: "Overruled", tone: "agent", note: "A named human heard the objection and chose to proceed. Recorded with a receipt." };
  if (c.severity === "low") return { label: "Advisory", tone: "rule", note: "Logged for the record. Not severe enough to stop the run." };
  return { label: "Awaiting a human", tone: "rule", note: "The run is held until a named person decides." };
}

/** One Prativaad objection, read as a short hearing: the charge, the evidence, the defence, the verdict. */
export function Hearing({ c }: { c: Charge }) {
  const v = verdict(c);
  const evidence = Array.isArray(c.evidence) ? c.evidence : c.evidence ? [c.evidence] : [];
  // The kernel's resolution repeats the charge before what it found; show only what it found.
  const defence = c.resolution?.includes("— kernel verified:")
    ? "The kernel read the external system instead of acting: " + c.resolution.split("— kernel verified:").pop()!.trim()
    : c.resolution;
  return (
    <article className={`hearing tone-${v.tone}`}>
      <header className="hearing-head">
        <Gavel size={16} />
        <b>{c.class.replace(/_/g, " ")}</b>
        {c.severity && <span className={`tag ${c.severity === "high" ? "seal" : c.severity === "medium" ? "warn" : ""}`}>{c.severity}</span>}
        <span className="spacer" />
        <span className="small muted">{GATE_NAME[c.gate || "A"] || c.gate}{c.layer ? ` · ${c.layer === "model" ? "model reviewer" : "rule check"}` : ""}</span>
      </header>
      <div className="hearing-body">
        <div className="hearing-row">
          <span className="hearing-label">The charge</span>
          <p>{c.claim}</p>
        </div>
        {evidence.length > 0 && (
          <div className="hearing-row">
            <span className="hearing-label">Evidence</span>
            <div className="row">{evidence.map((e) => <span key={e} className="tag rule">{e}</span>)}</div>
          </div>
        )}
        <div className="hearing-row">
          <span className="hearing-label">Defence</span>
          <p>{defence || (c.suggested_action ? `Suggested remedy: ${c.suggested_action.replace(/_/g, " ")}.` : "None offered yet.")}</p>
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
