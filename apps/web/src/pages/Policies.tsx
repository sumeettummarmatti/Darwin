import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";
import { Hearing } from "../components/Hearing";
import { sentence } from "../components/Pretty";

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
        <h1>Policy packs</h1>
        <p>Rules live here, versioned and tested, never in a prompt or an if-statement. A pack with no tests does not load, and a change has to survive Prativaad's adversarial review before it can go live.</p>
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
                    <td><b>{n.replace(/_/g, " ")}</b><div className="small muted mono">{a.ref} · {a.path}</div></td>
                    <td className="small" style={{ textAlign: "right" }}><span className={`tag ${a.tests_passed === a.tests.length ? "ok" : "seal"}`}>{a.tests_passed}/{a.tests.length} tests</span></td>
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
    toast("Prativaad's counter-example added to tests: — it can never regress silently.");
  }
  async function activate() {
    const r = await api.post(`/api/policies/${pack.name}/activate`, { yaml: draft });
    toast(r.ok ? `Activated ${r.path}. Hot-reloaded, no restart.` : `Refused: ${r.reason}`);
    if (r.ok) setDraft(null);
  }

  return (
    <div className="stack">
      <section className="panel panel-pad">
        <div className="row">
          <h2 style={{ margin: 0 }}>{pack.ref}</h2>
          <span className="tag">effective {pack.effective_from}</span>
          {pack.owner && <span className="tag">owner {pack.owner}</span>}
          <span className="tag mono">{pack.hash}</span>
          <span className="spacer" />
          {versions.length > 1 && <span className="small muted">versions: {versions.map((v) => v.version).join(", ")}</span>}
          {draft === null && <button className="btn primary" onClick={loadPrepared}>Draft a change</button>}
        </div>
        <p className="small muted" style={{ marginBottom: 0 }}>{pack.rules} rules · {pack.derive} derived values · {pack.guards} guards{pack.has_properties ? " · properties checked by gate B" : ""}</p>
      </section>

      {draft !== null ? (
        <section className="panel panel-pad">
          <div className="row" style={{ marginBottom: 10 }}>
            <h2 style={{ margin: 0 }}>Draft</h2><span className="spacer" />
            <button className="btn ghost" onClick={() => { setDraft(null); setReview(null); }}>Discard</button>
            <button className="btn" onClick={runReview} disabled={busy}>{busy ? "Reviewing…" : "Ask Prativaad to attack it"}</button>
            <button className="btn primary" onClick={activate} disabled={!review?.ok}>Activate</button>
          </div>
          {review && <div style={{ marginBottom: 14 }}><Review review={review} onAdd={addProposedTests} /></div>}
          <textarea className="code" value={draft} onChange={(e) => { setDraft(e.target.value); setReview(null); }} aria-label="Draft policy YAML" />
        </section>
      ) : (
        <div className="grid g2">
          <section className="panel panel-pad">
            <h2>Tests shipped in the pack</h2>
            <p className="sub">Run on load and in CI. A failing test blocks the pack.</p>
            {pack.tests.map((t: any) => (
              <div key={t.name} className="row small" style={{ padding: "4px 0" }}>
                <span className={`tag ${t.passed ? "ok" : "seal"}`}>{t.passed ? "pass" : "fail"}</span><span>{t.name}</span>
              </div>
            ))}
            {pack.clauses.length > 0 && <>
              <h2 style={{ marginTop: 18 }}>Clauses the helpdesk cites</h2>
              {pack.clauses.map((c: any) => <div key={c.id} className="small" style={{ padding: "4px 0" }}><span className="tag rule">{c.id}</span> {c.text}</div>)}
            </>}
          </section>
          <section className="panel"><pre className="code" style={{ margin: 0, borderRadius: 10, maxHeight: 640 }}>{src?.yaml || "…"}</pre></section>
        </div>
      )}
    </div>
  );
}

function Review({ review, onAdd }: { review: any; onAdd: () => void }) {
  if (review.load_error) return <div className="refusal" style={{ marginTop: 12 }}>Will not load: {review.load_error}</div>;
  return (
    <div className="stack">
      <div className={review.ok ? "notice" : "refusal"}>
        <b>Prativaad gate B: {review.ok ? "no findings" : `${review.finding_count} blocking finding(s)`}</b> — generated {review.cases} adversarial cases from the pack's input domains;
        {" "}{review.changed_count} case(s) resolve differently from the active version.
      </div>
      {review.failing_tests?.map((t: any) => <div key={t.name} className="refusal small">Pack test fails: {t.name} — {t.reason}</div>)}
      {review.findings.length > 0 && (
        <div className="hearings">
          {review.findings.slice(0, 2).map((f: any, i: number) => (
            <Hearing key={i} c={{
              gate: "B", class: `property ${f.property} broken`, severity: "high", layer: "rules",
              claim: `“${f.claim}” — the draft lets this case through.`,
              evidence: [`case: ${sentence(f.given)}`, `draft returns: ${sentence(f.got)}`, `rules ${f.rule_ids.join(", ")}`],
              resolution: "None from the draft. Prativaad proposes a regression test so this case can never pass silently again.",
              verdict_override: { label: "Blocks activation", tone: "seal" },
            }} />
          ))}
          {review.finding_count > 2 && <div className="small muted">…and {review.finding_count - 2} more cases breaking the same property.</div>}
        </div>
      )}
      {review.proposed_tests?.length > 0 && (
        <div className="row"><span className="small">Prativaad proposes {review.proposed_tests.length} regression test(s) for the pack.</span>
          <button className="btn small" onClick={onAdd}>Add them to tests:</button></div>
      )}
      {review.changed?.length > 0 && (
        <details>
          <summary className="small">What changes against the active version ({review.changed_count})</summary>
          <table className="t small">
            <thead><tr><th>Case</th><th>Active version</th><th>Draft</th></tr></thead>
            <tbody>{review.changed.slice(0, 12).map((c: any, i: number) => (
              <tr key={i}><td>{sentence(c.given)}</td><td>{typeof c.before === "string" ? c.before : sentence(c.before)}</td><td>{typeof c.after === "string" ? c.after : sentence(c.after)}</td></tr>
            ))}</tbody>
          </table>
        </details>
      )}
    </div>
  );
}
