import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, call, setToken } from "../lib/api/client";
import { useMe } from "./App";

export default function Login() {
  const { setMe } = useMe();
  const nav = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try {
      const path = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const r: any = await call(api.POST(path as "/api/auth/login", { body: { email, password } }));
      setToken(r.token); setMe(r.user); nav("/inbox");
    } catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="center panel">
      <h1 style={{ marginTop: 0 }}>GigBid</h1>
      <p className="muted">Your freelance copilot: finds jobs, flags scams, drafts grounded proposals. You approve everything.</p>
      <form onSubmit={submit}>
        <label htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <label htmlFor="pw">Password</label>
        <input id="pw" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} />
        {err && <div className="banner bad" role="alert" style={{ marginTop: 10 }}>{err}</div>}
        <div className="row" style={{ marginTop: 14 }}>
          <button className="primary" type="submit">{mode === "login" ? "Sign in" : "Create account"}</button>
          <button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
          </button>
        </div>
      </form>
    </div>
  );
}
