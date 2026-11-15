// Records the 3-minute captioned demo (Playwright video) against the local dev stack on :8000 (GigSim on :8081),
// and saves GIF frames. Usage: node scripts/demo_video.mjs   (dev stack must be running with GIGBID_E2E=1)
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const BASE = "http://127.0.0.1:8000";
const GIGSIM = "http://127.0.0.1:8081";
const OUT = path.resolve("..", "..", "demo_output");
const FRAMES = path.join(OUT, "frames");
fs.mkdirSync(FRAMES, { recursive: true });
const email = `demo-${Date.now()}@gigbid.test`;
const password = "demo-password-123";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let token = "";
const api = async (method, p, body) => {
  const r = await fetch(BASE + "/api" + p, { method, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error(`${method} ${p} -> ${r.status} ${await r.text()}`);
  return r.json();
};
const idle = async (maxS = 600) => {
  for (let i = 0; i < maxS / 3; i++) {
    const runs = await api("GET", "/runs");
    if (!runs.some((r) => r.status === "running")) return;
    await sleep(3000);
  }
};

// ---------------- preparation (not recorded) ----------------
console.log("prep: account + scouting");
token = (await api("POST", "/auth/register", { email, password, display_name: "Ayesha (demo)" })).token;
await api("POST", "/auth/onboarding", { persona: "ai_ml", saved_searches: ["churn", "lead-scoring", "entity extraction"],
  hourly_floor: 32, min_project: 120, weekly_connects_budget: 80 });
await api("POST", "/jobs/scout");
await idle();
for (const j of (await api("GET", "/jobs")).filter((x) => x.status === "queued").slice(0, 3)) {
  await api("POST", `/jobs/${j.job_id}/analyze`);
}
// a scam and a planted-injection job (dev set ids) analysed in advance
const SCAM = "dev-ai_ml-004";
const INJ = process.env.INJ_JOB || "dev-ai_ml-019";
await api("POST", `/jobs/${SCAM}/analyze`);
await api("POST", `/jobs/${INJ}/analyze`);
await idle();
let pending = await api("GET", "/approvals?kind=proposal");
console.log("prep: approvals waiting =", pending.length);
if (!pending.length) throw new Error("no proposal reached approval during prep");
const showcase = pending[0];
// approve the others quietly so the simulated clients have several proposals to answer
for (const a of pending.slice(1, 4)) await api("POST", `/approvals/${a.id}/decide`, { action: "approve" });
await idle();

// ---------------- recording ----------------
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: OUT, size: { width: 1280, height: 720 } } });
const page = await ctx.newPage();
let frame = 0;
const snap = async (n = 1) => { for (let i = 0; i < n; i++) await page.screenshot({ path: path.join(FRAMES, `${String(frame++).padStart(3, "0")}.png`) }); };
const cap = async (text, ms = 3500) => {
  await page.evaluate((t) => {
    let d = document.getElementById("demo-cap");
    if (!d) {
      d = document.createElement("div"); d.id = "demo-cap";
      Object.assign(d.style, { position: "fixed", left: "50%", bottom: "16px", transform: "translateX(-50%)", background: "rgba(16,24,40,.9)",
        color: "#fff", padding: "10px 18px", borderRadius: "10px", font: "600 17px system-ui", zIndex: 99999, maxWidth: "92%", textAlign: "center" });
      document.body.appendChild(d);
    }
    d.textContent = t;
  }, text);
  await sleep(ms);
};

// Scene 1: sign in, inbox
await page.goto(BASE + "/login");
await cap("GigBid: a multi-agent freelancer copilot. Nothing is sent without your approval.", 4000);
await page.getByLabel("Email").fill(email);
await page.getByLabel("Password").fill(password);
await page.getByRole("button", { name: "Sign in" }).click();
await page.getByRole("heading", { name: "Job inbox" }).waitFor();
await cap("Job inbox: jobs found by the Scout agent, ranked by fit, with risk badges, action, price and Connects cost.", 6000);
await snap(3);

// Scene 2: one job -> approved proposal
await page.goto(`${BASE}/jobs/${showcase.ref}`);
await cap("Job detail: Analyst, Risk Assessor and Fit Matcher ran in parallel (LangGraph Send).", 4000);
await snap(2);
await page.mouse.wheel(0, 380);
await cap("Requirement -> evidence matrix: every requirement mapped to the freelancer's own portfolio items.", 5000);
await snap(2);
await page.mouse.wheel(0, 500);
await cap("Price from real market data (Kaggle) and the freelancer's floor; Connects are only spent if worth it.", 4500);
await snap(2);
await page.goto(`${BASE}/studio/${showcase.ref}`);
await page.getByTestId("approval-panel").waitFor();
await cap("Proposal studio: the Writer drafted it, the claim verifier checked every claim, Critic and Compliance reviewed it.", 5000);
await snap(2);
const claim = page.getByTestId("claim").first();
if (await claim.count()) { await claim.hover(); await cap("Hover any claim to see the portfolio evidence behind it.", 5000); await snap(3); }
await page.getByTestId("dry-run").scrollIntoViewIfNeeded();
await cap("Dry run: exactly what will be sent and what it costs, before anything leaves GigBid.", 4500);
await snap(2);
await page.getByTestId("approve").click();
await cap("Approve: the paused LangGraph thread resumes; the executor submits it exactly once.", 3000);
await page.getByText(/Finished: submitted/).waitFor({ timeout: 90_000 });
await cap("Submitted. The human approval token is checked again by the marketplace MCP server.", 4500);
await snap(3);
await page.goto(BASE + "/pipeline");
await cap("Pipeline board: the proposal is now on the marketplace.", 4500);
await snap(2);

// Scene 3: scam caught
await page.goto(`${BASE}/jobs/${SCAM}`);
await cap("A scam caught: the Risk Assessor flagged it from rules + client history and skipped it, no proposal drafted.", 7000);
await page.mouse.wheel(0, 250);
await sleep(3000);

// Scene 4: injection ignored
await page.goto(`${BASE}/jobs/${INJ}`);
await cap("This post hides instructions aimed at AI agents (prompt injection).", 3500);
await page.getByText("Original post (untrusted)").click();
await page.getByText("Original post (untrusted)").scrollIntoViewIfNeeded();
await cap("GigBid treats posts as untrusted data: the injected sentence was stripped and never followed.", 7000);

// advance the simulated marketplace so clients respond
await fetch(GIGSIM + "/admin/tick?n=2", { method: "POST", headers: { Authorization: "Bearer gigsim-admin" } });
await sleep(1500);

// Scene 5: client reply handled
await page.goto(BASE + "/messages");
await cap("A client replied. The conversation graph classifies intent, finds interview slots and drafts a reply.", 4000);
const first = page.locator("main .panel button").first();
if (await first.count()) {
  await first.click();
  await sleep(1500);
  await page.getByRole("button", { name: "Suggest a reply" }).click();
  await page.getByTestId("approval-panel").waitFor({ timeout: 120_000 });
  await page.getByTestId("approval-panel").scrollIntoViewIfNeeded();
  await cap("Suggested reply: on-platform, within the price floor, injected text in the message ignored. Approve to send.", 6000);
  await page.getByTestId("approve").click();
  await page.getByText(/Finished: sent/).waitFor({ timeout: 90_000 });
  await cap("Sent after approval, and a tentative interview hold was created in the calendar.", 4500);
} else {
  await cap("(No client has replied yet in this run.)", 3000);
}

// Scene 6: degraded mode + runs
await fetch(BASE + "/api/dev/marketplace/down", { method: "POST" });
await page.goto(BASE + "/inbox");
await page.getByTestId("degraded-banner").waitFor({ timeout: 30_000 });
await cap("Degraded mode: if the marketplace goes down, GigBid says so, queues the work and recovers.", 5500);
await fetch(BASE + "/api/dev/marketplace/up", { method: "POST" });
await page.goto(BASE + "/runs");
await cap("Every run is traced: node by node, with tokens, cost and latency. github.com/Hudiyahaha/GigBid", 6000);
const video = page.video();
await ctx.close();
await browser.close();
const dest = path.join(OUT, "gigbid-demo.webm");
fs.copyFileSync(await video.path(), dest);
console.log("video:", dest, "frames:", frame);
