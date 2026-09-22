import { test, expect } from "@playwright/test";
import { mockBackend } from "./mocks";

test.describe("Boss round", () => {
  test("mode picker selects boss before starting", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");

    await page.getByRole("combobox", { name: "mode" }).selectOption("boss");
    await page.getByRole("button", { name: "start round" }).click();

    await expect(page.getByText("# define this term")).toBeVisible();
    // No sprint/lives/term-count progress indicator for a one-answer round.
    await expect(page.getByText(/⏱/)).not.toBeVisible();
    await expect(page.getByText(/^term \d+\/10$/)).not.toBeVisible();
  });

  test("AI grading checkbox is hidden and replaced with an always-on note", async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto("/");
    await page.getByRole("combobox", { name: "mode" }).selectOption("boss");
    await page.getByRole("button", { name: "start round" }).click();

    await expect(
      page.getByRole("checkbox", { name: /get ai feedback/i }),
    ).not.toBeVisible();
    await expect(
      page.getByText("AI grading is always on for boss rounds."),
    ).toBeVisible();
  });

  test("one answer ends the round regardless of verdict", async ({ page }) => {
    await mockBackend(page, {
      gradeRule: () => ({ verdict: "incorrect", score: 0 }),
    });
    await page.goto("/");
    await page.getByRole("combobox", { name: "mode" }).selectOption("boss");
    await page.getByRole("button", { name: "start round" }).click();

    await page.getByPlaceholder("type your answer…").fill("an answer");
    await page.getByRole("button", { name: "submit" }).click();

    await expect(page.getByText(/\[ NOT QUITE \]/)).toBeVisible();
    await page.getByRole("button", { name: "see results" }).click();

    await expect(page.getByText("# boss round complete")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "play again" }),
    ).toBeVisible();
  });
});
