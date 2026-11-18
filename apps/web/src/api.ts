// Thin client for the SETU API. The console can only ask; the kernel decides.
export type Json = any;

async function call<T = Json>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data && (data.error || data.detail)) || `${res.status} ${res.statusText}`);
  return data as T;
}

export const api = {
  get: <T = Json>(path: string) => call<T>("GET", path),
  post: <T = Json>(path: string, body: unknown = {}) => call<T>("POST", path, body),
};

export const fmtInr = (v: number | null | undefined, digits = 3) =>
  v === null || v === undefined ? "—" : `₹${v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
export const fmtPct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);
export const fmtDur = (s: number | null | undefined) => {
  if (s === null || s === undefined) return "—";
  if (s < 90) return `${Math.round(s)}s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  if (s < 172800) return `${(s / 3600).toFixed(1)} h`;
  return `${(s / 86400).toFixed(1)} days`;
};
export const fmtTime = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—");
export const short = (s: string | null | undefined, n = 10) => (s ? (s.length > n ? s.slice(0, n) + "…" : s) : "—");
