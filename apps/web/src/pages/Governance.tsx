import { useState } from "react";
import { api, fmtTime } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";
import { ProviderKey } from "../components/ProviderKey";

export default function Governance() {
  return (
    <>
      <div className="page-head">
        <h1>Guardrails</h1>
        <p>The reserved list is configuration HR can change. The kill switch is a row in a table. Neither needs a deploy, and the kernel enforces both.</p>
      </div>
      <div className="stack" style={{ gap: 16 }}>
        <Drill />
        <div className="grid g2">
          <KillSwitch />
          <Chaos />
        </div>
        <Registry />
        <ProviderKey />
        <Provider />
      </div>
    </>
  );
}

function Drill() {
  const { user } = useApp();
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    setRes(await api.post("/api/drill", { user_id: user.id }));
    setBusy(false);
  }
  return (
    <section className="panel panel-pad">
      <div className="row">
        <div>
          <h2>Reserved-decision drill</h2>
          <p className="sub" style={{ margin: 0 }}>An agent deliberately attempts every reserved action, every forbidden verb and every route-only matter. Each one must come back refused, with an audit entry.</p>
        </div>
        <span className="spacer" />
        <button className="btn seal" onClick={run} disabled={busy}>{busy ? "Running…" : "Run the drill"}</button>
      </div>
      {res && (
        <div style={{ marginTop: 16 }}>
          <div className="row" style={{ gap: 20, alignItems: "center", marginBottom: 12 }}>
            <div className={`seal-stamp stamp-in ${res.all_refused ? "" : "ok"}`} style={{ width: 110, height: 110 }}>
              <b>{res.results.filter((r: any) => r.outcome === "refused").length}/{res.results.length}</b>
              <small>REFUSED · 403</small>
            </div>
            <p style={{ maxWidth: 520 }}>
              {res.all_refused ? "Every attempt was refused by the kernel, not hidden by the UI. Each refusal is in the audit chain with its reason." : "Some attempts were not refused — this is a bug and should fail the build."}
            </p>
          </div>
          <table className="t">
            <thead><tr><th>Attempted action</th><th>Status</th><th>Kernel's reason</th><th>Audit</th></tr></thead>
            <tbody>
              {res.results.map((r: any) => (
                <tr key={r.action}><td className="mono">{r.action}</td><td><span className={`tag ${r.outcome === "refused" ? "seal" : "warn"}`}>{r.status} {r.outcome}</span></td>
                  <td className="small">{r.reason}</td><td className="mono small">#{r.audit_seq}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function KillSwitch() {
  const { user, boot, toast } = useApp();
  const [data, reload] = usePoll<any>("/api/killswitch", 3000);
  const [scope, setScope] = useState("workflow");
  const [target, setTarget] = useState("leave");
  const [reason, setReason] = useState("");
  const targets: Record<string, string[]> = {
    global: ["*"],
    workflow: boot.workflows.map((w: any) => w.name),
    skill: boot.registry.skills,
    connector: boot.registry.connectors,
  };
  async function set(active: boolean, s = scope, t = target) {
    await api.post("/api/killswitch", { scope: s, target: s === "global" ? "*" : t, active, reason, user_id: user.id });
    toast(active ? `Engaged: ${s}:${t}. In-flight work parks with its context.` : `Released: ${s}:${t}`);
    reload();
  }
  const active = (data?.switches || []).filter((s: any) => s.active);
  return (
    <section className="panel panel-pad">
      <h2>Kill switch</h2>
      <p className="sub">Four blast radii. Paused runs park in the decision queue so HR can finish them by hand.</p>
      <div className="row">
        <select value={scope} onChange={(e) => { setScope(e.target.value); setTarget(targets[e.target.value][0]); }} aria-label="Scope">
          {Object.keys(targets).map((s) => <option key={s}>{s}</option>)}
        </select>
        {scope !== "global" && (
          <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Target">
            {targets[scope].map((t) => <option key={t}>{t}</option>)}
          </select>
        )}
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (recorded)" style={{ flex: 1, minWidth: 140 }} />
        <button className="btn seal" onClick={() => set(true)}>Engage</button>
      </div>
      <div className="stack" style={{ marginTop: 14 }}>
        {active.map((s: any) => (
          <div key={s.scope + s.target} className="refusal row">
            <div><b>{s.scope}:{s.target}</b><div className="small">{s.reason || "no reason given"} · by {s.actor} · {fmtTime(s.at)}</div></div>
            <span className="spacer" />
            <button className="btn small" onClick={() => set(false, s.scope, s.target)}>Release</button>
          </div>
        ))}
        {!active.length && <div className="small muted">Nothing paused. The automatic circuit breaker will engage a workflow switch itself if its escalation rate crosses the threshold in policies/circuit_breakers.</div>}
      </div>
    </section>
  );
}

function Chaos() {
  const { toast } = useApp();
  const [data, reload] = usePoll<any>("/api/mocks/chaos", 2500);
  const [ks] = usePoll<any>("/api/killswitch", 2500);
  const [system, setSystem] = useState("assets");
  const [mode, setMode] = useState("error_500");
  async function apply(m = mode) {
    await api.post("/api/mocks/chaos", { system, mode: m, count: 3 });
    toast(m === "clear" ? `${system} recovered` : `${system} now returns ${m}`);
    reload();
  }
  return (
    <section className="panel panel-pad">
      <h2>Break a TBO system</h2>
      <p className="sub">The mocks are deliberately not idempotent. Duplicate prevention is the kernel's job: same key, outbox, read-back.</p>
      <div className="row">
        <select value={system} onChange={(e) => setSystem(e.target.value)} aria-label="System">
          {["assets", "tickets", "access", "directory", "payroll", "mail"].map((s) => <option key={s}>{s}</option>)}
        </select>
        <select value={mode} onChange={(e) => setMode(e.target.value)} aria-label="Failure mode">
          <option value="error_500">500 errors ×3</option>
          <option value="timeout_after_commit">timeout after commit</option>
          <option value="ack_no_commit">200 but nothing written</option>
          <option value="down">down until restored</option>
        </select>
        <button className="btn seal" onClick={() => apply()}>Inject</button>
        <button className="btn" onClick={() => apply("clear")}>Restore</button>
      </div>
      <div className="small" style={{ marginTop: 12 }}>
        {(data?.chaos || []).map((c: any) => <span key={c.system} className="tag seal" style={{ marginRight: 6 }}>{c.system}: {c.mode}{c.remaining > 0 ? ` ×${c.remaining}` : ""}</span>)}
        {(ks?.breakers || []).filter((b: any) => b.state !== "closed").map((b: any) => <span key={b.name} className="tag warn" style={{ marginRight: 6 }}>breaker {b.name}: {b.state}</span>)}
      </div>
      <table className="t" style={{ marginTop: 8 }}>
        <tbody>
          {(data?.calls || []).slice(0, 7).map((c: any) => (
            <tr key={c.seq}><td className="mono small">{c.system}.{c.op}</td><td><span className={`tag ${c.outcome === "ok" ? "ok" : "seal"}`}>{c.outcome}</span></td><td className="small muted">{fmtTime(c.at)}</td></tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Registry() {
  const { user, toast, reloadBoot } = useApp();
  const [reg, reload] = usePoll<any>("/api/reserved", 0);
  const [draft, setDraft] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  if (!reg) return null;
  async function save() {
    const r = await api.post("/api/reserved", { yaml: draft, user_id: user.id });
    setResult(r);
    if (r.ok) { toast(`Reserved list updated: ${r.path}. Live now, no deploy.`); setDraft(null); reload(); reloadBoot(); }
  }
  return (
    <section className="panel panel-pad">
      <div className="row">
        <div>
          <h2>Reserved decisions · {reg.ref}</h2>
          <p className="sub" style={{ margin: 0 }}>An agent can never complete these. Edit to save as a new version; its tests must pass or it will not load.</p>
        </div>
        <span className="spacer" />
        {draft === null ? <button className="btn" onClick={() => setDraft(reg.yaml.replace(/^version: (\d+)/m, (_: string, v: string) => `version: ${Number(v) + 1}`))}>Edit as HR</button>
          : <><button className="btn ghost" onClick={() => { setDraft(null); setResult(null); }}>Cancel</button><button className="btn primary" onClick={save}>Save new version</button></>}
      </div>
      {draft !== null ? (
        <div style={{ marginTop: 12 }}>
          <textarea className="code" value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Reserved registry YAML" />
          {result && !result.ok && <div className="refusal" style={{ marginTop: 8 }}>Refused: {result.reason || JSON.stringify(result.reload?.problems)}</div>}
        </div>
      ) : (
        <div className="grid g2" style={{ marginTop: 14 }}>
          <table className="t">
            <thead><tr><th>Action</th><th>Approver</th></tr></thead>
            <tbody>
              {reg.entries.map((e: any) => (
                <tr key={e.action}><td className="mono">{e.action}</td><td className="small">{e.approver_role.join(e.mode === "sequential" ? " → " : " or ")}</td></tr>
              ))}
            </tbody>
          </table>
          <div className="stack">
            <div><b>Route only, never decide</b>
              {reg.route_only.map((r: any) => <div key={r.action} className="small"><span className="mono">{r.action}</span> → {r.route_to_role.replace("_", " ")}</div>)}
            </div>
            <div><b>Agents may</b><div className="row small">{reg.may.map((v: string) => <span key={v} className="tag agent">{v}</span>)}</div></div>
            <div><b>Agents may never</b><div className="row small">{reg.may_never.map((v: string) => <span key={v} className="tag seal">{v}</span>)}</div>
              <div className="small muted">A workflow or skill granting one of these fails validation at load time.</div></div>
            <div><b>Registry tests</b><div className="small">{reg.tests.filter((t: any) => t.passed).length}/{reg.tests.length} passing</div></div>
          </div>
        </div>
      )}
    </section>
  );
}

function Provider() {
  const { boot, user, toast, reloadBoot } = useApp();
  async function swap(profile: string) {
    await api.post("/api/provider", { profile, user_id: user.id });
    toast(`Model profile switched to ${profile}. No skill changed.`);
    reloadBoot();
  }
  return (
    <section className="panel panel-pad row">
      <div>
        <h2>Switch profile</h2>
        <p className="sub" style={{ margin: 0 }}>Changing vendor is configuration. Swap the profile, then re-run the suite: the skills, prompts and rules do not change.</p>
      </div>
      <span className="spacer" />
      {boot.profiles.map((p: string) => (
        <button key={p} className={`btn ${boot.profile === p ? "primary" : ""}`} disabled={p === "openai_compatible" || (p === "groq" && !boot.groq_ready)} onClick={() => swap(p)} title={p === "openai_compatible" ? "Needs SETU_TIER*_ env vars" : ""}>{p}</button>
      ))}
    </section>
  );
}
