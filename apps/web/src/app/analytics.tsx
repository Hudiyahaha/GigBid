import { api, call } from "../lib/api/client";
import { State, useLoad } from "../components/ui";

export default function Analytics() {
  const { data: a, error, loading } = useLoad<any>(() => call(api.GET("/api/analytics")));
  return (
    <>
      <h1>Analytics</h1>
      <State loading={loading} error={error}>
        {a && (
          <>
            <div className="grid2">
              <div className="panel"><h3>Connects vs outcomes</h3><p>{a.connects_spent} Connects spent · {a.replies} replies · {a.hires} hires</p>
                <p className="muted">Connects per reply: {a.connects_per_reply ?? "-"}</p></div>
              <div className="panel"><h3>Cost and latency</h3>
                <p>Per job analysed: p50 {a.latency.job_p50_s}s · p95 {a.latency.job_p95_s}s · ${a.cost.usd_per_job}</p>
                <p>Per proposal: p95 {a.latency.proposal_p95_s}s · ${a.cost.usd_per_proposal}</p>
                <p className="muted">Declared budgets: {a.budgets && `${a.budgets.p95_latency_s_per_job_analysed}s / $${a.budgets.usd_per_job_analysed} per job, ${a.budgets.p95_latency_s_per_proposal}s / $${a.budgets.usd_per_proposal} per proposal`}</p></div>
            </div>
            <div className="panel"><h3>Reply and hire rate by category</h3>
              <table><thead><tr><th>Category</th><th>Submitted</th><th>Reply rate</th><th>Hire rate</th></tr></thead><tbody>
                {a.by_category.map((c: any) => <tr key={c.category}><td>{c.category}</td><td>{c.submitted}</td><td>{(c.reply_rate * 100).toFixed(0)}%</td><td>{(c.hire_rate * 100).toFixed(0)}%</td></tr>)}
              </tbody></table>{a.by_category.length === 0 && <p className="muted">No submitted proposals yet.</p>}</div>
            <div className="panel"><h3>Top rejection reasons</h3>
              <ul>{a.top_rejection_reasons.map((r: any) => <li key={r.reason}>{r.reason} ({r.count})</li>)}</ul>
              {a.top_rejection_reasons.length === 0 && <p className="muted">None yet.</p>}</div>
          </>
        )}
      </State>
    </>
  );
}
