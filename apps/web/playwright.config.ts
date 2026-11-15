import { defineConfig } from "@playwright/test";

// path is relative to webServer.cwd (the repo root)
const py = process.env.GIGBID_PYTHON || (process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python");

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 480_000,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: { baseURL: "http://127.0.0.1:8000", trace: "retain-on-failure" },
  webServer: {
    command: `${py} -m scripts.dev_stack`,
    cwd: "../..",
    url: "http://127.0.0.1:8000/api/health",
    timeout: 180_000,
    reuseExistingServer: !process.env.CI,
    env: { GIGBID_E2E: "1", HF_HUB_OFFLINE: process.env.HF_HUB_OFFLINE || "1" },
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1280, height: 860 } } },
    { name: "phone", use: { viewport: { width: 390, height: 844 }, isMobile: true }, testMatch: /onboarding/ },
  ],
});
