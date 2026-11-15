import { useState } from "react";
import { api, call } from "../lib/api/client";
import { useMe } from "./App";

export default function Onboarding() {
  const { setMe } = useMe();
  const [persona, setPersona] = useState<"ai_ml" | "fullstack" | "data">("ai_ml");
  const [market, setMarket] = useState<"gigsim" | "upwork_live">("gigsim");
  const [floor, setFloor] = useState(32);
  const [minProject, setMinProject] = useState(120);
  const [budget, setBudget] = useState(80);
  const [searches, setSearches] = useState("model, llm, data, api");
  const [upload, setUpload] = useState({ title: "", text: "" });
  const [err, setErr] = useState<string | null>(null);
  const finish = async () => {
    setErr(null);
    try {
      const me = await call(api.POST("/api/auth/onboarding", { body: { persona, marketplace: market, hourly_floor: floor, min_project: minProject,
        weekly_connects_budget: budget, saved_searches: searches.split(",").map((s) => s.trim()).filter(Boolean) } }));
      if (upload.title && upload.text.length >= 50) await call(api.POST("/api/portfolio/upload", { body: { ...upload, kind: "case_study" } }));
      if (market === "upwork_live") {
        const r: any = await call(api.GET("/api/auth/upwork/start"));
        if (r.authorize_url) window.open(r.authorize_url, "_blank", "noopener");
      }
      setMe(me as any);
    } catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="center panel" style={{ maxWidth: 640 }}>
      <h1 style={{ marginTop: 0 }}>Set up GigBid</h1>
      <label htmlFor="persona">Profile</label>
      <select id="persona" value={persona} onChange={(e) => setPersona(e.target.value as any)} data-testid="persona">
        <option value="ai_ml">AI/ML engineer (demo persona)</option>
        <option value="fullstack">Full-stack web developer (demo persona)</option>
        <option value="data">Data analyst (demo persona)</option>
      </select>
      <label htmlFor="market">Marketplace</label>
      <select id="market" value={market} onChange={(e) => setMarket(e.target.value as any)}>
        <option value="gigsim">GigSim (simulator)</option>
        <option value="upwork_live">Upwork (official MCP, OAuth)</option>
      </select>
      <div className="grid2">
        <div><label htmlFor="floor">Hourly floor (USD)</label><input id="floor" type="number" value={floor} onChange={(e) => setFloor(+e.target.value)} /></div>
        <div><label htmlFor="minp">Minimum fixed project (USD)</label><input id="minp" type="number" value={minProject} onChange={(e) => setMinProject(+e.target.value)} /></div>
        <div><label htmlFor="cb">Weekly Connects budget</label><input id="cb" type="number" value={budget} onChange={(e) => setBudget(+e.target.value)} /></div>
        <div><label htmlFor="ss">Saved searches (comma separated)</label><input id="ss" value={searches} onChange={(e) => setSearches(e.target.value)} /></div>
      </div>
      <label htmlFor="up-title">Add a case study to your portfolio (optional)</label>
      <input id="up-title" placeholder="Title" value={upload.title} onChange={(e) => setUpload({ ...upload, title: e.target.value })} />
      <textarea aria-label="Case study text" rows={4} placeholder="What you built, for whom, with which tools, and the measured result" style={{ marginTop: 6 }}
        value={upload.text} onChange={(e) => setUpload({ ...upload, text: e.target.value })} />
      {err && <div className="banner bad" role="alert">{err}</div>}
      <button className="primary" style={{ marginTop: 14 }} onClick={finish} data-testid="finish-onboarding">Finish setup</button>
    </div>
  );
}
