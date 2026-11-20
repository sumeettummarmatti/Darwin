import { useState } from "react";
import { api, fmtTime } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";
import { ProviderKey } from "../components/ProviderKey";
import { More, humanize, plainAction } from "../components/Pretty";

const role = (r: string) => humanize(r).toLowerCase().replace(/\bhr\b/g, "HR");

export default function Governance() {
  return (
    <>
      <div className="page-head">
        <h1>Safety controls</h1>
        <p>Test the limits, pause things in an emergency, and choose what only people can decide.</p>
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
  const refused = res ? res.results.filter((r: any) => r.outcome === "refused").length : 0;
  return (
    <section className="panel panel-pad">
      <div className="row">
        <div>
          <h2>Try to make the AI break the rules</h2>
          <p className="sub" style={{ margin: 0 }}>The AI attempts every action it's not allowed to do. Each attempt should be blocked.</p>
        </div>
        <span className="spacer" />
        <button className="btn seal" onClick={run} disabled={busy}>{busy ? "Running…" : "Run the test"}</button>
      </div>
      {res && (
        <div style={{ marginTop: 16 }}>
          <div className="row" style={{ gap: 20, alignItems: "center" }}>
            <div className={`seal-stamp stamp-in ${res.all_refused ? "" : "ok"}`} style={{ width: 110, height: 110 }}>
              <b>{refused}/{res.results.length}</b>
              <small>BLOCKED</small>
            </div>
            <p style={{ maxWidth: 520 }}>
              {res.all_refused ? "Every attempt was blocked by the system itself, not just hidden on screen. Each one is in the history log." : "Some attempts got through. This is a bug."}
            </p>
          </div>
          <More label="See every attempt">
            <table className="t">
              <thead><tr><th>What the AI tried</th><th>Result</th><th>Why</th></tr></thead>
              <tbody>
                {res.results.map((r: any) => (
                  <tr key={r.action}><td>{plainAction(r.action)}</td><td><span className={`tag ${r.outcome === "refused" ? "seal" : "warn"}`}>{r.outcome === "refused" ? "Blocked" : "Allowed"}</span></td>
                    <td className="small">{r.reason}</td></tr>
                ))}
              </tbody>
            </table>
          </More>
        </div>
      )}
    </section>
  );
}

const SCOPE_LABEL: Record<string, string> = { global: "Everything", workflow: "One process", skill: "One AI helper", connector: "One connected system" };

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
  const name = (s: string, t: string) => (s === "global" ? "Everything" : humanize(t));
  async function set(active: boolean, s = scope, t = target) {
    await api.post("/api/killswitch", { scope: s, target: s === "global" ? "*" : t, active, reason, user_id: user.id });
    toast(active ? `Paused: ${name(s, t)}. Anything in progress waits in Approvals.` : `Resumed: ${name(s, t)}`);
    reload();
  }
  const active = (data?.switches || []).filter((s: any) => s.active);
  return (
    <section className="panel panel-pad">
      <h2>Emergency stop</h2>
      <p className="sub">Pause something straight away. Work in progress waits for a person.</p>
      <div className="row">
        <select value={scope} onChange={(e) => { setScope(e.target.value); setTarget(targets[e.target.value][0]); }} aria-label="What to pause">
          {Object.keys(targets).map((s) => <option key={s} value={s}>{SCOPE_LABEL[s]}</option>)}
        </select>
        {scope !== "global" && (
          <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Which one">
            {targets[scope].map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
          </select>
        )}
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why? (optional)" style={{ flex: 1, minWidth: 140 }} />
        <button className="btn seal" onClick={() => set(true)}>Pause</button>
      </div>
      <div className="stack" style={{ marginTop: 14 }}>
        {active.map((s: any) => (
          <div key={s.scope + s.target} className="refusal row">
            <div><b>Paused: {name(s.scope, s.target)}</b><div className="small">{s.reason || "No reason given"} · {fmtTime(s.at)}</div></div>
            <span className="spacer" />
            <button className="btn small" onClick={() => set(false, s.scope, s.target)}>Resume</button>
          </div>
        ))}
        {!active.length && <div className="small muted">Nothing is paused.</div>}
      </div>
    </section>
  );
}

const SYSTEM_LABEL: Record<string, string> = { assets: "Laptops", tickets: "IT tickets", access: "Access cards", directory: "Email accounts", payroll: "Payroll", mail: "Mail" };

function Chaos() {
  const { toast } = useApp();
  const [data, reload] = usePoll<any>("/api/mocks/chaos", 2500);
  const [ks] = usePoll<any>("/api/killswitch", 2500);
  const [system, setSystem] = useState("assets");
  const [mode, setMode] = useState("error_500");
  async function apply(m = mode) {
    await api.post("/api/mocks/chaos", { system, mode: m, count: 3 });
    toast(m === "clear" ? `${SYSTEM_LABEL[system]} is working again` : `${SYSTEM_LABEL[system]} is now broken`);
    reload();
  }
  const broken = data?.chaos || [];
  const tripped = (ks?.breakers || []).filter((b: any) => b.state !== "closed");
  return (
    <section className="panel panel-pad">
      <h2>Break a system (for testing)</h2>
      <p className="sub">See HR Autopilot survive a crash without doing anything twice.</p>
      <div className="row">
        <select value={system} onChange={(e) => setSystem(e.target.value)} aria-label="System">
          {Object.keys(SYSTEM_LABEL).map((s) => <option key={s} value={s}>{SYSTEM_LABEL[s]}</option>)}
        </select>
        <select value={mode} onChange={(e) => setMode(e.target.value)} aria-label="How it breaks">
          <option value="error_500">Fails 3 times</option>
          <option value="timeout_after_commit">Saves, then times out</option>
          <option value="ack_no_commit">Says OK, saves nothing</option>
          <option value="down">Down until fixed</option>
        </select>
        <button className="btn seal" onClick={() => apply()}>Break it</button>
        <button className="btn" onClick={() => apply("clear")}>Fix it</button>
      </div>
      <div className="small" style={{ marginTop: 12 }}>
        {broken.map((c: any) => <span key={c.system} className="tag seal" style={{ marginRight: 6 }}>{SYSTEM_LABEL[c.system] || c.system} broken</span>)}
        {tripped.map((b: any) => <span key={b.name} className="tag warn" style={{ marginRight: 6 }}>HR Autopilot stopped calling {SYSTEM_LABEL[String(b.name).split(".").pop() as string] || humanize(String(b.name).split(".").pop() || "")} for now</span>)}
        {!broken.length && !tripped.length && <span className="muted">All systems working.</span>}
      </div>
      {(data?.calls || []).length > 0 && (
        <More label="Recent calls to these systems">
          <table className="t">
            <tbody>
              {(data?.calls || []).slice(0, 7).map((c: any) => (
                <tr key={c.seq}><td className="small">{SYSTEM_LABEL[c.system] || c.system}: {humanize(c.op).toLowerCase()}</td><td><span className={`tag ${c.outcome === "ok" ? "ok" : "seal"}`}>{c.outcome === "ok" ? "OK" : humanize(c.outcome)}</span></td><td className="small muted">{fmtTime(c.at)}</td></tr>
              ))}
            </tbody>
          </table>
        </More>
      )}
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
    if (r.ok) { toast("Saved. The new list is live."); setDraft(null); reload(); reloadBoot(); }
  }
  return (
    <section className="panel panel-pad">
      <div className="row">
        <div>
          <h2>Only a person can do these</h2>
          <p className="sub" style={{ margin: 0 }}>The AI can never do these, whatever it's told. HR can edit the list.</p>
        </div>
        <span className="spacer" />
        {draft === null ? <button className="btn" onClick={() => setDraft(reg.yaml.replace(/^version: (\d+)/m, (_: string, v: string) => `version: ${Number(v) + 1}`))}>Edit the list</button>
          : <><button className="btn ghost" onClick={() => { setDraft(null); setResult(null); }}>Cancel</button><button className="btn primary" onClick={save}>Save</button></>}
      </div>
      {draft !== null ? (
        <div style={{ marginTop: 12 }}>
          <textarea className="code" value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Approval list" />
          {result && !result.ok && <div className="refusal" style={{ marginTop: 8 }}>Not saved: {result.reason || (result.reload?.problems || []).map((x: any) => x.message || String(x)).join("; ")}</div>}
        </div>
      ) : (
        <>
          <table className="t" style={{ marginTop: 12 }}>
            <thead><tr><th>Action</th><th>Who decides</th></tr></thead>
            <tbody>
              {reg.entries.map((e: any) => (
                <tr key={e.action}><td>{plainAction(e.action)}</td><td className="small">{e.approver_role.map(role).join(e.mode === "sequential" ? ", then " : " or ")}</td></tr>
              ))}
            </tbody>
          </table>
          <More label="More: things passed on unread, and what the AI may or may not do">
            <div className="stack">
              <div><b>Passed straight to a person, never judged by the AI</b>
                {reg.route_only.map((r: any) => <div key={r.action} className="small">{plainAction(r.action)}: goes to {role(r.route_to_role)}</div>)}
              </div>
              <div><b>The AI may</b><div className="row small">{reg.may.map((v: string) => <span key={v} className="tag agent">{humanize(v)}</span>)}</div></div>
              <div><b>The AI may never</b><div className="row small">{reg.may_never.map((v: string) => <span key={v} className="tag seal">{humanize(v)}</span>)}</div></div>
              <div className="small muted">The list's own checks: {reg.tests.filter((t: any) => t.passed).length} of {reg.tests.length} passing.</div>
            </div>
          </More>
        </>
      )}
    </section>
  );
}

const PROFILE_LABEL: Record<string, string> = { sim: "Simulator", sim_alt: "Simulator (second vendor)", groq: "Groq" };

function Provider() {
  const { boot, user, toast, reloadBoot } = useApp();
  async function swap(profile: string) {
    await api.post("/api/provider", { profile, user_id: user.id });
    toast(`Now using: ${PROFILE_LABEL[profile] || profile}`);
    reloadBoot();
  }
  return (
    <section className="panel panel-pad row">
      <div>
        <h2>Switch AI</h2>
        <p className="sub" style={{ margin: 0 }}>Changing the AI provider changes nothing else.</p>
      </div>
      <span className="spacer" />
      {boot.profiles.filter((p: string) => p !== "openai_compatible").map((p: string) => (
        <button key={p} className={`btn ${boot.profile === p ? "primary" : ""}`} disabled={p === "groq" && !boot.groq_ready} onClick={() => swap(p)} title={p === "groq" && !boot.groq_ready ? "Add a Groq key first" : ""}>{PROFILE_LABEL[p] || p}</button>
      ))}
    </section>
  );
}
