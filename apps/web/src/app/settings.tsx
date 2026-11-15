import { useEffect, useState } from "react";
import { api, call } from "../lib/api/client";
import { State, useLoad } from "../components/ui";

export default function Settings() {
  const s = useLoad<any>(() => call(api.GET("/api/settings")));
  const mem = useLoad<any>(() => call(api.GET("/api/memory")));
  const [form, setForm] = useState<any>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => { if (s.data) setForm({ ...s.data, searches: s.data.saved_searches.map((x: any) => x.query).join(", ") }); }, [s.data]);
  const save = async () => {
    await call(api.PUT("/api/settings", { body: { hourly_floor: +form.hourly_floor, min_project: +form.min_project, weekly_connects_budget: +form.weekly_connects_budget,
      autonomy: form.autonomy, strategy: form.strategy, saved_searches: form.searches.split(",").map((x: string) => x.trim()).filter(Boolean) } }));
    setSaved(true); s.reload();
  };
  const forget = async (ns: string, key: string) => {
    await call(api.DELETE("/api/memory/{namespace}/{key}", { params: { path: { namespace: ns, key } } })); mem.reload();
  };
  return (
    <>
      <h1>Settings</h1>
      <State loading={s.loading || !form} error={s.error}>
        {form && <div className="panel">
          <div className="grid2">
            <div><label htmlFor="aut">Autonomy</label>
              <select id="aut" value={form.autonomy} onChange={(e) => setForm({ ...form, autonomy: e.target.value })}>
                <option value="suggest">Suggest only (I decide everything)</option>
                <option value="auto_skip_low_fit">Auto-skip low-fit jobs (never auto-send)</option></select></div>
            <div><label htmlFor="str">Proposal strategy (A/B)</label>
              <select id="str" value={form.strategy} onChange={(e) => setForm({ ...form, strategy: e.target.value })}>
                <option value="evidence_first">Evidence first</option><option value="question_first">Question first</option></select></div>
            <div><label htmlFor="hf">Hourly floor</label><input id="hf" type="number" value={form.hourly_floor} onChange={(e) => setForm({ ...form, hourly_floor: e.target.value })} /></div>
            <div><label htmlFor="mp">Minimum project</label><input id="mp" type="number" value={form.min_project} onChange={(e) => setForm({ ...form, min_project: e.target.value })} /></div>
            <div><label htmlFor="wb">Weekly Connects budget</label><input id="wb" type="number" value={form.weekly_connects_budget} onChange={(e) => setForm({ ...form, weekly_connects_budget: e.target.value })} /></div>
            <div><label htmlFor="sq">Saved searches</label><input id="sq" value={form.searches} onChange={(e) => setForm({ ...form, searches: e.target.value })} /></div>
          </div>
          <p className="muted">Connected accounts: {(s.data.connected_accounts || []).join(", ") || "none"} · marketplace mode: {s.data.marketplace_mode}</p>
          <button className="primary" onClick={save}>Save</button> {saved && <span className="muted" role="status">Saved.</span>}
        </div>}
      </State>
      <div className="panel" data-testid="memory">
        <h3>What GigBid has learned</h3>
        <p className="muted">Only promoted knowledge appears here (style: an edit pattern seen in 3+ jobs; outcomes: 5+ results with a 10-point reply-rate gap). Delete anything you disagree with.</p>
        <State loading={mem.loading} error={mem.error}>
          {["style", "outcome"].map((ns) => (
            <div key={ns}><h4 style={{ textTransform: "capitalize" }}>{ns} memory</h4>
              {(mem.data?.[ns] || []).length === 0 && <p className="muted">Nothing learned yet.</p>}
              {(mem.data?.[ns] || []).map((m: any) => (
                <div key={m.id} className="row" style={{ justifyContent: "space-between" }}>
                  <span>{m.rule} <span className="muted">({m.promotion_rule}; support {m.support ?? m.n})</span></span>
                  <button className="danger" onClick={() => forget(ns, m.id)}>Delete</button></div>))}
            </div>))}
        </State>
      </div>
    </>
  );
}
