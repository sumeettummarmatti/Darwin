import { useEffect, useState } from "react";
import { Play } from "lucide-react";
import { api, fmtInr, fmtTime, short } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";
import { Rail, RailLegend, Step } from "../components/Rail";
import { ComputedTable, Packet } from "../components/Packet";
import { Hearing } from "../components/Hearing";

const STATUS_TAG: Record<string, string> = { completed: "ok", waiting: "seal", running: "agent", paused: "warn", closed: "", cancelled: "", compensated: "warn" };

export default function Runs({ arg }: { arg: string | null }) {
  const { go } = useApp();
  const [runs] = usePoll<any[]>("/api/runs?limit=80", 2500);
  const [filter, setFilter] = useState("");
  const selected = arg;
  const shown = (runs || []).filter((r) => !filter || r.workflow === filter);

  return (
    <>
      <div className="page-head">
        <h1>Workflows</h1>
        <p>Every run walks the same governed path: propose, Prativaad, policy, reserved check, keyed execution, read-back, audit.</p>
      </div>
      <StartRun />
      <div className="split" style={{ marginTop: 16 }}>
        <section className="panel">
          <div className="row panel-pad" style={{ paddingBottom: 8 }}>
            <h2 style={{ margin: 0 }}>Runs</h2><span className="spacer" />
            <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter by workflow">
              <option value="">All lines</option>
              {["onboarding", "exit", "leave", "helpdesk", "sourcing", "sourcing_reply"].map((w) => <option key={w}>{w}</option>)}
            </select>
          </div>
          <table className="t">
            <tbody>
              {shown.map((r) => (
                <tr key={r.id} className={`click ${selected === r.id ? "sel" : ""}`} onClick={() => go(`runs/${r.id}`)}>
                  <td>
                    <div className="row"><b style={{ textTransform: "capitalize" }}>{r.workflow}</b><span className={`tag ${STATUS_TAG[r.status] || ""}`}>{r.status}</span></div>
                    <div className="small muted">{r.subject_name || r.subject || "—"} · {r.channel} · {fmtTime(r.created_at)}</div>
                  </td>
                  <td className="small" style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {r.progress.done + r.progress.skipped}/{r.progress.total}<br /><span className="muted">{fmtInr(r.cost_inr, 4)}</span>
                  </td>
                </tr>
              ))}
              {!shown.length && <tr><td className="empty">No runs yet. Start one above or play the demo story.</td></tr>}
            </tbody>
          </table>
        </section>
        <div>{selected ? <RunDetail runId={selected} /> : <div className="panel empty">Pick a run to see its rail, its decisions and its audit narration.</div>}</div>
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
      toast(`Started ${workflow} for ${subject}`);
      go(`runs/${r.run_id}`);
    } catch (e: any) { toast(e.message); }
  }
  return (
    <section className="panel panel-pad row" style={{ gap: 12 }}>
      <b>Start a run</b>
      <select value={workflow} onChange={(e) => setWorkflow(e.target.value)} aria-label="Workflow">
        {boot.workflows.filter((w: any) => !w.name.startsWith("sourcing")).map((w: any) => <option key={w.name} value={w.name}>{w.name} · {w.ref}</option>)}
      </select>
      <select value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="Subject">
        {choices.map((p) => <option key={p.id} value={p.id}>{p.display_name} · {p.id} · {p.attrs.org_unit}</option>)}
      </select>
      <span className="small muted">on behalf of {user.name}</span>
      <span className="spacer" />
      <button className="btn primary" onClick={start}><Play size={15} /> Start</button>
    </section>
  );
}

function RunDetail({ runId }: { runId: string }) {
  const { user } = useApp();
  const [d, reload] = usePoll<any>(`/api/runs/${runId}`, 2000);
  const [sel, setSel] = useState<string | null>(null);
  if (!d) return <div className="panel empty">Loading run…</div>;
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
            <h2 style={{ fontSize: 20, textTransform: "capitalize" }}>{d.run.workflow} · {d.subject?.display_name || d.run.subject}</h2>
            <div className="small muted">
              {d.workflow.ref} · <span className="mono">{d.run.id}</span> · on behalf of {d.run.principal} via {d.run.channel}
            </div>
          </div>
          <span className="spacer" />
          <div className="figure" style={{ textAlign: "right" }}>
            <span className="n" style={{ fontSize: 24 }}>{fmtInr(d.run.cost_inr, 4)}</span>
            <span className="l">of {fmtInr(d.workflow.budget_inr_per_run, 2)} budget · {done ? Math.round(((done - human) / done) * 100) : 0}% no human touch</span>
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

      <section className="panel">
        <div className="panel-pad" style={{ paddingBottom: 4 }}>
          <h2>Audit narration</h2>
          <p className="sub">Built from the hash-linked log, not from a model asked to remember. Every entry names the actor, the policy versions and the cost.</p>
        </div>
        <AuditList entries={d.audit} />
      </section>
    </div>
  );
}

function StepDetail({ step, d }: { step: Step; d: any }) {
  const calls = d.model_calls.filter((c: any) => c.step_id === step.id);
  const objections = d.objections.filter((o: any) => o.step_id === step.id);
  const outputs = step.outputs && typeof step.outputs === "object" ? step.outputs : null;
  return (
    <section className="panel panel-pad">
      <div className="row">
        <h2 style={{ margin: 0 }}>{step.title}</h2>
        <span className="tag">{step.kind}</span>
        <span className={`tag ${step.status === "done" ? "ok" : step.status === "awaiting_human" ? "seal" : ""}`}>{step.status.replace("_", " ")}</span>
        {step.kind === "skill" && <span className={`tag ${step.model ? "agent" : "rule"}`}>{step.model ? `model · tier ${step.tier}` : "tier 0 · code"}</span>}
        {step.cost_inr ? <span className="tag">{fmtInr(step.cost_inr, 5)}</span> : null}
      </div>
      <div className="small muted" style={{ margin: "6px 0 12px" }}>
        {step.connector ? <>connector <b>{step.connector}.{step.action}</b></> : step.skill ? <>skill <b>{step.skill}</b></> : step.action ? <>action <b>{step.action}</b></> : null}
        {step.attempts ? ` · ${step.attempts} attempt(s)` : ""}{step.scheduled_for ? ` · scheduled ${fmtTime(step.scheduled_for)}` : ""}
        {step.note ? ` · ${step.note}` : ""}
      </div>
      {objections.length > 0 && (
        <div className="hearings" style={{ marginBottom: 12 }}>
          {objections.map((o: any) => <Hearing key={o.id} c={o} />)}
        </div>
      )}
      {outputs && Object.keys(outputs).length > 0 && <ComputedTable computed={{ outputs }} />}
      {calls.map((c: any) => (
        <div key={c.id} className="notice small" style={{ marginTop: 8 }}>
          Model call <span className="mono">{c.model}</span> tier {c.tier} · {c.tokens_in}+{c.tokens_out} tokens · {fmtInr(c.inr, 5)} — {c.escalation_reason}
          {" "}<a href={`#/privacy/${c.id}`}>See the exact payload</a>
        </div>
      ))}
    </section>
  );
}

export function AuditList({ entries }: { entries: any[] }) {
  return (
    <table className="t">
      <tbody>
        {entries.map((e) => (
          <tr key={e.seq}>
            <td className="mono muted" style={{ width: 52 }}>#{e.seq}</td>
            <td>
              <div className="row">
                <b className="mono" style={{ fontSize: 13 }}>{e.action}</b>
                <span className={`tag ${e.outcome === "refused" || e.outcome === "failed" ? "seal" : e.outcome === "ok" || e.outcome === "cleared" ? "ok" : e.outcome === "objected" ? "rule" : ""}`}>{e.outcome}</span>
                {e.policy_versions?.map((p: string) => <span key={p} className="tag rule">{p}</span>)}
                {e.inr > 0 && <span className="tag">{fmtInr(e.inr, 5)}</span>}
                {e.model_id && <span className="tag agent">{e.model_id}</span>}
              </div>
              <div className="small muted">
                {e.actor}{e.on_behalf_of ? ` for ${e.on_behalf_of}` : ""} · {fmtTime(e.at)}
                {e.rule_ids?.length ? ` · rules ${e.rule_ids.slice(0, 6).join(", ")}` : ""}
                {e.detail?.reason ? ` · ${e.detail.reason}` : ""}{e.detail?.verified ? ` · ${e.detail.verified}` : ""}
                {e.detail?.route_reason ? ` · ${e.detail.route_reason}` : ""}
              </div>
            </td>
            <td className="mono muted small" style={{ whiteSpace: "nowrap" }}>{short(e.hash, 14)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
