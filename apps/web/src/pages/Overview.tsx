import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api, fmtDur, fmtInr, fmtPct, short } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";

const TIER_COLORS = ["var(--agent)", "#7fb0c8", "var(--rule)", "var(--seal)"];

export default function Overview() {
  const { go } = useApp();
  const [m] = usePoll<any>("/api/metrics", 4000);
  const [drill, setDrill] = useState<{ tile: string; workflow?: string; rows: any[] } | null>(null);

  async function open(tile: string, workflow?: string) {
    const rows = await api.get(`/api/metrics/drill?tile=${tile}${workflow ? `&workflow=${workflow}` : ""}`);
    setDrill({ tile, workflow, rows });
  }

  if (!m) return <div className="empty">Loading measurements…</div>;
  const CORE_LINES = ["onboarding", "exit", "leave", "helpdesk"];
  // Lines with no runs yet stay off the table, except the four core lines.
  const wfs = (Object.entries(m.workflows) as [string, any][]).filter(([n, w]) => w.runs > 0 || CORE_LINES.includes(n));
  const totalRuns = wfs.reduce((a, [, w]) => a + w.runs, 0);
  const g = m.governance;
  const pv = m.prativaad;

  return (
    <>
      <div className="page-head">
        <h1>What the agents did, and what the kernel refused</h1>
        <p>Measured from runs on the synthetic dataset, not estimated. Click any figure to see the rows behind it.</p>
      </div>

      {totalRuns === 0 && (
        <div className="notice" style={{ marginBottom: 16 }}>
          No runs yet. Open the <a href="#/story">demo story</a> to play the week at TBO, or run <span className="mono">make bench</span> to fill these figures.
        </div>
      )}

      <section className="panel" style={{ marginBottom: 16, overflowX: "auto" }}>
        <table className="t">
          <thead>
            <tr>
              <th>Service line</th><th>Completed</th><th>₹ per run · p50</th><th>p95</th><th>No human touch</th>
              <th>Escalated runs</th><th>Cycle time · p50</th><th style={{ minWidth: 160 }}>Where the work ran</th>
            </tr>
          </thead>
          <tbody>
            {wfs.map(([name, w]) => {
              const tiers = [0, 1, 2, 3].map((t) => w.tier_mix[t] || 0);
              const sum = tiers.reduce((a, b) => a + b, 0) || 1;
              return (
                <tr key={name}>
                  <td><b style={{ textTransform: "capitalize" }}>{name.replace(/_/g, " ")}</b><div className="small muted mono">{w.workflow}</div></td>
                  <td>{w.completed}<span className="muted small"> / {w.runs}</span></td>
                  <td><button className="metric-btn" onClick={() => open("cost", name)}><b>{fmtInr(w.cost_p50, 4)}</b></button>
                    <div className="small muted">budget {fmtInr(w.budget_inr_per_run, 2)}</div></td>
                  <td>{fmtInr(w.cost_p95, 4)}</td>
                  <td><button className="metric-btn" onClick={() => open("automation", name)}><b>{fmtPct(w.automation_rate)}</b></button>
                    <div className="small muted">target {fmtPct(w.target_automation_rate)}</div></td>
                  <td><button className="metric-btn" onClick={() => open("escalation", name)}><b>{fmtPct(w.escalation_rate)}</b></button></td>
                  <td>{fmtDur(w.cycle_p50_s)}</td>
                  <td>
                    <div className="bar" title={`tier 0: ${tiers[0]}, tier 1: ${tiers[1]}, tier 2: ${tiers[2]}`}>
                      {tiers.map((n, t) => n ? <span key={t} style={{ width: `${(n / sum) * 100}%`, background: TIER_COLORS[t] }} /> : null)}
                    </div>
                    <div className="small muted">{Math.round((tiers[0] / sum) * 100)}% code · {tiers[1]} small model · {tiers[2]} mid</div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <div className="grid g3" style={{ marginBottom: 16 }}>
        <section className="panel panel-pad">
          <h2>Refused by the kernel</h2>
          <p className="sub">Actions stopped by policy, RBAC, purpose limitation or the reserved list.</p>
          <button className="metric-btn" onClick={() => open("refusals")}>
            <div className="figure"><span className="n">{g.refusals}</span><span className="l">{fmtPct(g.policy_block_rate)} of governed actions</span></div>
          </button>
          <div className="stack small" style={{ marginTop: 14 }}>
            {Object.entries(g.refusals_by_reason).slice(0, 4).map(([reason, n]: any) => (
              <div key={reason} className="row"><span className="spacer" style={{ flex: "none", maxWidth: "80%" }}>{reason}</span><span className="spacer" /><b>{n}</b></div>
            ))}
          </div>
        </section>

        <section className="panel panel-pad">
          <h2>Decided by a named human</h2>
          <p className="sub">Reserved decisions, each with a receipt that hashes what was on screen.</p>
          <div className="figure"><span className="n">{g.reserved_decisions}</span><span className="l">receipts · median time to decide {fmtDur(g.time_to_approve_p50_s)}</span></div>
          <div className="row small" style={{ marginTop: 14 }}>
            <ShieldCheck size={16} color={g.audit.ok ? "var(--ok)" : "var(--seal)"} />
            {g.audit.ok ? <>Audit chain intact · {g.audit.checked} entries · head <span className="mono">{short(g.audit.head, 18)}</span></>
              : <b style={{ color: "var(--seal)" }}>Audit chain broken at entry {g.audit.broken_at}</b>}
          </div>
          <button className="btn small" style={{ marginTop: 12 }} onClick={() => go("audit")}>Open audit chain</button>
        </section>

        <section className="panel panel-pad">
          <h2>Prativaad, the devil's advocate</h2>
          <p className="sub">Objections raised before irreversible actions, and whether humans agreed.</p>
          <button className="metric-btn" onClick={() => open("objections")}>
            <div className="figure"><span className="n">{pv.objections}</span><span className="l">objections · precision {fmtPct(pv.precision)} ({pv.upheld} of {pv.resolved} upheld)</span></div>
          </button>
          <div className="small" style={{ marginTop: 14 }}>
            Rules layer {pv.by_layer.rules} · model layer {pv.by_layer.model}<br />
            Cost overhead {fmtInr(pv.cost_inr, 4)} ({fmtPct(pv.overhead_share)} of all run cost; capped at 8% of each run's budget)
          </div>
        </section>
      </div>

      {drill && (
        <section className="panel" style={{ marginBottom: 16 }}>
          <div className="row panel-pad" style={{ paddingBottom: 0 }}>
            <h2 style={{ margin: 0 }}>Behind the figure: {drill.tile}{drill.workflow ? ` · ${drill.workflow}` : ""}</h2>
            <span className="spacer" />
            <button className="btn small ghost" onClick={() => setDrill(null)}>Close</button>
          </div>
          <DrillTable rows={drill.rows} onRun={(id) => go(`runs/${id}`)} />
        </section>
      )}

      <div className="grid g2">
        <section className="panel panel-pad">
          <h2>Monthly projection</h2>
          <p className="sub">{m.projection.assumptions}</p>
          <table className="t">
            <thead><tr><th>Line</th><th>Runs / month (assumed)</th><th>Measured ₹/run</th><th>Per month</th></tr></thead>
            <tbody>
              {m.projection.rows.map((r: any) => (
                <tr key={r.workflow}><td style={{ textTransform: "capitalize" }}>{r.workflow}</td><td>{r.runs_per_month_assumed.toLocaleString("en-IN")}</td>
                  <td>{fmtInr(r.measured_inr_per_run_p50, 4)}</td><td>{fmtInr(r.total_inr_per_month, 0)}</td></tr>
              ))}
              <tr><td colSpan={3}><b>Total, including {fmtInr(m.projection.hosting_inr_per_month_assumed, 0)} hosting</b></td><td><b>{fmtInr(m.projection.total_inr_per_month, 0)}</b></td></tr>
            </tbody>
          </table>
        </section>
        <section className="panel panel-pad">
          <h2>Model calls by tier</h2>
          <p className="sub">Tier 0 is code and costs nothing to call. A larger model only runs on a measured trigger, which is logged with the call.</p>
          <table className="t">
            <thead><tr><th>Tier</th><th>Calls</th><th>Tokens in / out</th><th>Cost</th></tr></thead>
            <tbody>
              {Object.entries(m.models.by_tier).map(([tier, v]: any) => (
                <tr key={tier}><td>{tier}</td><td>{v.calls}</td><td className="mono">{v.tokens_in} / {v.tokens_out}</td><td>{fmtInr(v.inr, 4)}</td></tr>
              ))}
              {Object.keys(m.models.by_tier).length === 0 && <tr><td colSpan={4} className="muted">No model calls yet.</td></tr>}
            </tbody>
          </table>
          <div className="small muted" style={{ marginTop: 10 }}>{m.models.escalations} escalations on a measured trigger · profile <b>{m.models.profile}</b></div>
        </section>
      </div>
    </>
  );
}

function DrillTable({ rows, onRun }: { rows: any[]; onRun: (id: string) => void }) {
  if (!rows.length) return <div className="empty">Nothing here yet — which is the point of some of these figures.</div>;
  const cols = Object.keys(rows[0]).filter((c) => !["detail", "evidence"].includes(c)).slice(0, 7);
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="t">
        <thead><tr>{cols.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}{rows[0].detail && <th>reason</th>}</tr></thead>
        <tbody>
          {rows.slice(0, 60).map((r, i) => (
            <tr key={i} className={r.run_id ? "click" : ""} onClick={() => r.run_id && onRun(r.run_id)}>
              {cols.map((c) => <td key={c} className={c.endsWith("id") ? "mono" : ""}>{typeof r[c] === "number" ? (c.includes("inr") ? fmtInr(r[c], 4) : r[c]) : String(r[c] ?? "—")}</td>)}
              {r.detail && <td className="small">{r.detail.reason}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
