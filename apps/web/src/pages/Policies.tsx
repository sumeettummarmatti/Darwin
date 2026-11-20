import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";
import { Hearing } from "../components/Hearing";
import { More, humanize, sentence } from "../components/Pretty";

export default function Policies({ arg }: { arg: string | null }) {
  const { go } = useApp();
  const [packs] = usePoll<any[]>("/api/policies", 0);
  const names = Array.from(new Set((packs || []).map((p) => p.name)));
  const current = arg || "notice_period";
  const versions = (packs || []).filter((p) => p.name === current);
  const active = versions.find((v) => v.active) || versions.at(-1);

  return (
    <>
      <div className="page-head">
        <h1>Rules</h1>
        <p>HR rules like notice periods and leave. A change only goes live after the checker tries to break it.</p>
      </div>
      <div className="split">
        <section className="panel">
          <table className="t">
            <tbody>
              {names.map((n) => {
                const vs = (packs || []).filter((p) => p.name === n);
                const a = vs.find((v) => v.active) || vs.at(-1);
                return (
                  <tr key={n} className={`click ${n === current ? "sel" : ""}`} onClick={() => go(`policies/${n}`)}>
                    <td><b>{humanize(n)}</b><div className="small muted">version {a.version}</div></td>
                    <td className="small" style={{ textAlign: "right" }}><span className={`tag ${a.tests_passed === a.tests.length ? "ok" : "seal"}`}>{a.tests_passed === a.tests.length ? "Tests pass" : `${a.tests.length - a.tests_passed} failing`}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
        {active ? <PackDetail key={active.ref} pack={active} versions={versions} /> : <div className="panel empty">Loading…</div>}
      </div>
    </>
  );
}

function PackDetail({ pack, versions }: { pack: any; versions: any[] }) {
  const { toast } = useApp();
  const [src, setSrc] = useState<any>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const [review, setReview] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get(`/api/policies/${pack.name}/source?version=${pack.version}`).then(setSrc); }, [pack.ref]);

  async function loadPrepared() {
    try {
      const d = await api.get(`/api/policies/${pack.name}/draft`);
      setDraft(d.yaml); setReview(null);
    } catch { setDraft(src.yaml.replace(/^version: (\d+)/m, (_: string, v: string) => `version: ${Number(v) + 1}`)); }
  }
  async function runReview() {
    setBusy(true);
    setReview(await api.post(`/api/policies/${pack.name}/review`, { yaml: draft }));
    setBusy(false);
  }
  function addProposedTests() {
    if (!review?.proposed_tests?.length || draft === null) return;
    const lines = review.proposed_tests.map((t: any) =>
      `  - name: "${t.name.replace(/"/g, "'")}"\n    given: ${JSON.stringify(t.given)}\n    expect_error: "${t.expect_error}"`).join("\n");
    setDraft(draft.replace(/\ntests:\n/, `\ntests:\n${lines}\n`));
    toast("Test added. This mistake can't come back unnoticed.");
  }
  async function activate() {
    const r = await api.post(`/api/policies/${pack.name}/activate`, { yaml: draft });
    toast(r.ok ? "The new rule is live." : `Not saved: ${r.reason}`);
    if (r.ok) setDraft(null);
  }

  return (
    <div className="stack">
      <section className="panel panel-pad">
        <div className="row">
          <h2 style={{ margin: 0 }}>{humanize(pack.name)}</h2>
          <span className="small muted">version {pack.version} · in effect from {pack.effective_from}{pack.owner ? ` · owned by ${humanize(pack.owner).toLowerCase().replace(/\bhr\b/g, "HR")}` : ""}</span>
          <span className="spacer" />
          {draft === null && <button className="btn primary" onClick={loadPrepared}>Suggest a change</button>}
        </div>
      </section>

      {draft !== null ? (
        <section className="panel panel-pad">
          <div className="row" style={{ marginBottom: 10 }}>
            <h2 style={{ margin: 0 }}>Your change</h2><span className="spacer" />
            <button className="btn ghost" onClick={() => { setDraft(null); setReview(null); }}>Cancel</button>
            <button className="btn" onClick={runReview} disabled={busy}>{busy ? "Checking…" : "Check this change"}</button>
            <button className="btn primary" onClick={activate} disabled={!review?.ok} title={review?.ok ? "" : "Check the change first"}>Make it live</button>
          </div>
          {review && <div style={{ marginBottom: 14 }}><Review review={review} onAdd={addProposedTests} /></div>}
          <textarea className="code" value={draft} onChange={(e) => { setDraft(e.target.value); setReview(null); }} aria-label="Rule file" />
        </section>
      ) : (
        <div className="grid g2">
          <section className="panel panel-pad">
            <h2>Tests</h2>
            <p className="sub">If any test fails, the rule isn't used.</p>
            {pack.tests.map((t: any) => (
              <div key={t.name} className="row small" style={{ padding: "4px 0" }}>
                <span className={`tag ${t.passed ? "ok" : "seal"}`}>{t.passed ? "Pass" : "Fail"}</span><span>{t.name}</span>
              </div>
            ))}
            {pack.clauses.length > 0 && <>
              <h2 style={{ marginTop: 18 }}>What the chat quotes</h2>
              {pack.clauses.map((c: any) => <div key={c.id} className="small" style={{ padding: "4px 0" }}><span className="tag rule">{c.id}</span> {c.text}</div>)}
            </>}
          </section>
          <section className="panel panel-pad">
            <h2>The rule file</h2>
            <p className="sub">This is what SETU follows. No rule is hidden in code or in the AI's instructions.</p>
            <More label="Show the file">
              <pre className="code" style={{ margin: 0, borderRadius: 10, maxHeight: 560 }}>{src?.yaml || "…"}</pre>
            </More>
          </section>
        </div>
      )}
    </div>
  );
}

const plainClaim = (c: string) => String(c || "").replace(/statutory floor/g, "the legal minimum");

function Review({ review, onAdd }: { review: any; onAdd: () => void }) {
  if (review.load_error) return <div className="refusal" style={{ marginTop: 12 }}>This file has a mistake: {review.load_error}</div>;
  return (
    <div className="stack">
      <div className={review.ok ? "notice" : "refusal"}>
        <b>{review.ok ? "No problems found." : `Blocked: ${review.finding_count} case${review.finding_count === 1 ? "" : "s"} break the rules.`}</b>
        {" "}The checker tried {review.cases} test cases. {review.changed_count} would get a different answer than today.
      </div>
      {review.failing_tests?.map((t: any) => <div key={t.name} className="refusal small">Test fails: {t.name}. {t.reason}</div>)}
      {review.findings.length > 0 && (
        <div className="hearings">
          {review.findings.slice(0, 2).map((f: any, i: number) => (
            <Hearing key={i} c={{
              gate: "B", class: `Ends up ${plainClaim(f.claim)}`, severity: "high",
              claim: `With your change, this case ends up ${plainClaim(f.claim)}.`,
              evidence: [`Case: ${sentence(f.given)}`, `Your change gives: ${sentence(f.got)}`],
              resolution: "None. The checker wrote a test so this mistake can't slip through again.",
              verdict_override: { label: "Can't go live", tone: "seal" },
            }} />
          ))}
          {review.finding_count > 2 && <div className="small muted">And {review.finding_count - 2} more cases like this.</div>}
        </div>
      )}
      {review.proposed_tests?.length > 0 && (
        <div className="row"><span className="small">The checker wrote {review.proposed_tests.length === 1 ? "a test" : `${review.proposed_tests.length} tests`} that catch this.</span>
          <button className="btn small" onClick={onAdd}>Add to the tests</button></div>
      )}
      {review.changed?.length > 0 && (
        <details>
          <summary className="small">What would change ({review.changed_count})</summary>
          <table className="t small">
            <thead><tr><th>Case</th><th>Today</th><th>With your change</th></tr></thead>
            <tbody>{review.changed.slice(0, 12).map((c: any, i: number) => (
              <tr key={i}><td>{sentence(c.given)}</td><td>{typeof c.before === "string" ? c.before : sentence(c.before)}</td><td>{typeof c.after === "string" ? c.after : sentence(c.after)}</td></tr>
            ))}</tbody>
          </table>
        </details>
      )}
    </div>
  );
}
