import { useState } from "react";
import { api, call } from "../lib/api/client";
import RunTimeline from "./RunTimeline";

/** Approve / edit / reject a pending interrupt. Approving resumes the LangGraph thread (nothing is sent before). */
export default function ApprovalPanel({ approval, text, onDone }: { approval: any; text: string; onDone: () => void }) {
  const [edited, setEdited] = useState(text);
  const [reason, setReason] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const p = approval.payload;
  const preview = p.preview || {};
  const decide = async (action: "approve" | "edit" | "reject") => {
    setErr(null);
    try {
      const body: any = { action };
      if (action === "edit") body.edited_text = edited;
      if (action === "reject") body.reason = reason;
      const r = await call(api.POST("/api/approvals/{approval_id}/decide", { params: { path: { approval_id: approval.id } }, body }));
      setRunId((r as any).run_id);
    } catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="panel" data-testid="approval-panel">
      <h3 style={{ marginTop: 0 }}>Approval</h3>
      {!p.can_approve && <div className="banner warn" role="alert">Compliance blocked this draft: {(p.compliance?.blocked_reasons || []).join("; ")}. Edit it to continue.</div>}
      <div className="muted" data-testid="dry-run">
        Dry run: <b>{preview.operation || "send"}</b> to <b>{preview.target || "marketplace"}</b>
        {preview.connects_cost != null && <> · costs <b>{preview.connects_cost} Connects</b> (balance {preview.connects_balance} → {preview.connects_balance_after})</>}
        {(preview.warnings || []).map((w: string) => <div key={w} className="chip warn">{w}</div>)}
      </div>
      <label htmlFor="edit-box">Text that will be sent (edit before approving if needed)</label>
      <textarea id="edit-box" rows={9} value={edited} onChange={(e) => setEdited(e.target.value)} data-testid="edit-box" />
      <div className="row" style={{ marginTop: 10 }}>
        <button className="primary" disabled={!p.can_approve || edited !== text || !!runId} onClick={() => decide("approve")} data-testid="approve">Approve and send</button>
        <button disabled={edited === text || !!runId} onClick={() => decide("edit")} data-testid="save-edit">Save edit and re-check</button>
        <input aria-label="Reason for rejecting" placeholder="Reason for rejecting" value={reason} onChange={(e) => setReason(e.target.value)} style={{ maxWidth: 260 }} data-testid="reject-reason" />
        <button className="danger" disabled={!reason || !!runId} onClick={() => decide("reject")} data-testid="reject">Reject</button>
      </div>
      {edited !== text && <p className="muted">You changed the text: save the edit so Compliance re-checks it, then approve.</p>}
      {err && <div className="banner bad" role="alert">{err}</div>}
      {runId && <RunTimeline runId={runId} onEnd={onDone} />}
    </div>
  );
}
