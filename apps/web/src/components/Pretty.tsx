// Renders any value as something a person can read: no raw JSON anywhere in the console.

export const humanize = (key: string) =>
  key.replace(/^(args|steps|subject|inputs|facts|plan)\./, "").replace(/[._]/g, " ").replace(/\s+/g, " ").trim().replace(/^./, (c) => c.toUpperCase());

const ISO_DATE = /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?([+-]\d{2}:\d{2}|Z)?)?$/;

function Text({ s }: { s: string }) {
  if (s.startsWith("tok_")) return <span className="tok" title="vault token — the raw value never leaves the vault">{s}</span>;
  if (ISO_DATE.test(s)) {
    const d = new Date(s.length === 10 ? s + "T00:00:00" : s);
    if (!isNaN(d.getTime())) return <span>{s.length === 10 ? d.toLocaleDateString("en-IN", { dateStyle: "medium" }) : d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</span>;
  }
  if (s.includes("«")) return <span>{s.split(/(«[^»]+»)/g).map((p, i) => (p.startsWith("«") ? <span key={i} className="tok">{p}</span> : p))}</span>;
  return <span style={{ whiteSpace: "pre-wrap" }}>{s}</span>;
}

export function Pretty({ v, depth = 0 }: { v: any; depth?: number }) {
  if (v === null || v === undefined || v === "") return <span className="muted">—</span>;
  if (typeof v === "boolean") return <span className={`tag ${v ? "ok" : "warn"}`}>{v ? "yes" : "no"}</span>;
  if (typeof v === "number") return <span style={{ fontVariantNumeric: "tabular-nums" }}>{v.toLocaleString("en-IN", { maximumFractionDigits: 4 })}</span>;
  if (typeof v === "string") return <Text s={v} />;
  if (Array.isArray(v)) {
    if (!v.length) return <span className="muted">none</span>;
    if (v.every((x) => x === null || typeof x !== "object")) {
      return <span className="row" style={{ gap: 4 }}>{v.map((x, i) => <span key={i} className="tag"><Pretty v={x} depth={depth + 1} /></span>)}</span>;
    }
    const shown = v.slice(0, 6);
    return (
      <div className="pretty-list">
        {shown.map((x, i) => <div key={i} className="pretty-item"><Pretty v={x} depth={depth + 1} /></div>)}
        {v.length > shown.length && <div className="small muted">and {v.length - shown.length} more</div>}
      </div>
    );
  }
  const entries = Object.entries(v).filter(([k]) => !k.startsWith("_"));
  if (!entries.length) return <span className="muted">—</span>;
  if (depth > 2) return <span className="small muted">{entries.length} fields</span>;
  return (
    <dl className="pretty-obj">
      {entries.map(([k, x]) => (
        <div key={k} className="pretty-pair">
          <dt>{humanize(k)}</dt>
          <dd><Pretty v={x} depth={depth + 1} /></dd>
        </div>
      ))}
    </dl>
  );
}

/** "employment type fixed term · grade L2 · state IN-KA" — for one-line summaries of a case. */
export const sentence = (o: Record<string, any>) =>
  Object.entries(o || {}).map(([k, v]) => `${humanize(k).toLowerCase()} ${Array.isArray(v) ? v.join(", ") : v === null ? "none" : String(v)}`).join(" · ");
