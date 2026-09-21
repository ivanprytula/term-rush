import { test, expect } from "@playwright/test";
import { mockBackend } from "./mocks";

test.describe("Sprint mode", () => {
  test("checkbox selects sprint mode before starting", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");

    await page.getByRole("checkbox", { name: /sprint mode/i }).check();
    await page.getByRole("button", { name: "start round" }).click();

    // Countdown visible, term counter is not (mode is mutually exclusive).
    await expect(page.getByText(/⏱/)).toBeVisible();
    await expect(page.getByText(/^term \d+\/10$/)).not.toBeVisible();
  });

  test("counts down while answering, doesn't reset across a submit", async ({
    page,
  }) => {
    await mockBackend(page, { sprintDurationSeconds: 60 });
    await page.goto("/");
    await page.getByRole("checkbox", { name: /sprint mode/i }).check();
    await page.getByRole("button", { name: "start round" }).click();

    const clockText = page.getByText(/⏱/);
    await expect(clockText).toContainText("60s");

    await page.waitForTimeout(1500);
    const midCountText = await clockText.textContent();
    expect(midCountText).not.toContain("60s");

    await page.getByPlaceholder("type your answer…").fill("an answer");
    await page.getByRole("button", { name: "submit" }).click();
    await expect(page.getByText(/\[ CORRECT \]/)).toBeVisible();

    // The countdown kept running through grading — a fresh 60s figure
    // here would mean the timer silently reset, which it must not.
    const afterGradeText = await clockText.textContent();
    expect(afterGradeText).not.toContain("60s");
  });

  test("expiry shows the time's-up screen with the running score", async ({
    page,
  }) => {
    await mockBackend(page, { sprintDurationSeconds: 2 });
    await page.goto("/");
    await page.getByRole("checkbox", { name: /sprint mode/i }).check();
    await page.getByRole("button", { name: "start round" }).click();

    await page.getByPlaceholder("type your answer…").fill("an answer");
    await page.getByRole("button", { name: "submit" }).click();
    await expect(page.getByText(/\[ CORRECT \]/)).toBeVisible();

    // Timer keeps running under the result panel; "see results" replaces
    // "next term" once it hits zero, even mid-result.
    await expect(
      page.getByRole("button", { name: "see results" }),
    ).toBeVisible({ timeout: 5000 });
    await page.getByRole("button", { name: "see results" }).click();

    await expect(page.getByText("# time's up")).toBeVisible();
    await expect(page.getByText("30", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "play again" })).toBeVisible();
  });

  test("submit is blocked once the round has expired", async ({ page }) => {
    await mockBackend(page, { sprintDurationSeconds: 2 });
    await page.goto("/");
    await page.getByRole("checkbox", { name: /sprint mode/i }).check();
    await page.getByRole("button", { name: "start round" }).click();

    // Let the timer run out while the question is still on screen — no
    // submit in flight, matching the "abandon the in-progress question"
    // decision confirmed for expiry behavior.
    await expect(page.getByText("# time's up")).toBeVisible({
      timeout: 5000,
    });
  });

  test("play again re-mints a sprint round with a fresh countdown", async ({
    page,
  }) => {
    // First round expires almost immediately; the round minted by "play
    // again" gets a longer mock duration so there's a comfortable window
    // to assert the countdown actually re-synced to a high value instead
    // of continuing from (or resetting to 0 from) the expired round.
    await mockBackend(page, {
      sprintDurationSeconds: (roundNumber) => (roundNumber === 1 ? 1 : 60),
    });

    await page.goto("/");
    await page.getByRole("checkbox", { name: /sprint mode/i }).check();
    await page.getByRole("button", { name: "start round" }).click();

    await expect(page.getByText("# time's up")).toBeVisible({
      timeout: 5000,
    });
    await page.getByRole("button", { name: "play again" }).click();

    await expect(page.getByText(/⏱/)).toContainText("60s");
  });
});
