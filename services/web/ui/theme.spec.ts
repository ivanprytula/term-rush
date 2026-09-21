import { test, expect } from "@playwright/test";
import { mockBackend } from "./mocks";

test.describe("Theme select", () => {
  test("defaults to phosphor and lists all themes", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");

    const select = page.getByRole("combobox", { name: /switch theme/i });
    await expect(select).toHaveValue("phosphor");
    await expect(select.locator("option")).toHaveText([
      "phosphor",
      "devtool",
      "synthwave",
      "solarized",
      "high-contrast",
      "nord",
    ]);
  });

  test("switching updates data-theme and persists across reload", async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto("/");

    const select = page.getByRole("combobox", { name: /switch theme/i });
    await select.selectOption("nord");

    await expect(page.locator("html")).toHaveAttribute("data-theme", "nord");
    expect(await page.evaluate(() => localStorage.getItem("term-rush-theme"))).toBe(
      "nord",
    );

    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "nord");
    await expect(
      page.getByRole("combobox", { name: /switch theme/i }),
    ).toHaveValue("nord");
  });

  test("theme choice survives starting a round", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");

    await page
      .getByRole("combobox", { name: /switch theme/i })
      .selectOption("solarized");
    await page.getByRole("button", { name: "start round" }).click();

    await expect(page.locator("html")).toHaveAttribute(
      "data-theme",
      "solarized",
    );
  });
});
