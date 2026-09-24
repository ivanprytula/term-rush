import { test, expect } from "@playwright/test";
import { mockBackend } from "./mocks";

test.describe("Difficulty picker", () => {
  test("shown with 'any' plus every level, default unselected", async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto("/");

    const picker = page.getByLabel(/difficulty/i);
    await expect(picker).toBeVisible();
    await expect(picker).toHaveValue(""); // "any" by default
    await expect(picker.locator("option")).toHaveText([
      "any",
      "trivial+",
      "easy+",
      "moderate+",
      "hard+",
      "expert+",
    ]);
  });

  test("selecting a difficulty scopes every term fetch in the round", async ({
    page,
  }) => {
    const mock = await mockBackend(page);
    await page.goto("/");

    await page.getByLabel(/difficulty/i).selectOption("4");
    await page.getByRole("button", { name: "start round" }).click();
    await expect(page.getByText("# define this term")).toBeVisible();
    expect(mock.lastRandomTermDifficulty()).toBe("4");

    // Advance one term — the floor must still apply on the *next* fetch,
    // not just the round's first one.
    await page.getByPlaceholder("type your answer…").fill("an answer");
    await page.getByRole("button", { name: "submit" }).click();
    await page.getByRole("button", { name: "next term" }).click();
    await expect(page.getByText("# define this term")).toBeVisible();
    expect(mock.lastRandomTermDifficulty()).toBe("4");
  });

  test("'any' sends no difficulty filter", async ({ page }) => {
    const mock = await mockBackend(page);
    await page.goto("/");

    // Default selection is already "any" — just start the round.
    await page.getByRole("button", { name: "start round" }).click();
    await expect(page.getByText("# define this term")).toBeVisible();

    expect(mock.lastRandomTermDifficulty()).toBeNull();
  });
});
