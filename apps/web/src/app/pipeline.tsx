import { useEffect } from "react";
import { api, call } from "../lib/api/client";
import { money, State, useLoad } from "../components/ui";

export default function Pipeline() {
  const { data, error, loading, reload } = useLoad<any>(() => call(api.GET("/api/pipeline")));
  useEffect(() => { const id = setInterval(reload, 6000); return () => clearInterval(id); }, [reload]);
  return (
    <>
      <h1>Pipeline</h1>
      <State loading={loading && !data} error={error}>
        <div className="kanban" data-testid="kanban">
          {Object.entries(data?.columns || {}).map(([col, cards]: any) => (
            <section key={col} className="col" aria-label={col}>
              <h4 style={{ margin: "0 0 8px", textTransform: "capitalize" }}>{col} <span className="muted">{cards.length}</span></h4>
              {cards.map((c: any) => <div key={c.proposal_id} className="card"><b>{c.title}</b><div className="muted">{money(c.bid)} · {c.connects} Connects</div></div>)}
            </section>))}
        </div>
      </State>
    </>
  );
}
