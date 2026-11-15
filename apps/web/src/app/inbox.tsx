import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, call } from "../lib/api/client";
import { money, RiskBadge, State, useLoad } from "../components/ui";

export default function Inbox() {
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const { data, error, loading, reload } = useLoad<any[]>(() => call(api.GET("/api/jobs", { params: { query: { status: status || undefined, q: q || undefined } } })) as any, [status, q]);
  const [scouting, setScouting] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { const id = setInterval(reload, 5000); return () => clearInterval(id); }, [reload]);
  const scout = async () => {
    setScouting(true); setMsg(null);
    try { const r: any = await call(api.POST("/api/jobs/scout")); setMsg(`${r.queued.length} new jobs (${r.duplicates} duplicates hidden); analysing ${r.analysing}.`); reload(); }
    catch (e: any) { setMsg(e.message); } finally { setScouting(false); }
  };
  const skip = async (id: string) => { await call(api.POST("/api/jobs/{job_id}/skip", { params: { path: { job_id: id } } })); reload(); };
  const analyse = async (id: string) => { await call(api.POST("/api/jobs/{job_id}/analyze", { params: { path: { job_id: id } } })); reload(); };
  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1>Job inbox</h1>
        <button className="primary" onClick={scout} disabled={scouting} data-testid="scout">{scouting ? "Scouting…" : "Scout now"}</button>
      </div>
      {msg && <p className="muted" role="status">{msg}</p>}
      <div className="row panel">
        <label htmlFor="flt" style={{ margin: 0 }}>Status</label>
        <select id="flt" value={status} onChange={(e) => setStatus(e.target.value)} style={{ maxWidth: 200 }}>
          {["", "awaiting_approval", "queued", "analysing", "watch", "skipped", "submitted", "rejected", "needs_attention", "queued_retry", "duplicate"].map((s) => <option key={s} value={s}>{s || "all"}</option>)}
        </select>
        <input aria-label="Search titles" placeholder="Search titles" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 260 }} />
      </div>
      <State loading={loading && !data} error={error} empty={data?.length === 0}>
        <div className="panel" style={{ overflowX: "auto" }}>
          <table data-testid="inbox-table">
            <thead><tr><th>Job</th><th>Fit</th><th>Risk</th><th>Action</th><th>Price</th><th>Connects</th><th /></tr></thead>
            <tbody>
              {(data || []).map((j) => (
                <tr key={j.job_id} data-testid={`job-${j.status}`}>
                  <td><Link to={`/jobs/${j.job_id}`}>{j.title}</Link><div className="muted">{j.category} · <span className="chip">{j.status}</span>{j.source?.startsWith("kaggle") && <span className="chip">real post</span>}</div></td>
                  <td>{j.fit ? j.fit.toFixed(2) : "-"}</td>
                  <td><RiskBadge risk={j.risk || 0} scam={j.summary?.scam} /></td>
                  <td>{j.action || "-"}<div className="muted">{(j.summary?.reasons || [])[0]}</div></td>
                  <td>{money(j.price || j.budget?.max)}{j.budget?.type === "hourly" ? "/h" : ""}</td>
                  <td>{j.connects_cost}</td>
                  <td className="row">
                    {j.status === "awaiting_approval" && <Link to={`/studio/${j.job_id}`}><button className="primary">Review</button></Link>}
                    {["queued", "watch", "queued_retry"].includes(j.status) && <button onClick={() => analyse(j.job_id)}>Analyse</button>}
                    {!["skipped", "submitted"].includes(j.status) && <button onClick={() => skip(j.job_id)}>Skip</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </State>
    </>
  );
}
