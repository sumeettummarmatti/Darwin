import { useState } from "react";
import { Link2, Search } from "lucide-react";
import { api } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";
import { Hearing } from "../components/Hearing";
import { plainStatus } from "../components/Pretty";

export default function Talent() {
  const { go, setUser, toast } = useApp();
  const [runs, reloadRuns] = usePoll<any[]>("/api/runs?workflow=sourcing&limit=5", 3000);
  const latest = (runs || [])[0];
  const [detail] = usePoll<any>(latest ? `/api/runs/${latest.id}` : null, 3000);
  const [pointers, reloadPointers] = usePoll<any[]>("/api/people?kind=sourced", 3000);
  const [probe, setProbe] = useState<Record<string, string>>({});
  const steps = Object.fromEntries((detail?.steps || []).map((s: any) => [s.id, s]));
  const out = (id: string) => steps[id]?.outputs || {};

  async function source() {
    setUser("USR-110");
    await api.post("/api/runs", { workflow: "sourcing", subject_id: null, user_id: "USR-110" });
    toast("Searching for candidates as Ananya.");
    reloadRuns();
  }
  async function assess(id: string) {
    const r = await api.post("/api/runs", { workflow: "sourcing_assess", subject_id: id, user_id: "USR-110" });
    const d = await api.get(`/api/runs/${r.run_id}`);
    const item = d.queue[0];
    setProbe((p) => ({ ...p, [id]: item ? item.packet.summary : "Not blocked. This is a bug." }));
  }
  async function reply(id: string, kind: string) {
    await api.post("/api/runs", { workflow: "sourcing_reply", subject_id: id, user_id: "USR-110", inputs: { reply: kind } });
    toast(kind === "objection" ? "They said stop. Link deleted, and they'll never be contacted again." : "They're interested. Their consent is saved.");
    reloadPointers();
  }

  // Real models do not always return the shapes the simulator does: read everything defensively.
  const list = (v: any) => (Array.isArray(v) ? v : []);
  const blocked = list(out("no_raid").blocked);
  const ranking = list(out("score").ranking);
  const flags = list(out("bias_challenge").flags);
  const discarded = list(out("extract_claims").discarded);
  const proposals = list(out("score")._proposals);
  const campaign = steps["campaign_approval"];

  return (
    <>
      <div className="page-head">
        <h1>Hiring</h1>
        <p>Find and rank candidates fairly. The AI can rank, but only a person can reject.</p>
      </div>

      <section className="panel panel-pad row" style={{ marginBottom: 16 }}>
        <div><b>Senior platform engineer</b><div className="small muted">Open role, hiring manager Ananya</div></div>
        <span className="spacer" />
        {latest && <button className="btn ghost" onClick={() => go(`runs/${latest.id}`)}>See all steps</button>}
        <button className="btn primary" onClick={source}><Search size={15} /> {latest ? "Search again" : "Find candidates"}</button>
      </section>

      {!latest && <div className="panel empty">Click Find candidates to start.</div>}

      {latest && (
        <div className="stack" style={{ gap: 16 }}>
          <div className="grid g2">
            <section className="panel panel-pad">
              <h2>Found online, never applied</h2>
              <p className="sub">We only keep a link. No profile, no score, no AI. The link is deleted after 30 days with no reply.</p>
              <div className="stack">
                {list(pointers).filter((p: any) => p?.attrs?.public_url).map((p: any) => {
                  const block = blocked.find((b: any) => b.public_url === p.attrs.public_url);
                  return (
                    <div key={p.id} style={{ borderBottom: "1px solid var(--line-2)", paddingBottom: 10 }}>
                      <div className="row">
                        <Link2 size={14} /><span className="mono" style={{ overflowWrap: "anywhere" }}>{p.attrs.public_url}</span>
                      </div>
                      <div className="row small" style={{ marginTop: 4 }}>
                        <span className={`tag ${p.processing_mode === "pointer_only" ? "seal" : "ok"}`}>{p.processing_mode === "pointer_only" ? "Link only" : "Agreed to be contacted"}</span>
                        {p.attrs.org_hint && <span className="tag">{p.attrs.org_hint}</span>}
                        {block && <span className="tag rule">Can't approach</span>}
                      </div>
                      {p.processing_mode === "pointer_only" && (
                        <div className="row" style={{ marginTop: 8 }}>
                          <button className="btn small" onClick={() => assess(p.id)}>Ask the AI about them</button>
                          <button className="btn small ghost" onClick={() => reply(p.id, "interest")}>They replied: interested</button>
                          <button className="btn small ghost" onClick={() => reply(p.id, "objection")}>They replied: stop</button>
                        </div>
                      )}
                      {probe[p.id] && <div className="refusal small" style={{ marginTop: 8 }}>Blocked: {probe[p.id]}</div>}
                    </div>
                  );
                })}
                {!(pointers || []).length && <div className="small muted">No one found yet.</div>}
              </div>
            </section>

            <section className="panel panel-pad stack">
              <div>
                <h2>Can't approach</h2>
                <p className="sub">TBO has promised these companies it won't hire their staff.</p>
                {blocked.map((b: any) => (
                  <div key={b.ref} className="refusal small" style={{ marginBottom: 8 }}>
                    <b>{b.employer}</b>: {b.reason}.<div className="muted">Agreement {b.clause}.{String(b.exception || "").match(/reserved to ([^)]+)/) ? ` Only ${String(b.exception).match(/reserved to ([^)]+)/)![1]} can make an exception.` : ""}</div>
                  </div>
                ))}
              </div>
              <div>
                <h2>Outreach messages</h2>
                <p className="sub">Messages go out only after Ananya approves. Each says who we are and how to say stop.</p>
                <div className="row">
                  <span className={`tag ${campaign?.status === "done" ? "ok" : "seal"}`}>{campaign?.status === "done" ? "Approved" : campaign?.status === "awaiting_human" ? "Waiting for Ananya" : plainStatus(campaign?.status) || "—"}</span>
                  {steps["send_notices"]?.outputs?.executed !== undefined && <span className="tag agent">{steps["send_notices"].outputs.executed} messages sent</span>}
                  {campaign?.status === "awaiting_human" && <button className="btn small seal" onClick={() => { setUser("USR-110"); go("inbox"); }}>Approve as Ananya</button>}
                </div>
              </div>
              {discarded.length > 0 && (
                <div>
                  <h2>Made-up facts, thrown away</h2>
                  <p className="sub">The AI claimed these, but they aren't actually in the CV, so they were ignored.</p>
                  {discarded.map((d: any, i: number) => <div key={i} className="objection small"><b>{String(d.candidate ?? "")}</b> · {String(d.criterion ?? "").replace(/_/g, " ")}: “{String(d.quote ?? "")}”</div>)}
                </div>
              )}
            </section>
          </div>

          <section className="panel">
            <div className="panel-pad" style={{ paddingBottom: 0 }}>
              <h2>Applicants, ranked</h2>
              <p className="sub">The score is plain maths over facts quoted from each CV. The AI never gives the score.</p>
            </div>
            <table className="t">
              <thead><tr><th>#</th><th>Name</th><th>Score</th><th>Must-haves</th><th>Proof from the CV</th></tr></thead>
              <tbody>
                {ranking.map((r: any) => {
                  const flag = flags.find((f: any) => f.candidate === r.candidate_id);
                  const proposal = !r.must_have_met && proposals.length;
                  return (
                    <tr key={r.candidate_id}>
                      <td><b>{r.position}</b></td>
                      <td><b>{r.display_name}</b></td>
                      <td style={{ whiteSpace: "nowrap" }}><b>{typeof r.score === "number" ? Math.round(r.score * 100) : "—"}</b><span className="small muted"> / 100</span></td>
                      <td>{r.must_have_met ? <span className="tag ok">Yes</span> : <span className="tag warn">No</span>}
                        {proposal ? <div className="small" style={{ marginTop: 6, color: "var(--seal)" }}>The AI suggested rejecting. Blocked: only a hiring manager can reject.</div> : null}</td>
                      <td className="small">
                        {list(r.breakdown).map((b: any, i: number) => (
                          <div key={i}><span className="tag rule">{String(b.criterion || "").replace(/_/g, " ")}</span> “{String(b.evidence ?? "")}”</div>
                        ))}
                        {flag && <div style={{ marginTop: 8 }}><Hearing c={{
                          gate: "D", class: "possible bias", severity: "medium",
                          claim: `The AI's note says “${flag.phrase}”, which can be a hidden stand-in for ${String(flag.proxy_for || "").replace(/_/g, " ")}. That isn't allowed in hiring.`,
                          evidence: [`“${String(r.rationale ?? "")}”`],
                          resolution: "The score doesn't use it: the scoring rules can't see banned criteria. The phrase is flagged so the reviewer ignores it.",
                          verdict_override: { label: "Flagged for the reviewer", tone: "rule" },
                        }} /></div>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        </div>
      )}
    </>
  );
}
