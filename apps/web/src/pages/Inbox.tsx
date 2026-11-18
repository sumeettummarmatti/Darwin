import { useState } from "react";
import { fmtTime, short } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";
import { Packet } from "../components/Packet";

export default function Inbox() {
  const { user, go } = useApp();
  const [tab, setTab] = useState<"mine" | "all" | "receipts">("mine");
  const [items, reload] = usePoll<any[]>(`/api/queue?status=open&user_id=${user.id}`, 2500);
  const [receipts] = usePoll<any[]>(tab === "receipts" ? "/api/receipts" : null, 4000);
  const [selId, setSelId] = useState<string | null>(null);
  const list = (items || []).filter((i) => tab === "all" || i.can_decide);
  const sel = list.find((i) => i.id === selId) || list[0];

  return (
    <>
      <div className="page-head">
        <h1>Decisions</h1>
        <p>Only people decide here. Each item arrives with the computed values, the clauses applied and one question. Approving binds to the exact packet you see.</p>
      </div>
      <div className="row" style={{ marginBottom: 12 }}>
        <button className={`btn small ${tab === "mine" ? "primary" : ""}`} onClick={() => setTab("mine")}>For {user.name.split(" ")[0]}</button>
        <button className={`btn small ${tab === "all" ? "primary" : ""}`} onClick={() => setTab("all")}>Everything open</button>
        <button className={`btn small ${tab === "receipts" ? "primary" : ""}`} onClick={() => setTab("receipts")}>Receipts</button>
      </div>

      {tab === "receipts" ? <Receipts rows={receipts || []} /> : (
        <div className="split">
          <section className="panel">
            <table className="t">
              <tbody>
                {list.map((i) => (
                  <tr key={i.id} className={`click ${sel?.id === i.id ? "sel" : ""}`} onClick={() => setSelId(i.id)}>
                    <td>
                      <div className="row"><span className={`tag ${i.kind === "reserved" || i.kind === "route_only" ? "seal" : i.kind === "objection" ? "rule" : "warn"}`}>{i.kind.replace("_", " ")}</span>
                        <span className="small muted">{fmtTime(i.created_at)}</span></div>
                      <div style={{ marginTop: 4 }}>{i.title}</div>
                      <div className="small muted">{i.packet?.subject?.display_name || i.packet?.subject_id || ""} {i.packet?.workflow ? `· ${i.packet.workflow}` : ""}</div>
                    </td>
                  </tr>
                ))}
                {!list.length && <tr><td className="empty">Nothing waiting for {tab === "mine" ? user.name : "anyone"}. Switch user at the top to see other approvers' queues.</td></tr>}
              </tbody>
            </table>
          </section>
          <section className="panel panel-pad">
            {sel ? (
              <>
                <Packet key={sel.id} item={sel} onDecided={() => { reload(); setSelId(null); }} />
                {sel.run_id && <button className="btn small ghost" style={{ marginTop: 12 }} onClick={() => go(`runs/${sel.run_id}`)}>Open the run</button>}
              </>
            ) : <div className="empty">Select an item.</div>}
          </section>
        </div>
      )}
    </>
  );
}

function Receipts({ rows }: { rows: any[] }) {
  const [verified, setVerified] = useState<Record<string, boolean>>({});
  async function verify(id: string) {
    const r = await fetch(`/api/receipts/${id}/verify`).then((x) => x.json());
    setVerified((v) => ({ ...v, [id]: r.matches }));
  }
  if (!rows.length) return <div className="panel empty">No receipts yet. Approve a reserved decision to create one.</div>;
  return (
    <div className="grid g2">
      {rows.map((r) => (
        <section key={r.id} className="panel panel-pad row" style={{ alignItems: "flex-start", gap: 20 }}>
          <div className={`seal-stamp ${r.decision === "approve" ? "" : "ok"}`}>
            <b>{r.decision.toUpperCase()}</b>
            <small>{r.context_hash.slice(7, 31)}</small>
          </div>
          <div className="stack" style={{ gap: 6, minWidth: 0 }}>
            <b className="mono" style={{ fontSize: 13 }}>{r.action}</b>
            <div className="small">{r.approver.name} ({r.approver.roles.join(", ")}) · {fmtTime(r.decided_at)} · via {r.channel}</div>
            <div className="small muted">Subject {r.subject || "—"} · policies {r.policy_versions.join(", ") || "—"}</div>
            {r.note && <div className="small">“{r.note}”</div>}
            <div className="small mono muted">receipt {short(r.id, 24)} · audit #{r.audit_seq}</div>
            <div className="row">
              <button className="btn small" onClick={() => verify(r.id)}>Re-hash the stored snapshot</button>
              {r.id in verified && <span className={`tag ${verified[r.id] ? "ok" : "seal"}`}>{verified[r.id] ? "matches what was shown" : "does not match"}</span>}
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
