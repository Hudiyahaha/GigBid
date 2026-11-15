import { useCallback, useEffect, useState } from "react";

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(() => {
    setLoading(true);
    fn().then((d) => { setData(d); setError(null); }).catch((e) => setError(String(e.message || e))).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload, setData };
}

export function State({ loading, error, empty, children }: { loading: boolean; error: string | null; empty?: boolean; children: React.ReactNode }) {
  if (loading) return <p className="muted" role="status"><span className="spinner" /> Loading…</p>;
  if (error) return <div className="banner bad" role="alert">Something went wrong: {error}</div>;
  if (empty) return <p className="muted">Nothing here yet.</p>;
  return <>{children}</>;
}

export function RiskBadge({ risk, scam }: { risk: number; scam?: boolean }) {
  const cls = scam || risk >= 0.75 ? "bad" : risk >= 0.45 ? "warn" : "ok";
  return <span className={`chip ${cls}`} title={`risk ${risk.toFixed(2)}`}>{scam ? "scam" : cls === "ok" ? "low risk" : cls === "warn" ? "some risk" : "high risk"}</span>;
}

export const money = (v?: number | null) => (v == null ? "-" : `$${Math.round(v).toLocaleString()}`);
