import { useEffect, useState } from "react";
import { api, call } from "../lib/api/client";
import ApprovalPanel from "../components/ApprovalPanel";
import RunTimeline from "../components/RunTimeline";
import { State, useLoad } from "../components/ui";

export default function Messages() {
  const threads = useLoad<any[]>(() => call(api.GET("/api/messages/threads")) as any);
  const [sel, setSel] = useState<string | null>(null);
  return (
    <>
      <h1>Messages</h1>
      <div className="grid2">
        <div className="panel">
          <State loading={threads.loading} error={threads.error} empty={threads.data?.length === 0}>
            {(threads.data || []).map((t) => (
              <button key={t.id} style={{ display: "block", width: "100%", textAlign: "left", marginBottom: 6, fontWeight: sel === t.id ? 700 : 400 }}
                onClick={() => setSel(t.id)}>{t.title} <span className="chip">{t.stage}</span></button>))}
          </State>
        </div>
        {sel && <Thread id={sel} />}
      </div>
    </>
  );
}

function Thread({ id }: { id: string }) {
  const t = useLoad<any>(() => call(api.GET("/api/messages/threads/{thread_id}", { params: { path: { thread_id: id } } })), [id]);
  const pending = useLoad<any[]>(() => call(api.GET("/api/approvals", { params: { query: { kind: "message" } } })) as any, [id]);
  const [runId, setRunId] = useState<string | null>(null);
  const appr = (pending.data || []).find((a) => a.ref === id);
  const full = useLoad<any>(() => (appr ? call(api.GET("/api/approvals/{approval_id}", { params: { path: { approval_id: appr.id } } })) : Promise.resolve(null)), [appr?.id]);
  useEffect(() => setRunId(null), [id]);
  const suggest = async () => {
    const r: any = await call(api.POST("/api/messages/threads/{thread_id}/suggest", { params: { path: { thread_id: id } } }));
    setRunId(r.run_id);
  };
  return (
    <div>
      <div className="panel">
        <State loading={t.loading} error={t.error}>
          {(t.data?.messages || []).map((m: any) => (
            <p key={m.id}><span className="chip">{m.sender}</span> {m.body}</p>))}
        </State>
        <button className="primary" onClick={suggest} disabled={!!appr}>Suggest a reply</button>
        {runId && <RunTimeline runId={runId} onEnd={() => { pending.reload(); }} />}
      </div>
      {full.data && <>
        {full.data.payload.reply?.slots?.length > 0 && <p className="muted">Interview slots offered: {full.data.payload.reply.slots.join(", ")}</p>}
        <p className="muted">Intent: <b>{full.data.payload.intent?.intent}</b>{full.data.payload.intent?.injection_detected && <span className="chip bad">injection ignored</span>}</p>
        <ApprovalPanel approval={full.data} text={full.data.payload.send_payload.body} onDone={() => { pending.reload(); t.reload(); }} />
      </>}
    </div>
  );
}
