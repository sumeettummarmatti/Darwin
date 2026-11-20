import { useState } from "react";
import { KeyRound } from "lucide-react";
import { api } from "../api";
import { useApp } from "../context";
import { usePoll } from "../hooks";

/** Ask for a Groq key on the website. Validated with Groq before it is kept; never shown again. */
export function ProviderKey({ compact = false, onlyRejected = false }: { compact?: boolean; onlyRejected?: boolean }) {
  const { user, toast, reloadBoot } = useApp();
  const [status, reload] = usePoll<any>("/api/provider", 5000);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  if (!status) return null;
  const g = status.groq;
  const needsKey = g.state === "missing" || g.state === "rejected";

  async function save() {
    setBusy(true); setMsg(null);
    const r = await api.post("/api/provider/key", { key, user_id: user.id }).catch((e) => ({ ok: false, message: e.message }));
    setBusy(false);
    setMsg({ ok: r.ok, text: r.message });
    if (r.ok) { setKey(""); toast(r.message); reload(); reloadBoot(); }
  }
  async function useSimulator() {
    await api.post("/api/provider", { profile: "sim", user_id: user.id });
    reload(); reloadBoot();
  }

  if (compact && !needsKey) return null;
  if (onlyRejected && g.state !== "rejected") return null;
  return (
    <section className={`panel panel-pad ${g.state === "rejected" ? "key-alert" : ""}`}>
      <div className="row" style={{ alignItems: "flex-start" }}>
        <KeyRound size={20} style={{ marginTop: 3 }} />
        <div style={{ flex: 1 }}>
          <h2>Real AI (optional)</h2>
          <p className="sub" style={{ marginBottom: 8 }}>
            {status.profile === "groq" && g.state !== "rejected"
              ? <>Using <b>Groq</b>. A small model first, a bigger one only when needed. Names and personal details are hidden before anything is sent.</>
              : g.state === "rejected"
                ? <>Groq didn't accept the key, so SETU is using the built-in simulator. Add a new key to use real AI again.</>
                : <>Using the built-in simulator, which is free and works offline. Paste a Groq key to use real AI.</>}
          </p>
          {(needsKey || !compact) && (
            <div className="row">
              <input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder={needsKey ? "Paste a Groq key (starts with gsk_)" : "Replace the key"}
                aria-label="Groq API key" style={{ flex: 1, minWidth: 220 }} autoComplete="off" />
              <button className="btn primary" disabled={busy || !key} onClick={save}>{busy ? "Checking…" : "Save key"}</button>
              <a className="btn ghost" href={g.create_url} target="_blank" rel="noreferrer">Get a free key</a>
              {status.profile !== "sim" && <button className="btn ghost" onClick={useSimulator}>Use the simulator instead</button>}
            </div>
          )}
          {msg && <div className={msg.ok ? "notice small" : "refusal small"} style={{ marginTop: 8 }}>{msg.text}{!msg.ok && <> Try a new one: <a href={g.create_url} target="_blank" rel="noreferrer">get a key</a>.</>}</div>}
        </div>
      </div>
    </section>
  );
}
