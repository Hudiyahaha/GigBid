import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, call } from "../lib/api/client";
import ApprovalPanel from "../components/ApprovalPanel";
import EvidenceHover from "../components/EvidenceHover";
import { money, RiskBadge, State, useLoad } from "../components/ui";

export default function Studio() {
  const { id = "" } = useParams();
  const { data: a, error, loading, reload } = useLoad<any>(() => call(api.GET("/api/approvals/by-job/{job_id}", { params: { path: { job_id: id } } })), [id]);
  const [regen, setRegen] = useState<{ i: number; text: string } | null>(null);
  const p = a?.payload;
  const paragraphs: string[] = (p?.send_payload?.cover_letter || "").split(/\n{2,}|(?<=\?)\s+/).filter(Boolean);
  const regenerate = async (i: number) => {
    const r: any = await call(api.POST("/api/proposals/regenerate-paragraph", { body: { paragraph: paragraphs[i], instruction: "make it more specific to this client" } }));
    setRegen({ i, text: r.text });
  };
  return (
    <State loading={loading} error={error ? `${error}. If you just approved it, see the pipeline.` : null}>
      {p && (
        <>
          <h1>Proposal studio</h1>
          <p className="muted"><Link to={`/jobs/${id}`}>{p.title}</Link> · <RiskBadge risk={p.risk?.score || 0} scam={p.risk?.scam} /> · bid {money(p.price?.amount)}{p.price?.pay_type === "hourly" ? "/h" : ""} · fit {p.fit?.score?.toFixed(2)}</p>
          <div className="grid2">
            <div className="panel">
              <h3>Draft (hover a sentence to see its evidence)</h3>
              <EvidenceHover text={p.draft.cover_letter} claims={p.claims || []} evidence={p.evidence || []} />
              {(p.draft.screening_answers || []).map((q: any, i: number) => (
                <div key={i}><b>{q.question}</b><EvidenceHover text={q.answer} claims={p.claims || []} evidence={p.evidence || []} /></div>))}
              <h4>Regenerate one paragraph</h4>
              {paragraphs.map((t, i) => <div key={i} className="row" style={{ marginBottom: 4 }}><span className="muted" style={{ flex: 1 }}>{t.slice(0, 90)}…</span><button onClick={() => regenerate(i)}>Regenerate</button></div>)}
              {regen && <div className="banner warn">Suggested paragraph {regen.i + 1}: {regen.text} <br />Paste it into the editor and save the edit to re-check it.</div>}
            </div>
            <div>
              <div className="panel">
                <h3>Critic and Compliance</h3>
                {(p.critiques || []).map((c: any, i: number) => (
                  <p key={i}><span className={`chip ${c.passed ? "ok" : "warn"}`}>v{c.version}: {c.passed ? "passed" : "revise"}</span> grounding {c.grounding} · personalisation {c.personalisation}
                    {c.issues?.length > 0 && <span className="muted"> — {c.issues.join("; ")}</span>}</p>))}
                <p className="muted">Claims: {p.verification?.claims} · unsupported before {p.verification?.unsupported_before} → after {p.verification?.unsupported_rate_after} · rewritten {p.verification?.rewritten}</p>
                {(p.compliance?.redactions || []).map((r: any, i: number) => <div key={i} className="chip warn">removed ({r.rule_id}): {r.original}</div>)}
                {(p.compliance?.warnings || []).map((w: string) => <div key={w} className="chip warn">{w}</div>)}
              </div>
              <ApprovalPanel approval={a} text={p.send_payload.cover_letter} onDone={reload} />
            </div>
          </div>
        </>
      )}
    </State>
  );
}
