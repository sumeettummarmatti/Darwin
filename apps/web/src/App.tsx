import { useCallback, useEffect, useMemo, useState } from "react";
import { Blocks as BlocksIcon, BookOpenText, Clock3, FileCheck2, Gauge, Inbox as InboxIcon, Landmark, LayoutList, MessagesSquare, RotateCcw, ScanEye, ScrollText, Users } from "lucide-react";
import { api, fmtTime } from "./api";
import { Ctx, User } from "./context";
import { usePoll } from "./hooks";
import Overview from "./pages/Overview";
import Story from "./pages/Story";
import Runs from "./pages/Runs";
import Inbox from "./pages/Inbox";
import Chat from "./pages/Chat";
import Governance from "./pages/Governance";
import Policies from "./pages/Policies";
import Privacy from "./pages/Privacy";
import Audit from "./pages/Audit";
import Talent from "./pages/Talent";
import Workflows from "./pages/Workflows";
import { ProviderKey } from "./components/ProviderKey";
import { PageBoundary } from "./components/PageBoundary";

const PAGES: { id: string; label: string; icon: any; group?: string }[] = [
  { id: "story", label: "Start here", icon: BookOpenText },
  { id: "overview", label: "Dashboard", icon: Gauge },
  { id: "runs", label: "Processes", icon: LayoutList, group: "Work" },
  { id: "inbox", label: "Approvals", icon: InboxIcon },
  { id: "chat", label: "Chat", icon: MessagesSquare },
  { id: "talent", label: "Hiring", icon: Users },
  { id: "governance", label: "Safety controls", icon: Landmark, group: "Safety" },
  { id: "workflows", label: "Workflows", icon: BlocksIcon },
  { id: "policies", label: "Rules", icon: FileCheck2 },
  { id: "privacy", label: "Privacy", icon: ScanEye },
  { id: "audit", label: "History log", icon: ScrollText },
];

function parseHash(): [string, string | null] {
  const [page, arg] = window.location.hash.replace(/^#\/?/, "").split("/");
  return [page || "story", arg || null];
}

export default function App() {
  const [[page, arg], setRoute] = useState(parseHash());
  const [boot, setBoot] = useState<any>(null);
  const [userId, setUserId] = useState<string>(() => localStorageGet("setu.user") || "USR-101");
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [queue] = usePoll<any[]>("/api/queue?status=open", 3000);

  const reloadBoot = useCallback(() => { api.get("/api/bootstrap").then(setBoot).catch(() => setTimeout(reloadBoot, 1500)); }, []);
  useEffect(reloadBoot, [reloadBoot]);
  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = useCallback((route: string) => { window.location.hash = `/${route}`; }, []);
  const toast = useCallback((msg: string) => { setToastMsg(msg); setTimeout(() => setToastMsg(null), 4200); }, []);
  const setUser = (id: string) => { setUserId(id); localStorageSet("setu.user", id); };

  const users: User[] = boot?.users || [];
  const user = users.find((u) => u.id === userId) || users[0];
  const mine = (queue || []).filter((q) => user && q.approver_roles.some((r: string) => user.roles.includes(r))).length;

  const ctx = useMemo(() => ({ user, users, setUser, boot, reloadBoot, go, toast }), [user, users, boot, reloadBoot, go, toast]);

  if (!boot || !user) {
    return <div className="empty" style={{ paddingTop: 120 }}>Loading HR Autopilot…</div>;
  }

  async function advance(days: number) {
    const r = await api.post("/api/clock/advance", { days });
    reloadBoot();
    toast(`Date is now ${fmtTime(r.clock)}.`);
  }
  async function reset() {
    await api.post("/api/demo/reset");
    reloadBoot();
    toast("Demo reset. Everything is back to the start.");
    go("story");
  }

  const Page = { overview: Overview, story: Story, runs: Runs, inbox: Inbox, chat: Chat, governance: Governance,
    policies: Policies, privacy: Privacy, audit: Audit, talent: Talent, workflows: Workflows }[page] || Story;

  let lastGroup: string | undefined;
  return (
    <Ctx.Provider value={ctx}>
      <div className="shell">
        <nav className="nav" aria-label="Main">
          <div className="brand"><span className="wordmark">HR Autopilot</span></div>
          {PAGES.map((p) => {
            const header = p.group && p.group !== lastGroup ? <div key={p.group} className="section">{p.group}</div> : null;
            if (p.group) lastGroup = p.group;
            const Icon = p.icon;
            return (
              <span key={p.id} style={{ display: "contents" }}>
                {header}
                <button className={page === p.id ? "active" : ""} onClick={() => go(p.id)} aria-current={page === p.id ? "page" : undefined}>
                  <Icon size={17} /> {p.label}
                  {p.id === "inbox" && mine > 0 && <span className="count">{mine}</span>}
                </button>
              </span>
            );
          })}
          <div className="foot">
            Demo data only.<br />AI: <b style={{ color: "#fff" }}>{boot.profile === "groq" ? "Groq" : "built-in simulator"}</b>
          </div>
        </nav>
        <div className="main">
          <header className="topbar">
            <label className="row small" style={{ gap: 8 }}>
              <span className="muted">You are</span>
              <select value={user.id} onChange={(e) => setUser(e.target.value)} aria-label="You are">
                {users.map((u) => <option key={u.id} value={u.id}>{u.name} — {u.title}</option>)}
              </select>
            </label>
            <span className="grow" />
            <span className="clock"><Clock3 size={15} /> {fmtTime(boot.clock)}</span>
            <button className="btn small" onClick={() => advance(1)}>+1 day</button>
            <button className="btn small" onClick={() => advance(30)}>+30 days</button>
            <button className="btn small ghost" onClick={reset} title="Start the demo again from scratch"><RotateCcw size={14} /> Reset</button>
          </header>
          <main className="content">
            <div style={{ marginBottom: 16 }}><ProviderKey compact onlyRejected={!["story"].includes(page)} /></div>
            <PageBoundary page={page}><Page arg={arg} /></PageBoundary>
          </main>
        </div>
      </div>
      {toastMsg && <div className="toast" role="status">{toastMsg}</div>}
    </Ctx.Provider>
  );
}

function localStorageGet(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}
function localStorageSet(key: string, value: string) {
  try { window.localStorage.setItem(key, value); } catch { /* private mode */ }
}
