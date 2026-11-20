import { useState } from "react";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { api } from "../api";
import { usePoll } from "../hooks";
import { AuditList } from "./Runs";

const KINDS: Record<string, string> = {
  reserved: "Approvals", human: "People's decisions", policy: "Rule checks", connector: "Other systems",
  model: "AI use", devils_advocate: "Devil's Advocate", governance: "Safety controls", step: "Steps", system: "System",
};

export default function Audit() {
  const [kind, setKind] = useState("");
  const [entries] = usePoll<any[]>(`/api/audit?limit=150${kind ? `&kind=${kind}` : ""}`, 3000);
  const [verify, reloadVerify] = usePoll<any>("/api/audit/verify", 3000);
  async function tamper() { await api.post("/api/audit/tamper"); reloadVerify(); }
  async function repair() { await api.post("/api/audit/repair"); reloadVerify(); }

  return (
    <>
      <div className="page-head">
        <h1>History log</h1>
        <p>Everything HR Autopilot did, in order. Each entry is locked to the one before, so a secret edit gets caught.</p>
      </div>
      <section className="panel panel-pad row" style={{ marginBottom: 16, gap: 16 }}>
        {verify?.ok ? <ShieldCheck size={34} color="var(--ok)" /> : <ShieldAlert size={34} color="var(--seal)" />}
        <div>
          <b style={{ fontSize: 18 }}>{verify ? (verify.ok ? `Untouched. All ${verify.checked} entries check out.` : `Someone changed entry ${verify.broken_at}.`) : "Checking…"}</b>
          {!verify?.ok && <div className="small muted">Every entry after it can no longer be trusted until it's put back.</div>}
        </div>
        <span className="spacer" />
        <button className="btn seal" onClick={tamper}>Secretly edit an old entry</button>
        <button className="btn" onClick={repair}>Put it back</button>
      </section>
      <section className="panel">
        <div className="row panel-pad" style={{ paddingBottom: 6 }}>
          <h2 style={{ margin: 0 }}>Latest</h2><span className="spacer" />
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Filter by kind">
            <option value="">Everything</option>
            {Object.entries(KINDS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
        </div>
        <AuditList entries={entries || []} />
      </section>
    </>
  );
}
