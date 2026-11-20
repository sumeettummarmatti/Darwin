import { useState } from "react";
import { fmtTime } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";
import { KIND_LABEL, Packet } from "../components/Packet";
import { humanize, plainAction } from "../components/Pretty";

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
        <h1>Approvals</h1>
        <p>Things only a person can decide. Each one shows what SETU worked out and asks one question.</p>
      </div>
      <div className="row" style={{ marginBottom: 12 }}>
        <button className={`btn small ${tab === "mine" ? "primary" : ""}`} onClick={() => setTab("mine")}>For {user.name.split(" ")[0]}</button>
        <button className={`btn small ${tab === "all" ? "primary" : ""}`} onClick={() => setTab("all")}>Everyone's</button>
        <button className={`btn small ${tab === "receipts" ? "primary" : ""}`} onClick={() => setTab("receipts")}>Past decisions</button>
      </div>

      {tab === "receipts" ? <Receipts rows={receipts || []} /> : (
        <div className="split">
          <section className="panel">
            <table className="t">
              <tbody>
                {list.map((i) => (
                  <tr key={i.id} className={`click ${sel?.id === i.id ? "sel" : ""}`} onClick={() => setSelId(i.id)}>
                    <td>
                      <div className="row"><span className={`tag ${i.kind === "reserved" || i.kind === "route_only" ? "seal" : i.kind === "objection" ? "rule" : "warn"}`}>{KIND_LABEL[i.kind] || humanize(i.kind)}</span>
                        <span className="small muted">{fmtTime(i.created_at)}</span></div>
                      <div style={{ marginTop: 4 }}>{i.title}</div>
                      <div className="small muted">{i.packet?.subject?.display_name || i.packet?.subject_id || ""}</div>
                    </td>
                  </tr>
                ))}
                {!list.length && <tr><td className="empty">Nothing waiting for {tab === "mine" ? user.name.split(" ")[0] : "anyone"}. Change "You are" at the top to see someone else's.</td></tr>}
              </tbody>
            </table>
          </section>
          <section className="panel panel-pad">
            {sel ? (
              <>
                <Packet key={sel.id} item={sel} onDecided={() => { reload(); setSelId(null); }} />
                {sel.run_id && <button className="btn small ghost" style={{ marginTop: 12 }} onClick={() => go(`runs/${sel.run_id}`)}>Open the process</button>}
              </>
            ) : <div className="empty">Pick one on the left.</div>}
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
  if (!rows.length) return <div className="panel empty">No decisions yet.</div>;
  return (
    <div className="grid g2">
      {rows.map((r) => (
        <section key={r.id} className="panel panel-pad row" style={{ alignItems: "flex-start", gap: 20 }}>
          <div className={`seal-stamp ${r.decision === "approve" ? "" : "ok"}`}>
            <b>{({ approve: "Approved", reject: "Rejected", acknowledge: "Received", accept_draft: "Accepted", abort: "Stopped", proceed: "Went ahead", skip_step: "Skipped" } as Record<string, string>)[r.decision] || humanize(r.decision)}</b>
          </div>
          <div className="stack" style={{ gap: 6, minWidth: 0 }}>
            <b>{plainAction(r.action)}</b>
            <div className="small">{r.approver.name} · {fmtTime(r.decided_at)}</div>
            {r.note && <div className="small">“{r.note}”</div>}
            <div className="row">
              <button className="btn small" onClick={() => verify(r.id)}>Check it wasn't changed</button>
              {r.id in verified && <span className={`tag ${verified[r.id] ? "ok" : "seal"}`}>{verified[r.id] ? "Matches what they saw" : "Doesn't match"}</span>}
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
