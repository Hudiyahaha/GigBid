import { useEffect, useState } from "react";
import { getToken } from "../lib/api/client";

/** Live node-by-node progress over Server-Sent Events. */
export default function RunTimeline({ runId, onEnd }: { runId: string; onEnd?: (run: any) => void }) {
  const [events, setEvents] = useState<any[]>([]);
  const [done, setDone] = useState<any>(null);
  useEffect(() => {
    setEvents([]); setDone(null);
    const es = new EventSource(`/api/runs/${runId}/stream?token=${encodeURIComponent(getToken() || "")}`);
    es.addEventListener("node", (e) => setEvents((xs) => [...xs, JSON.parse((e as MessageEvent).data)]));
    es.addEventListener("end", (e) => { const r = JSON.parse((e as MessageEvent).data); setDone(r); onEnd?.(r); es.close(); });
    es.onerror = () => es.close();
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);
  return (
    <div aria-live="polite">
      <ol className="timeline" data-testid="run-timeline">
        {events.filter((e) => e.type === "node").map((e, i) => (
          <li key={i}><b>{e.node}</b> <span className="muted">{e.t != null ? `${e.t}s` : ""}</span>{" "}
            {e.status && <span className="chip">{e.status}</span>}
            {e.fit != null && <span className="chip">fit {Number(e.fit).toFixed(2)}</span>}
            {e.risk != null && <span className="chip">risk {Number(e.risk).toFixed(2)}</span>}
            {e.critique_passed != null && <span className="chip">{e.critique_passed ? "critic passed" : "critic: revise"}</span>}
            {e.tokens ? <span className="muted"> {e.tokens} tok</span> : null}
          </li>
        ))}
      </ol>
      {!done ? <p className="muted"><span className="spinner" /> running…</p> : <p className="muted">Finished: <b>{done.status}</b> in {done.latency_s}s · {done.tokens} tokens · ${done.usd?.toFixed(4)}</p>}
    </div>
  );
}
