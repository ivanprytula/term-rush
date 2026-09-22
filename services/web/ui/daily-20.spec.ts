import { test, expect } from "@playwright/test";
import { mockBackend } from "./mocks";

test.describe("Daily 20", () => {
  test("mode picker selects daily 20 before starting", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");

    await page.getByRole("combobox", { name: "mode" }).selectOption("daily_20");
    await page.getByRole("button", { name: "start round" }).click();

    await expect(page.getByText("# define this term")).toBeVisible();
    await expect(page.getByText("term 1/20")).toBeVisible();
    await expect(page.getByText(/⏱/)).not.toBeVisible();
  });

  test("20 answers ends the round", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");
    await page.getByRole("combobox", { name: "mode" }).selectOption("daily_20");
    await page.getByRole("button", { name: "start round" }).click();

    for (let i = 0; i < 20; i++) {
      await expect(page.getByText(`term ${i + 1}/20`)).toBeVisible();
      await page.getByPlaceholder("type your answer…").fill("an answer");
      await page.getByRole("button", { name: "submit" }).click();
      await expect(page.getByText(/\[ CORRECT \]/)).toBeVisible();
      const continueLabel = i < 19 ? "next term" : "see results";
      await page.getByRole("button", { name: continueLabel }).click();
    }

    await expect(page.getByText("# daily 20 complete")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "play again" }),
    ).toBeVisible();
  });
});
