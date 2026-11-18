import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** Fetch a path and re-fetch every `ms` while mounted. Returns [data, reload]. */
export function usePoll<T = any>(path: string | null, ms = 2500): [T | null, () => void, string | null] {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  const load = useCallback(() => {
    if (!path) return;
    api.get<T>(path).then((d) => alive.current && (setData(d), setError(null))).catch((e) => alive.current && setError(String(e.message || e)));
  }, [path]);
  useEffect(() => {
    alive.current = true;
    load();
    if (!ms) return () => { alive.current = false; };
    const t = setInterval(load, ms);
    return () => { alive.current = false; clearInterval(t); };
  }, [load, ms]);
  return [data, load, error];
}
