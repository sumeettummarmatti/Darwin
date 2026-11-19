import { useState } from "react";
import { Link2, Search } from "lucide-react";
import { api } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";
import { Hearing } from "../components/Hearing";

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
    toast("Sourcing run started for REQ-PLAT-07 on behalf of Ananya Rao.");
    reloadRuns();
  }
  async function assess(id: string) {
    const r = await api.post("/api/runs", { workflow: "sourcing_assess", subject_id: id, user_id: "USR-110" });
    const d = await api.get(`/api/runs/${r.run_id}`);
    const item = d.queue[0];
    setProbe((p) => ({ ...p, [id]: item ? item.packet.summary : "not refused (this would be a bug)" }));
  }
  async function reply(id: string, kind: string) {
    await api.post("/api/runs", { workflow: "sourcing_reply", subject_id: id, user_id: "USR-110", inputs: { reply: kind } });
    toast(kind === "objection" ? "Objection: added to the permanent suppression list and the pointer deleted." : "Interest: consent recorded, record upgraded.");
    reloadPointers();
  }

  const blocked = out("no_raid").blocked || [];
  const ranking = out("score").ranking || [];
  const flags = out("bias_challenge").flags || [];
  const discarded = out("extract_claims").discarded || [];
  const proposals = out("score")._proposals || [];
  const campaign = steps["campaign_approval"];

  return (
    <>
      <div className="page-head">
        <h1>Talent, on people who chose to be here</h1>
        <p>Anyone found in a public source who never gave TBO anything is a pointer: a link and the date, nothing derived, no model call. Applicants are ranked by rule over evidence quoted from their own résumé. Only a person can reject.</p>
      </div>

      <section className="panel panel-pad row" style={{ marginBottom: 16 }}>
        <div><b>REQ-PLAT-07 · Senior platform engineer</b><div className="small muted">ICP pack icp@v2 · lawful-basis pack sourcing_basis.in@v1 · no-raid pack no_raid@v1 (owned by Legal)</div></div>
        <span className="spacer" />
        {latest && <button className="btn ghost" onClick={() => go(`runs/${latest.id}`)}>Open the run</button>}
        <button className="btn primary" onClick={source}><Search size={15} /> {latest ? "Source again" : "Source candidates"}</button>
      </section>

      {!latest && <div className="panel empty">No sourcing run yet. Source candidates to see the gate at work.</div>}

      {latest && (
        <div className="stack" style={{ gap: 16 }}>
          <div className="grid g2">
            <section className="panel panel-pad">
              <h2>Pointers · no lawful basis</h2>
              <p className="sub">Stored: public link, source, date, role hypothesis, the organisation on the public record, its public contact. Nothing else, ever. They expire in 30 days without a reply.</p>
              <div className="stack">
                {(pointers || []).map((p) => {
                  const block = blocked.find((b: any) => b.public_url === p.attrs.public_url);
                  return (
                    <div key={p.id} style={{ borderBottom: "1px solid var(--line-2)", paddingBottom: 10 }}>
                      <div className="row">
                        <Link2 size={14} /><span className="mono" style={{ overflowWrap: "anywhere" }}>{p.attrs.public_url}</span>
                      </div>
                      <div className="row small" style={{ marginTop: 4 }}>
                        <span className={`tag ${p.processing_mode === "pointer_only" ? "seal" : "ok"}`}>{p.processing_mode === "pointer_only" ? "pointer only" : `consented · ${p.lawful_basis}`}</span>
                        <span className="tag">{p.attrs.source_id}</span>
                        {p.attrs.org_hint && <span className="tag">{p.attrs.org_hint}</span>}
                        {block && <span className="tag rule">blocked · {block.clause}</span>}
                      </div>
                      {p.processing_mode === "pointer_only" && (
                        <div className="row" style={{ marginTop: 8 }}>
                          <button className="btn small" onClick={() => assess(p.id)}>Ask the model about them</button>
                          <button className="btn small ghost" onClick={() => reply(p.id, "interest")}>Reply: interested</button>
                          <button className="btn small ghost" onClick={() => reply(p.id, "objection")}>Reply: stop</button>
                        </div>
                      )}
                      {probe[p.id] && <div className="refusal small" style={{ marginTop: 8 }}>Refused by the kernel: {probe[p.id]}</div>}
                    </div>
                  );
                })}
                {!(pointers || []).length && <div className="small muted">No pointers stored.</div>}
              </div>
            </section>

            <section className="panel panel-pad stack">
              <div>
                <h2>Blocked by TBO's own obligations</h2>
                <p className="sub">Non-competes are void in India; non-solicit clauses binding TBO are not. A block always names the clause.</p>
                {blocked.map((b: any) => (
                  <div key={b.ref} className="refusal small" style={{ marginBottom: 8 }}>
                    <b>{b.ref}</b> · {b.employer} — {b.reason}. Clause <span className="mono">{b.clause}</span>. Exception: {b.exception}.
                  </div>
                ))}
              </div>
              <div>
                <h2>Outreach campaign</h2>
                <p className="sub">Agents send only inside a campaign a named person approved: the list, the notice-first template and the lawful-basis attestation.</p>
                <div className="row">
                  <span className={`tag ${campaign?.status === "done" ? "ok" : "seal"}`}>{campaign?.status === "done" ? "approved" : (campaign?.status || "—").replace("_", " ")}</span>
                  {steps["send_notices"]?.outputs?.executed !== undefined && <span className="tag agent">{steps["send_notices"].outputs.executed} notices sent to the mail mock</span>}
                  {campaign?.status === "awaiting_human" && <button className="btn small seal" onClick={() => { setUser("USR-110"); go("inbox"); }}>Review as Ananya</button>}
                </div>
              </div>
              {discarded.length > 0 && (
                <div>
                  <h2>Claims thrown away</h2>
                  <p className="sub">The model returned these without a verbatim quote in the source. They never reached the scorer.</p>
                  {discarded.map((d: any, i: number) => <div key={i} className="objection small"><b>{d.candidate}</b> · {d.criterion}: “{d.quote}” — {d.reason}</div>)}
                </div>
              )}
            </section>
          </div>

          <section className="panel">
            <div className="panel-pad" style={{ paddingBottom: 0 }}>
              <h2>Ranking · deterministic, explained from stored evidence</h2>
              <p className="sub">Score = arithmetic in icp@v2 over span-backed claims. “Why is she fourth?” is answered from these rows, not by asking a model.</p>
            </div>
            <table className="t">
              <thead><tr><th>#</th><th>Applicant</th><th>Score</th><th>Must-haves</th><th>Evidence (quoted from the résumé)</th></tr></thead>
              <tbody>
                {ranking.map((r: any) => {
                  const flag = flags.find((f: any) => f.candidate === r.candidate_id);
                  const proposal = !r.must_have_met && proposals.length;
                  return (
                    <tr key={r.candidate_id}>
                      <td><b>{r.position}</b></td>
                      <td><b>{r.display_name}</b><div className="small muted mono">{r.candidate_id}</div></td>
                      <td><b>{r.score.toFixed(3)}</b></td>
                      <td>{r.must_have_met ? <span className="tag ok">met</span> : <span className="tag warn">not met</span>}
                        {proposal ? <div className="small" style={{ marginTop: 6, color: "var(--seal)" }}>Agent proposed rejection → 403 RESERVED. A hiring manager decides.</div> : null}</td>
                      <td className="small">
                        {r.breakdown.map((b: any, i: number) => (
                          <div key={i}><span className="tag rule">{b.criterion}</span> “{b.evidence}” <span className="muted mono">[{b.span.join("–")}]</span></div>
                        ))}
                        {flag && <div style={{ marginTop: 8 }}><Hearing c={{
                          gate: "D", class: "proxy bias", severity: "medium", layer: "rules",
                          claim: `The rationale says “${flag.phrase}”, which can stand in for ${flag.proxy_for.replace(/_/g, " ")} — a prohibited criterion.`,
                          evidence: [`rationale: “${r.rationale}”`, `characters ${flag.span.join("–")}`],
                          resolution: "The score does not use it (icp@v2 cannot read prohibited criteria). The phrase is flagged so the reviewer discounts it.",
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
