import { useEffect, useState } from "react";
import { Play } from "lucide-react";
import { api, fmtInr, fmtTime } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";
import { Rail, RailLegend, Step } from "../components/Rail";
import { ComputedTable, Packet } from "../components/Packet";
import { Hearing } from "../components/Hearing";
import { More, describeActor, describeEvent, humanize, plainReason, plainStatus, stepTitle } from "../components/Pretty";

const STATUS_TAG: Record<string, string> = { completed: "ok", waiting: "seal", running: "agent", paused: "warn", closed: "", cancelled: "", compensated: "warn" };
const nice = (w: string) => humanize(w);

export default function Runs({ arg }: { arg: string | null }) {
  const { go } = useApp();
  const [runs] = usePoll<any[]>("/api/runs?limit=80", 2500);
  const [filter, setFilter] = useState("");
  const selected = arg;
  const shown = (runs || []).filter((r) => !filter || r.workflow === filter);

  return (
    <>
      <div className="page-head">
        <h1>Processes</h1>
        <p>Every joiner, leaver, leave request and question, step by step.</p>
      </div>
      <StartRun />
      <div className="split" style={{ marginTop: 16 }}>
        <section className="panel">
          <div className="row panel-pad" style={{ paddingBottom: 8 }}>
            <h2 style={{ margin: 0 }}>All processes</h2><span className="spacer" />
            <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter">
              <option value="">Show all</option>
              {["onboarding", "exit", "leave", "helpdesk", "sourcing", "sourcing_reply"].map((w) => <option key={w} value={w}>{nice(w)}</option>)}
            </select>
          </div>
          <table className="t">
            <tbody>
              {shown.map((r) => (
                <tr key={r.id} className={`click ${selected === r.id ? "sel" : ""}`} onClick={() => go(`runs/${r.id}`)}>
                  <td>
                    <div className="row"><b>{nice(r.workflow)}</b><span className={`tag ${STATUS_TAG[r.status] || ""}`}>{plainStatus(r.status)}</span></div>
                    <div className="small muted">{r.subject_name || r.subject || "—"} · {fmtTime(r.created_at)}</div>
                  </td>
                  <td className="small muted" style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {r.progress.done + r.progress.skipped} of {r.progress.total} steps
                  </td>
                </tr>
              ))}
              {!shown.length && <tr><td className="empty">Nothing yet. Start one above.</td></tr>}
            </tbody>
          </table>
        </section>
        <div>{selected ? <RunDetail runId={selected} /> : <div className="panel empty">Pick one on the left to see its steps.</div>}</div>
      </div>
    </>
  );
}

function StartRun() {
  const { boot, user, go, toast } = useApp();
  const [workflow, setWorkflow] = useState("onboarding");
  const [subject, setSubject] = useState("EMP-4821");
  const [people] = usePoll<any[]>("/api/people?kind=employee", 0);
  const choices = (people || []).filter((p) => (workflow === "onboarding" ? p.attrs.status === "pre_joining" : p.attrs.status !== "pre_joining"));
  useEffect(() => { if (choices.length && !choices.find((c) => c.id === subject)) setSubject(choices[0].id); }, [workflow, people]);

  async function start() {
    try {
      const r = await api.post("/api/runs", { workflow, subject_id: subject, user_id: user.id, inputs: workflow === "helpdesk" ? { question: "What do I need to bring on day one?" } : {} });
      toast(`Started ${nice(workflow).toLowerCase()}`);
      go(`runs/${r.run_id}`);
    } catch (e: any) { toast(e.message); }
  }
  return (
    <section className="panel panel-pad row" style={{ gap: 12 }}>
      <b>Start</b>
      <select value={workflow} onChange={(e) => setWorkflow(e.target.value)} aria-label="Process">
        {boot.workflows.filter((w: any) => !w.name.startsWith("sourcing")).map((w: any) => <option key={w.name} value={w.name}>{nice(w.name)}</option>)}
      </select>
      <span className="small muted">for</span>
      <select value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="Person">
        {choices.map((p) => <option key={p.id} value={p.id}>{p.display_name} ({p.attrs.org_unit})</option>)}
      </select>
      <span className="spacer" />
      <button className="btn primary" onClick={start}><Play size={15} /> Start</button>
    </section>
  );
}

function RunDetail({ runId }: { runId: string }) {
  const [d, reload] = usePoll<any>(`/api/runs/${runId}`, 2000);
  const [sel, setSel] = useState<string | null>(null);
  if (!d) return <div className="panel empty">Loading…</div>;
  const steps: Step[] = d.steps;
  const step = steps.find((s) => s.id === sel) || steps.find((s) => s.status === "awaiting_human") || null;
  const openItem = d.queue.find((q: any) => q.status === "open" && (!step || q.step_id === step.id));
  const human = steps.filter((s) => s.status === "done" && s.human_touch).length;
  const done = steps.filter((s) => s.status === "done").length;

  return (
    <div className="stack">
      <section className="panel panel-pad">
        <div className="row">
          <div>
            <h2 style={{ fontSize: 20 }}>{nice(d.run.workflow)}: {d.subject?.display_name || d.run.subject || "—"}</h2>
            <div className="small muted">{plainStatus(d.run.status)} · {done} of {steps.length} steps done · {done ? Math.round(((done - human) / done) * 100) : 0}% automatic · cost {fmtInr(d.run.cost_inr)}</div>
          </div>
        </div>
        <Rail steps={steps} selected={step?.id} onSelect={setSel} />
        <RailLegend />
      </section>

      {openItem && (
        <section className="panel panel-pad" style={{ borderColor: "var(--seal)" }}>
          <Packet item={openItem} onDecided={() => reload()} />
        </section>
      )}

      {step && <StepDetail step={step} d={d} />}

      <section className="panel panel-pad">
        <More label="Show the full history of this process">
          <AuditList entries={d.audit} />
        </More>
      </section>
    </div>
  );
}

function whatItDoes(step: Step): string {
  if (step.kind === "reserved") return "Needs a person's approval. The AI can't do this.";
  if (step.kind === "route_only") return "Passed straight to the right person. The AI doesn't read or judge it.";
  if (step.kind === "connector") return "Updates another system.";
  if (step.model) return "Uses AI.";
  return "Worked out by rules. No AI.";
}

function StepDetail({ step, d }: { step: Step; d: any }) {
  const calls = d.model_calls.filter((c: any) => c.step_id === step.id);
  // The AI reviewer often repeats a concern the rules already raised; show each kind of concern once.
  const objections = d.objections.filter((o: any, i: number, all: any[]) =>
    o.step_id === step.id && all.findIndex((x: any) => x.step_id === step.id && x.class === o.class) === i);
  const outputs = step.outputs && typeof step.outputs === "object" ? step.outputs : null;
  return (
    <section className="panel panel-pad">
      <div className="row">
        <h2 style={{ margin: 0 }}>{stepTitle(step.title)}</h2>
        <span className={`tag ${step.status === "done" ? "ok" : step.status === "awaiting_human" ? "seal" : ""}`}>{plainStatus(step.status)}</span>
      </div>
      <div className="small muted" style={{ margin: "6px 0 12px" }}>
        {whatItDoes(step)}
        {step.attempts && step.attempts > 1 ? ` Tried ${step.attempts} times.` : ""}
        {step.scheduled_for ? ` Scheduled for ${fmtTime(step.scheduled_for)}.` : ""}
        {step.note && step.kind !== "route_only" ? ` ${step.note}` : ""}
      </div>
      {objections.length > 0 && (
        <div className="hearings" style={{ marginBottom: 12 }}>
          {objections.map((o: any) => <Hearing key={o.id} c={o} />)}
        </div>
      )}
      {outputs && Object.keys(outputs).length > 0 && (step.kind === "connector" ? (
        <>
          {outputs.record_id && <div className="small">Done once, record <b>{String(outputs.record_id)}</b>{outputs.status ? ` (${humanize(String(outputs.status)).toLowerCase()})` : ""}.</div>}
          <More label="What the other system sent back"><ComputedTable computed={{ result: outputs }} /></More>
        </>
      ) : <ComputedTable computed={{ result: outputs }} />)}
      {calls.map((c: any) => (
        <div key={c.id} className="notice small" style={{ marginTop: 8 }}>
          {String(c.skill).includes("devils_advocate") ? "The Devil's Advocate asked the AI for a second opinion" : c.tier >= 2 ? "Used the bigger AI model" : "Used AI"} ({fmtInr(c.inr)}).{c.tier >= 2 && c.escalation_reason ? ` ${plainReason(c.escalation_reason)}` : ""}
          {" "}<a href={`#/privacy/${c.id}`}>See exactly what the AI was sent</a>
        </div>
      ))}
    </section>
  );
}

export function AuditList({ entries }: { entries: any[] }) {
  const { users } = useApp();
  return (
    <table className="t">
      <tbody>
        {entries.map((e) => {
          const bad = e.outcome === "refused" || e.outcome === "failed";
          const raw = e.detail?.reason || e.detail?.route_reason || e.detail?.verified;
          const why = typeof raw === "string" && /read-back found exactly one/.test(raw) ? "checked afterwards: exactly one record" : raw;
          return (
            <tr key={e.seq}>
              <td className="muted small" style={{ width: 44 }}>{e.seq}</td>
              <td>
                <div className="row">
                  <span>{describeEvent(e.action)}</span>
                  {e.outcome && e.outcome !== "ok" && <span className={`tag ${bad ? "seal" : e.outcome === "cleared" ? "ok" : e.outcome === "objected" ? "rule" : ""}`}>{plainStatus(e.outcome)}</span>}
                </div>
                <div className="small muted">
                  {describeActor(e.actor, users)} · {fmtTime(e.at)}{e.inr > 0 ? ` · ${fmtInr(e.inr)}` : ""}{why ? ` · ${why}` : ""}
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
