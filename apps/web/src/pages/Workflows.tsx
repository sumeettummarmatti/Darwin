import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";
import { humanize, stepTitle } from "../components/Pretty";

type Block = { id: string; title: string; kind: string; needs: string[]; approver_action?: string; system?: string; scheduled?: boolean };
type Wf = { name: string; version: number; ref: string; description: string; path: string; steps: Block[] };

const KIND: Record<string, { label: string; cls: string }> = {
  rules: { label: "Rules", cls: "b-rules" },
  ai: { label: "AI", cls: "b-ai" },
  system: { label: "Another system", cls: "b-system" },
  person: { label: "A person approves", cls: "b-person" },
  route: { label: "Passed on unread", cls: "b-route" },
};

// A ready-made block to drop in, so adding a step is a paste, not a programming job.
function blockTemplate(wf: Wf) {
  const exit = wf.name === "exit";
  return `  - id: ${exit ? "collect_materials" : "new_ticket"}
    title: ${exit ? "Collect issued materials" : "Open a ticket"}
    connector: it.ticketing
    action: open_ticket
    needs: [${exit ? "accept_resignation" : ""}]
    args: { summary: "${exit ? "Collect ID card, headset and books from {{subject.display_name}}" : "Follow-up for {{subject.display_name}}"}" }
    idempotency_key: "${wf.name}:{{subject.id}}:${exit ? "materials" : "ticket"}:v1"
    compensation: close_ticket
`;
}

export function Blocks({ steps }: { steps: Block[] }) {
  return (
    <div className="blocks">
      {steps.map((s, i) => (
        <div key={s.id} className={`block ${KIND[s.kind]?.cls || ""}`}>
          <span className="block-n">{i + 1}</span>
          <b>{stepTitle(s.title)}</b>
          <small>{KIND[s.kind]?.label || humanize(s.kind)}{s.scheduled ? " · on a date" : ""}</small>
        </div>
      ))}
    </div>
  );
}

export default function Workflows({ arg }: { arg: string | null }) {
  const { go, toast, reloadBoot } = useApp();
  const [list, reload] = usePoll<Wf[]>("/api/workflows", 0);
  const current = (list || []).find((w) => w.name === (arg || "exit")) || (list || [])[0];
  const [draft, setDraft] = useState<string | null>(null);
  const [check, setCheck] = useState<any>(null);
  useEffect(() => { setDraft(null); setCheck(null); }, [current?.name]);

  async function edit() {
    const src = await api.get(`/api/workflows/${current!.name}/source`);
    setDraft(src.yaml.replace(/^version: (\d+)/m, (_: string, v: string) => `version: ${Number(v) + 1}`));
    setCheck(null);
  }
  function addBlock() {
    if (draft === null) return;
    // Exit: drop it in before "mark exited", so the block sits where it belongs; otherwise first.
    const tpl = blockTemplate(current!);
    setDraft(draft.includes("\n  - id: mark_exited") ? draft.replace("\n  - id: mark_exited", `\n${tpl}\n  - id: mark_exited`)
      : draft.replace(/\nsteps:\n/, `\nsteps:\n${tpl}\n`));
    setCheck(null);
  }
  async function runCheck() { setCheck(await api.post(`/api/workflows/${current!.name}/check`, { yaml: draft })); }
  async function makeLive() {
    const r = await api.post(`/api/workflows/${current!.name}/activate`, { yaml: draft });
    if (r.ok) { toast(`${humanize(current!.name)} version ${r.ref.split("@v")[1]} is live. New processes use it; running ones keep theirs.`); setDraft(null); setCheck(null); reload(); reloadBoot(); }
    else setCheck({ ok: false, errors: [r.reason] });
  }

  return (
    <>
      <div className="page-head">
        <h1>Workflows</h1>
        <p>Every process is a list of blocks in a file. Add, remove or reorder blocks without touching the engine.</p>
      </div>
      <div className="split">
        <section className="panel">
          <table className="t"><tbody>
            {(list || []).map((w) => (
              <tr key={w.name} className={`click ${current?.name === w.name ? "sel" : ""}`} onClick={() => go(`workflows/${w.name}`)}>
                <td><b>{humanize(w.name)}</b><div className="small muted">version {w.version} · {w.steps.length} blocks</div></td>
              </tr>
            ))}
          </tbody></table>
        </section>

        {current && (
          <div className="stack">
            <section className="panel panel-pad">
              <div className="row">
                <h2 style={{ margin: 0 }}>{humanize(current.name)}</h2>
                <span className="small muted">version {current.version}</span>
                <span className="spacer" />
                {draft === null && <button className="btn primary" onClick={edit}>Edit this workflow</button>}
              </div>
              <p className="small muted" style={{ margin: "6px 0 10px" }}>{current.description}</p>
              <Blocks steps={current.steps} />
              <div className="legend" style={{ marginTop: 10 }}>
                {Object.values(KIND).map((k) => <span key={k.label}><i className={`dot-${k.cls}`} /> {k.label}</span>)}
              </div>
            </section>

            {draft !== null && (
              <section className="panel panel-pad">
                <div className="row" style={{ marginBottom: 10 }}>
                  <h2 style={{ margin: 0 }}>Your change</h2>
                  <span className="spacer" />
                  <button className="btn" onClick={addBlock}>Add a block</button>
                  <button className="btn ghost" onClick={() => { setDraft(null); setCheck(null); }}>Cancel</button>
                  <button className="btn" onClick={runCheck}>Check this change</button>
                  <button className="btn primary" onClick={makeLive} disabled={!check?.ok} title={check?.ok ? "" : "Check the change first"}>Make it live</button>
                </div>
                {check && (
                  <div style={{ marginBottom: 12 }}>
                    {check.ok ? (
                      <>
                        <div className="notice"><b>Valid.</b> Same checks as before any release: every action has a receipt number, the AI holds no approval powers, every system and approval exists.{check.warnings?.length ? ` ${check.warnings.length} note(s).` : ""}</div>
                        {check.preview && <div style={{ marginTop: 10 }}><div className="small muted" style={{ marginBottom: 6 }}>After your change:</div><Blocks steps={check.preview.steps} /></div>}
                      </>
                    ) : (
                      <div className="refusal"><b>Not valid.</b> {(check.errors || []).join(" · ")}</div>
                    )}
                  </div>
                )}
                <textarea className="code" value={draft} onChange={(e) => { setDraft(e.target.value); setCheck(null); }} aria-label="Workflow file" />
              </section>
            )}
          </div>
        )}
      </div>
    </>
  );
}
