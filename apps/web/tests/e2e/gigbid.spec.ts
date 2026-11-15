import { expect, test } from "@playwright/test";
import { openFirstApproval, signUpAndOnboard } from "./helpers";

test("onboarding: sign up, choose a persona, land in the inbox", async ({ page }) => {
  await signUpAndOnboard(page);
  await expect(page.getByTestId("scout")).toBeVisible();
});

test("approving a proposal resumes the graph and submits it", async ({ page }) => {
  await openFirstApproval(page);
  await expect(page.getByTestId("dry-run")).toContainText("Connects");
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("run-timeline")).toContainText("executor", { timeout: 60_000 });
  await expect(page.getByText(/Finished: submitted/)).toBeVisible({ timeout: 60_000 });
});

test("rejecting requires a reason and stops the thread", async ({ page }) => {
  await openFirstApproval(page);
  await expect(page.getByTestId("reject")).toBeDisabled();
  await page.getByTestId("reject-reason").fill("too far from my niche");
  await page.getByTestId("reject").click();
  await expect(page.getByText(/Finished: rejected/)).toBeVisible({ timeout: 60_000 });
});

test("editing a draft is re-checked by Compliance before approval", async ({ page }) => {
  await openFirstApproval(page);
  const box = page.getByTestId("edit-box");
  await box.fill((await box.inputValue()) + " Contact me at me@example.com, results guaranteed.");
  await expect(page.getByTestId("approve")).toBeDisabled();
  await page.getByTestId("save-edit").click();
  await expect(page.getByText(/Finished: awaiting_approval/)).toBeVisible({ timeout: 60_000 });
  await page.reload();
  const text = await page.getByTestId("edit-box").inputValue();
  expect(text).not.toContain("@example.com");
  expect(text.toLowerCase()).not.toContain("guaranteed");
});

test("degraded mode: the UI says when the marketplace is unavailable", async ({ page, request }) => {
  await signUpAndOnboard(page);
  await request.post("/api/dev/marketplace/down");
  try {
    await page.reload();
    await expect(page.getByTestId("degraded-banner")).toBeVisible({ timeout: 30_000 });
  } finally {
    await request.post("/api/dev/marketplace/up");
  }
  await page.reload();
  await expect(page.getByTestId("degraded-banner")).toBeHidden({ timeout: 30_000 });
});
