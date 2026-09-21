import { test, expect } from "@playwright/test";
import { mockBackend } from "./mocks";

test.describe("Collection picker", () => {
  test("hidden when the bank has no categories", async ({ page }) => {
    await mockBackend(page); // default: categories: []
    await page.goto("/");

    await expect(page.getByLabel(/collection/i)).not.toBeVisible();
  });

  test("shown with 'All terms' plus every category, once loaded", async ({
    page,
  }) => {
    await mockBackend(page, {
      categories: ["architecture", "python-keywords"],
    });
    await page.goto("/");

    const picker = page.getByLabel(/collection/i);
    await expect(picker).toBeVisible();
    await expect(picker).toHaveValue(""); // "All terms" by default
    await expect(picker.locator("option")).toHaveText([
      "All terms",
      "architecture",
      "python-keywords",
    ]);
  });

  test("selecting a category scopes every term fetch in the round", async ({
    page,
  }) => {
    const mock = await mockBackend(page, {
      categories: ["architecture", "python-keywords"],
    });
    await page.goto("/");

    await page.getByLabel(/collection/i).selectOption("python-keywords");
    await page.getByRole("button", { name: "start round" }).click();
    await expect(page.getByText("# define this term")).toBeVisible();
    expect(mock.lastRandomTermCategory()).toBe("python-keywords");

    // Advance one term — the category must still apply on the *next*
    // fetch, not just the round's first one.
    await page.getByPlaceholder("type your answer…").fill("an answer");
    await page.getByRole("button", { name: "submit" }).click();
    await page.getByRole("button", { name: "next term" }).click();
    await expect(page.getByText("# define this term")).toBeVisible();
    expect(mock.lastRandomTermCategory()).toBe("python-keywords");
  });

  test("'All terms' sends no category filter", async ({ page }) => {
    const mock = await mockBackend(page, { categories: ["architecture"] });
    await page.goto("/");

    // Default selection is already "All terms" — just start the round.
    await page.getByRole("button", { name: "start round" }).click();
    await expect(page.getByText("# define this term")).toBeVisible();

    expect(mock.lastRandomTermCategory()).toBeNull();
  });
});
