import { useState } from "react";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { api, short } from "../api";
import { usePoll } from "../hooks";
import { AuditList } from "./Runs";

export default function Audit() {
  const [kind, setKind] = useState("");
  const [entries] = usePoll<any[]>(`/api/audit?limit=150${kind ? `&kind=${kind}` : ""}`, 3000);
  const [verify, reloadVerify] = usePoll<any>("/api/audit/verify", 3000);
  async function tamper() { await api.post("/api/audit/tamper"); reloadVerify(); }
  async function repair() { await api.post("/api/audit/repair"); reloadVerify(); }

  return (
    <>
      <div className="page-head">
        <h1>Audit chain</h1>
        <p>One entry per kernel step, each carrying the hash of the one before. Change a single historic row and verification breaks from that point on.</p>
      </div>
      <section className="panel panel-pad row" style={{ marginBottom: 16, gap: 16 }}>
        {verify?.ok ? <ShieldCheck size={34} color="var(--ok)" /> : <ShieldAlert size={34} color="var(--seal)" />}
        <div>
          <b style={{ fontSize: 18 }}>{verify ? (verify.ok ? `Intact · ${verify.checked} entries verified` : `Broken at entry #${verify.broken_at}`) : "Verifying…"}</b>
          <div className="small muted">{verify?.ok ? <>head <span className="mono">{short(verify.head, 40)}</span></> : verify?.reason}</div>
        </div>
        <span className="spacer" />
        <button className="btn seal" onClick={tamper}>Edit a historic row in the database</button>
        <button className="btn" onClick={repair}>Restore it</button>
      </section>
      <section className="panel">
        <div className="row panel-pad" style={{ paddingBottom: 6 }}>
          <h2 style={{ margin: 0 }}>Latest entries</h2><span className="spacer" />
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Filter by kind">
            <option value="">Every kind</option>
            {["reserved", "human", "policy", "connector", "model", "prativaad", "governance", "step", "system"].map((k) => <option key={k}>{k}</option>)}
          </select>
        </div>
        <AuditList entries={entries || []} />
      </section>
    </>
  );
}
