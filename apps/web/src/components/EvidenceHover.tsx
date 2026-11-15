import { useState } from "react";

type Claim = { text: string; status: string; evidence_ids: string[]; reason?: string };
type Ev = { item_id: string; title?: string; snippet?: string; type?: string };

const CITE = /\s*\[E:([A-Za-z0-9_\-.]+)\]/g;

/** Renders a draft; every cited sentence shows its evidence on hover / keyboard focus. */
export default function EvidenceHover({ text, claims, evidence }: { text: string; claims: Claim[]; evidence: Ev[] }) {
  const byId = Object.fromEntries(evidence.map((e) => [e.item_id, e]));
  const sentences = text.split(/(?<=[.!?])\s+/);
  return (
    <p style={{ lineHeight: 1.7 }}>
      {sentences.map((s, i) => {
        const ids = [...s.matchAll(CITE)].map((m) => m[1]);
        const plain = s.replace(CITE, "");
        if (!ids.length) return <span key={i}>{plain} </span>;
        const c = claims.find((x) => x.text.replace(CITE, "").trim() === plain.trim());
        return <Sentence key={i} text={plain} ids={ids} status={c?.status || "supported"} byId={byId} />;
      })}
    </p>
  );
}

function Sentence({ text, ids, status, byId }: { text: string; ids: string[]; status: string; byId: Record<string, Ev> }) {
  const [open, setOpen] = useState(false);
  return (
    <span className={`claim ${status}`} tabIndex={0} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} aria-describedby={open ? "ev-tip" : undefined} data-testid="claim">
      {text}{" "}
      {open && (
        <span className="tip" role="tooltip" id="ev-tip">
          <b>{status}</b> · evidence:
          {ids.map((id) => (
            <span key={id} style={{ display: "block", marginTop: 6 }}>
              <span className="chip">{byId[id]?.type || "item"}</span><b>{byId[id]?.title || id}</b>
              <span className="muted" style={{ display: "block" }}>{(byId[id]?.snippet || "").slice(0, 220)}</span>
            </span>
          ))}
        </span>
      )}
    </span>
  );
}
