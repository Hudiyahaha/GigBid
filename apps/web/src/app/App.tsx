import { createContext, useContext, useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { api, call, getToken, setToken } from "../lib/api/client";
import DegradedBanner from "../components/DegradedBanner";
import Login from "./login";
import Onboarding from "./onboarding";
import Inbox from "./inbox";
import JobDetail from "./job";
import Studio from "./studio";
import Pipeline from "./pipeline";
import Messages from "./messages";
import { RunList, RunView } from "./runs";
import Analytics from "./analytics";
import Settings from "./settings";

type Me = { id: string; email: string; persona: string; onboarded: boolean; display_name: string } | null;
const Ctx = createContext<{ me: Me; setMe: (m: Me) => void }>({ me: null, setMe: () => {} });
export const useMe = () => useContext(Ctx);

export default function App() {
  const [me, setMe] = useState<Me>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!getToken()) { setReady(true); return; }
    call(api.GET("/api/auth/me")).then((m) => setMe(m as Me)).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);
  if (!ready) return <p className="center muted">Loading…</p>;
  return (
    <Ctx.Provider value={{ me, setMe }}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/*" element={!me ? <Navigate to="/login" /> : !me.onboarded ? <Onboarding /> : <Shell />} />
      </Routes>
    </Ctx.Provider>
  );
}

function Shell() {
  const { me, setMe } = useMe();
  const nav = useNavigate();
  const links = [["/inbox", "Job inbox"], ["/pipeline", "Pipeline"], ["/messages", "Messages"], ["/runs", "Agent runs"],
    ["/analytics", "Analytics"], ["/settings", "Settings"]];
  return (
    <div className="layout">
      <nav className="side" aria-label="Main">
        <div className="brand">GigBid</div>
        {links.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
        <div style={{ flex: 1 }} />
        <span className="muted" style={{ padding: "0 10px" }}>{me?.display_name} · {me?.persona}</span>
        <button onClick={() => { setToken(null); setMe(null); nav("/login"); }}>Sign out</button>
      </nav>
      <main>
        <DegradedBanner />
        <Routes>
          <Route path="/inbox" element={<Inbox />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/studio/:id" element={<Studio />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/runs" element={<RunList />} />
          <Route path="/runs/:id" element={<RunView />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/inbox" />} />
        </Routes>
      </main>
    </div>
  );
}
