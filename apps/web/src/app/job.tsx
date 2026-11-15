import { Link, useParams } from "react-router-dom";
import { api, call } from "../lib/api/client";
import { money, RiskBadge, State, useLoad } from "../components/ui";

export default function JobDetail() {
  const { id = "" } = useParams();
  const { data: d, error, loading } = useLoad<any>(() => call(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } })), [id]);
  return (
    <State loading={loading} error={error}>
      {d && (
        <>
          <h1>{d.job?.title}</h1>
          <p className="muted">{d.job?.category} · {d.job?.budget?.type} {money(d.job?.budget?.max)} · <span className="chip">{d.status || d.inbox?.status}</span>
            {d.status === "awaiting_approval" && <> · <Link to={`/studio/${id}`}>Open proposal studio</Link></>}</p>
          {d.attention_reason && <div className="banner warn">{d.attention_reason}</div>}
          <div className="grid2">
            <div className="panel"><h3>Decision</h3><p><b>{d.decision?.action || "not analysed yet"}</b></p>
              <ul>{(d.decision?.reasons || []).map((r: string) => <li key={r}>{r}</li>)}</ul></div>
            <div className="panel"><h3>Risk report <RiskBadge risk={d.risk?.score || 0} scam={d.risk?.scam} /></h3>
              <p className="muted">{d.risk?.explanation}</p>
              <ul>{(d.risk?.flags || []).map((f: any, i: number) => <li key={i}><span className="chip">{f.code}</span> {f.evidence}</li>)}</ul></div>
          </div>
          <div className="panel"><h3>Requirement → evidence matrix (fit {d.fit?.score?.toFixed(2) ?? "-"})</h3>
            <table><thead><tr><th>Requirement</th><th>Strength</th><th>Evidence</th></tr></thead><tbody>
              {(d.fit?.matrix || []).map((m: any, i: number) => (
                <tr key={i}><td>{m.requirement}</td><td><span className={`chip ${m.strength === "strong" ? "ok" : m.strength === "partial" ? "warn" : "bad"}`}>{m.strength}</span></td>
                  <td>{m.evidence_ids.map((e: string) => <span key={e} className="chip">{e}</span>)}<div className="muted">{m.reason}</div></td></tr>))}
            </tbody></table></div>
          <div className="grid2">
            <div className="panel"><h3>JobSpec</h3>
              <ul>{(d.job_spec?.requirements || []).map((r: any, i: number) => <li key={i}>{r.skill} <span className="chip">{r.importance}</span></li>)}</ul>
              {d.job_spec?.hidden_needs?.length > 0 && <p className="muted">Hidden needs: {d.job_spec.hidden_needs.join("; ")}</p>}
              <p className="muted">Screening: {(d.job_spec?.screening_questions || []).join(" | ") || "none"}</p></div>
            <div className="panel"><h3>Price {money(d.price?.amount)}{d.price?.pay_type === "hourly" ? "/h" : ""}</h3>
              <p className="muted">{d.price?.rationale}</p>
              <p>Connects: {d.price?.connects_cost} ({money(d.price?.connects_usd)}) · worth it: <b>{d.price ? (d.price.worth_it ? "yes" : "no") : "-"}</b></p></div>
          </div>
          <details className="panel"><summary>Original post (untrusted)</summary><p style={{ whiteSpace: "pre-wrap" }}>{d.job?.description}</p>
            {(d.job?.injection_removed || []).length > 0 && <div className="banner warn">Ignored injected instructions: {d.job.injection_removed.join(" | ")}</div>}</details>
        </>
      )}
    </State>
  );
}
