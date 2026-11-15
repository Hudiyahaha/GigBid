// Drive the MCP Inspector (already running on :6274 with auth disabled) and save screenshots to docs/images/.
// Usage: node scripts/inspector_shots.mjs <name-prefix>
import { chromium } from "@playwright/test";
import path from "node:path";

const prefix = process.argv[2] || "portfolio";
const out = (n) => path.resolve("..", "..", "docs", "images", `inspector-${prefix}-${n}.png`);
const token = process.env.MCP_PROXY_AUTH_TOKEN || "";
const port = process.env.CLIENT_PORT || "6274";
const proxy = process.env.SERVER_PORT || "6277";
const url = `http://localhost:${port}/?MCP_PROXY_AUTH_TOKEN=${token}&MCP_PROXY_FULL_ADDRESS=http://localhost:${proxy}` +
  "&MCP_SERVER_REQUEST_TIMEOUT=120000&MCP_REQUEST_MAX_TOTAL_TIMEOUT=120000";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
const step = async (name, fn) => {
  try { await fn(); console.log("ok", name); }
  catch (e) { console.log("FAIL", name, String(e).slice(0, 200)); await page.screenshot({ path: out(`debug-${name}`) }); }
};
await page.goto(url);
await step("connect", async () => {
  await page.getByRole("button", { name: /^connect$/i }).click();
  await page.getByText(/connected/i).first().waitFor({ timeout: 120_000 });
  await page.screenshot({ path: out("connected") });
});
await step("tools", async () => {
  await page.getByRole("tab", { name: /tools/i }).click();
  await page.getByRole("button", { name: /list tools/i }).click();
  await page.getByText("search_evidence").first().waitFor({ timeout: 30_000 });
  await page.screenshot({ path: out("tools") });
});
if (prefix === "portfolio") {
  await step("run", async () => {
    // get_case_study answers instantly (no model loading), so v1's fixed 10 s request timeout is not hit
    await page.getByText("get_case_study").first().click();
    await page.locator("input[name=id], #id, textarea#id").first().fill("cs-ai_ml-p01")
      .catch(async () => { await page.getByRole("textbox").last().fill("cs-ai_ml-p01"); });
    await page.getByRole("button", { name: /run tool/i }).click();
    await page.getByText(/Tool Result: Success/i).first().waitFor({ timeout: 60_000 });
    await page.getByText(/Tool Result/i).first().scrollIntoViewIfNeeded();
    await page.screenshot({ path: out("tool-call") });
  });
}
await step("resources", async () => {
  await page.getByRole("tab", { name: /resources/i }).click();
  await page.getByRole("button", { name: /list templates/i }).click().catch(() => {});
  await page.getByRole("button", { name: /list resources/i }).click().catch(() => {});
  await page.waitForTimeout(3000);
  await page.screenshot({ path: out("resources") });
});
if (prefix === "portfolio") {
  await step("prompts", async () => {
    await page.getByRole("tab", { name: /prompts/i }).click();
    await page.getByRole("button", { name: /list prompts/i }).click();
    await page.getByText(/screening/i).first().waitFor({ timeout: 30_000 });
    await page.screenshot({ path: out("prompt-templates") });
  });
}
await browser.close();
