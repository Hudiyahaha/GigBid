import { expect, Page } from "@playwright/test";

export async function signUpAndOnboard(page: Page) {
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.test`;
  await page.goto("/login");
  await page.getByRole("button", { name: /create an account/i }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("test-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByTestId("persona").selectOption("ai_ml");
  // saved searches inside the AI/ML persona's niche (broad searches mostly return correctly-skipped off-domain jobs)
  await page.getByLabel("Saved searches (comma separated)").fill("churn, lead-scoring, entity extraction");
  await page.getByTestId("finish-onboarding").click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
  return email;
}

/** Scout, then keep analysing queued jobs until one waits for approval; open it in the studio. */
export async function openFirstApproval(page: Page) {
  await signUpAndOnboard(page);
  await page.getByTestId("scout").click();
  await expect(page.getByRole("status")).toContainText("new jobs", { timeout: 60_000 });
  const deadline = Date.now() + 360_000; // CPU-only retrieval: ~40 s per job, 3 jobs analysed in parallel
  while (Date.now() < deadline) {
    const review = page.getByRole("button", { name: "Review" }).first();
    if (await review.isVisible().catch(() => false)) {
      await review.click();
      await expect(page.getByTestId("approval-panel")).toBeVisible({ timeout: 30_000 });
      return;
    }
    await page.waitForTimeout(4000);
  }
  throw new Error("no job reached human approval");
}
