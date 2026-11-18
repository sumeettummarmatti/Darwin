import { Calculator, Check, Clock, Plug, ShieldAlert, Sparkles, Stamp, X } from "lucide-react";

export type Step = {
  id: string; title: string; kind: string; status: string; human_touch: number; model?: boolean;
  deterministic?: boolean; note?: string | null; gate?: string | null; tier?: number; cost_inr?: number;
  scheduled_for?: string | null; outputs?: any; connector?: string | null; action?: string | null; skill?: string | null;
  attempts?: number; needs?: string[];
};

function icon(step: Step) {
  if (step.status === "done" && step.kind !== "reserved" && step.kind !== "route_only") return <Check size={16} strokeWidth={3} />;
  if (["refused", "failed", "rejected"].includes(step.status)) return <X size={16} strokeWidth={3} />;
  if (step.status === "scheduled") return <Clock size={15} />;
  if (step.kind === "reserved") return <Stamp size={15} />;
  if (step.kind === "route_only") return <ShieldAlert size={15} />;
  if (step.kind === "connector") return <Plug size={15} />;
  return step.model ? <Sparkles size={15} /> : <Calculator size={15} />;
}

/** A run as a bridge: blue stations are the agent's, maroon seals are a human's. */
export function Rail({ steps, selected, onSelect }: { steps: Step[]; selected?: string | null; onSelect?: (id: string) => void }) {
  return (
    <div className="rail" role="list" aria-label="Workflow steps">
      {steps.map((s) => {
        const human = s.kind === "reserved" || s.kind === "route_only" || !!s.human_touch;
        const cls = [
          "station",
          s.status === "awaiting_human" ? "awaiting" : s.status,
          human ? "human" : "",
          selected === s.id ? "sel" : "",
        ].join(" ");
        return (
          <button key={s.id} className={cls} role="listitem" onClick={() => onSelect?.(s.id)} title={`${s.title} — ${s.status}`}>
            <span className="dot">{icon(s)}</span>
            <span className="lbl">{s.title}</span>
          </button>
        );
      })}
    </div>
  );
}

export function RailLegend() {
  return (
    <div className="legend">
      <span><i style={{ background: "var(--agent)" }} /> agent, no human touch</span>
      <span><i style={{ background: "var(--seal)" }} /> a named human decided</span>
      <span><i style={{ border: "2px dashed var(--agent)" }} /> scheduled or retrying</span>
      <span><i style={{ background: "var(--seal-soft)", border: "2px solid var(--seal)" }} /> refused or failed</span>
    </div>
  );
}
