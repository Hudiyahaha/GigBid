import { Link, useParams } from "react-router-dom";
import { api, call } from "../lib/api/client";
import RunTimeline from "../components/RunTimeline";
import { State, useLoad } from "../components/ui";

export function RunList() {
  const { data, error, loading } = useLoad<any[]>(() => call(api.GET("/api/runs")) as any);
  return (
    <>
      <h1>Agent runs</h1>
      <State loading={loading} error={error} empty={data?.length === 0}>
        <div className="panel" style={{ overflowX: "auto" }}>
          <table><thead><tr><th>Run (trace id)</th><th>Graph</th><th>Job / thread</th><th>Status</th><th>Latency</th><th>Tokens</th><th>Cost</th></tr></thead>
            <tbody>{(data || []).map((r) => (
              <tr key={r.id}><td><Link to={`/runs/${r.id}`}>{r.id.slice(0, 10)}…</Link></td><td>{r.graph}</td><td>{r.ref}</td>
                <td><span className="chip">{r.status}</span></td><td>{r.latency_s}s</td><td>{r.tokens}</td><td>${r.usd.toFixed(4)}</td></tr>))}</tbody></table>
        </div>
      </State>
    </>
  );
}

export function RunView() {
  const { id = "" } = useParams();
  const { data: r, error, loading } = useLoad<any>(() => call(api.GET("/api/runs/{run_id}", { params: { path: { run_id: id } } })), [id]);
  return (
    <State loading={loading} error={error}>
      {r && (
        <>
          <h1>Run {id.slice(0, 10)}…</h1>
          <p className="muted">{r.graph} graph · thread {r.thread_id} · trace id <code>{r.id}</code>
            {r.trace_url && <> · <a href={r.trace_url} target="_blank" rel="noreferrer">open full trace</a></>}</p>
          <div className="panel"><RunTimeline runId={id} /></div>
          {r.usage?.by_node && <div className="panel"><h3>Tokens and cost per node</h3>
            <table><thead><tr><th>Node</th><th>Tokens</th><th>USD</th><th>Latency</th></tr></thead><tbody>
              {Object.entries(r.usage.by_node).map(([n, v]: any) => <tr key={n}><td>{n}</td><td>{v.tokens}</td><td>{Number(v.usd).toFixed(5)}</td><td>{Number(v.latency_s).toFixed(2)}s</td></tr>)}
            </tbody></table></div>}
        </>
      )}
    </State>
  );
}
