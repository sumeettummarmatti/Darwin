import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api, fmtDur, fmtInr, fmtPct } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";
import { More, Pretty, humanize } from "../components/Pretty";

const TIER_COLORS = ["var(--agent)", "#7fb0c8", "var(--rule)", "var(--seal)"];
const TILE_NAME: Record<string, string> = {
  cost: "cost per run", automation: "fully automatic runs", escalation: "runs sent to a person",
  refusals: "blocked actions", objections: "objections",
};

export default function Overview() {
  const { go } = useApp();
  const [m] = usePoll<any>("/api/metrics", 4000);
  const [drill, setDrill] = useState<{ tile: string; workflow?: string; rows: any[] } | null>(null);

  async function open(tile: string, workflow?: string) {
    const rows = await api.get(`/api/metrics/drill?tile=${tile}${workflow ? `&workflow=${workflow}` : ""}`);
    setDrill({ tile, workflow, rows });
  }

  if (!m) return <div className="empty">Loading…</div>;
  const CORE_LINES = ["onboarding", "exit", "leave", "helpdesk"];
  const wfs = (Object.entries(m.workflows) as [string, any][]).filter(([n, w]) => w.runs > 0 || CORE_LINES.includes(n));
  const totalRuns = wfs.reduce((a, [, w]) => a + w.runs, 0);
  const g = m.governance;
  const pv = m.prativaad;

  return (
    <>
      <div className="page-head">
        <h1>Dashboard</h1>
        <p>Real numbers from the processes run so far. Click a number to see what's behind it.</p>
      </div>

      {totalRuns === 0 && (
        <div className="notice" style={{ marginBottom: 16 }}>
          Nothing has run yet. Go to <a href="#/story">Start here</a> and click the first step.
        </div>
      )}

      <div className="grid g3" style={{ marginBottom: 16 }}>
        <section className="panel panel-pad">
          <h2>Blocked</h2>
          <p className="sub">Things the AI tried that weren't allowed.</p>
          <button className="metric-btn" onClick={() => open("refusals")}>
            <div className="figure"><span className="n">{g.refusals}</span><span className="l">{g.refusals === 1 ? "action blocked" : "actions blocked"}</span></div>
          </button>
        </section>

        <section className="panel panel-pad">
          <h2>Decided by a person</h2>
          <p className="sub">Approvals only a human can give.</p>
          <div className="figure"><span className="n">{g.reserved_decisions}</span><span className="l">{g.reserved_decisions === 1 ? "approval" : "approvals"}{g.reserved_decisions ? ` · usually decided in ${fmtDur(g.time_to_approve_p50_s)}` : ""}</span></div>
          <div className="row small" style={{ marginTop: 14 }}>
            <ShieldCheck size={16} color={g.audit.ok ? "var(--ok)" : "var(--seal)"} />
            {g.audit.ok ? <>History log is untouched</> : <b style={{ color: "var(--seal)" }}>History log was changed at entry {g.audit.broken_at}</b>}
            <button className="btn small ghost" onClick={() => go("audit")}>Open</button>
          </div>
        </section>

        <section className="panel panel-pad">
          <h2>Caught by the checker</h2>
          <p className="sub">Problems spotted before something permanent happened.</p>
          <button className="metric-btn" onClick={() => open("objections")}>
            <div className="figure"><span className="n">{pv.objections}</span><span className="l">objections · {pv.upheld} of {pv.resolved} were right</span></div>
          </button>
        </section>
      </div>

      <section className="panel" style={{ marginBottom: 16, overflowX: "auto" }}>
        <div className="panel-pad" style={{ paddingBottom: 0 }}><h2>By process</h2></div>
        <table className="t">
          <thead>
            <tr><th>Process</th><th>Finished</th><th>Cost per run</th><th>Fully automatic</th><th>Sent to a person</th><th>Usual time to finish</th></tr>
          </thead>
          <tbody>
            {wfs.map(([name, w]) => (
              <tr key={name}>
                <td><b style={{ textTransform: "capitalize" }}>{name.replace(/_/g, " ")}</b></td>
                <td>{w.completed}<span className="muted small"> of {w.runs}</span></td>
                <td><button className="metric-btn" onClick={() => open("cost", name)}><b>{fmtInr(w.cost_p50, 2)}</b></button></td>
                <td><button className="metric-btn" onClick={() => open("automation", name)}><b>{fmtPct(w.automation_rate)}</b></button></td>
                <td><button className="metric-btn" onClick={() => open("escalation", name)}><b>{fmtPct(w.escalation_rate)}</b></button></td>
                <td>{fmtDur(w.cycle_p50_s)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {drill && (
        <section className="panel" style={{ marginBottom: 16 }}>
          <div className="row panel-pad" style={{ paddingBottom: 0 }}>
            <h2 style={{ margin: 0 }}>Behind the number: {TILE_NAME[drill.tile] || drill.tile}{drill.workflow ? `, ${drill.workflow}` : ""}</h2>
            <span className="spacer" />
            <button className="btn small ghost" onClick={() => setDrill(null)}>Close</button>
          </div>
          <DrillTable rows={drill.rows} onRun={(id) => go(`runs/${id}`)} />
        </section>
      )}

      <section className="panel panel-pad">
        <More label="Show cost details">
          <div className="grid g2">
            <div>
              <h2>Where the work ran</h2>
              <p className="sub">Most steps are plain rules and cost nothing. AI is used only where a rule can't decide.</p>
              <table className="t">
                <thead><tr><th>Process</th><th>Split</th><th>Slowest runs cost</th><th>Usual duration</th></tr></thead>
                <tbody>
                  {wfs.map(([name, w]) => {
                    const tiers = [0, 1, 2, 3].map((t) => w.tier_mix[t] || 0);
                    const sum = tiers.reduce((a, b) => a + b, 0) || 1;
                    return (
                      <tr key={name}>
                        <td style={{ textTransform: "capitalize" }}>{name.replace(/_/g, " ")}</td>
                        <td style={{ minWidth: 140 }}>
                          <div className="bar">{tiers.map((n, t) => n ? <span key={t} style={{ width: `${(n / sum) * 100}%`, background: TIER_COLORS[t] }} /> : null)}</div>
                          <div className="small muted">{Math.round((tiers[0] / sum) * 100)}% rules, {tiers[1] + tiers[2] + tiers[3]} AI</div>
                        </td>
                        <td>{fmtInr(w.cost_p95, 2)}</td>
                        <td>{fmtDur(w.cycle_p50_s)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="small muted">{m.models.escalations} times a bigger AI model was needed. The checker cost {fmtInr(pv.cost_inr, 2)} in total.</p>
            </div>
            <div>
              <h2>Monthly estimate</h2>
              <p className="sub">{m.projection.assumptions}</p>
              <table className="t">
                <thead><tr><th>Process</th><th>Runs a month</th><th>Per month</th></tr></thead>
                <tbody>
                  {m.projection.rows.map((r: any) => (
                    <tr key={r.workflow}><td style={{ textTransform: "capitalize" }}>{r.workflow}</td><td>{r.runs_per_month_assumed.toLocaleString("en-IN")}</td><td>{fmtInr(r.total_inr_per_month, 0)}</td></tr>
                  ))}
                  <tr><td colSpan={2}><b>Total, with hosting</b></td><td><b>{fmtInr(m.projection.total_inr_per_month, 0)}</b></td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </More>
      </section>
    </>
  );
}

function DrillTable({ rows, onRun }: { rows: any[]; onRun: (id: string) => void }) {
  if (!rows.length) return <div className="empty">Nothing here yet.</div>;
  const cols = Object.keys(rows[0]).filter((c) => !["detail", "evidence", "seq", "hash"].includes(c)).slice(0, 5);
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="t">
        <thead><tr>{cols.map((c) => <th key={c}>{humanize(c)}</th>)}{rows[0].detail && <th>Reason</th>}</tr></thead>
        <tbody>
          {rows.slice(0, 60).map((r, i) => (
            <tr key={i} className={r.run_id ? "click" : ""} onClick={() => r.run_id && onRun(r.run_id)}>
              {cols.map((c) => <td key={c}>{typeof r[c] === "number" ? (c.includes("inr") ? fmtInr(r[c], 2) : r[c]) : <Pretty v={r[c]} />}</td>)}
              {r.detail && <td className="small">{r.detail.reason}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
