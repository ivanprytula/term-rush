import { test, expect } from "@playwright/test";
import { mockBackend } from "./mocks";

test.describe("Classic mode", () => {
  test("starts unchecked, shows the pre-game screen", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");

    await expect(
      page.getByRole("checkbox", { name: /sprint mode/i }),
    ).not.toBeChecked();
    await expect(
      page.getByRole("button", { name: "start round" }),
    ).toBeVisible();
  });

  test("plays a full round and reaches the summary screen", async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto("/");

    await page.getByRole("button", { name: "start round" }).click();

    // 10 terms per Classic round (ROUND_LENGTH) — answer each and advance.
    for (let i = 0; i < 10; i++) {
      await expect(page.getByText("# define this term")).toBeVisible();
      await page.getByPlaceholder("type your answer…").fill("an answer");
      await page.getByRole("button", { name: "submit" }).click();

      await expect(page.getByText(/\[ CORRECT \]/)).toBeVisible();
      const continueLabel = i < 9 ? "next term" : "see results";
      await page
        .getByRole("button", { name: continueLabel })
        .click();
    }

    await expect(page.getByText("# round complete")).toBeVisible();
    await expect(page.getByRole("button", { name: "play again" })).toBeVisible();
  });

  test("shows the term counter, not a countdown", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");
    await page.getByRole("button", { name: "start round" }).click();

    await expect(page.getByText("term 1/10")).toBeVisible();
    await expect(page.getByText(/⏱/)).not.toBeVisible();
  });

  test("play again starts a genuinely new round", async ({ page }) => {
    await mockBackend(page);
    const roundIds: string[] = [];
    page.on("request", (req) => {
      if (req.method() === "POST" && req.url().endsWith("/game-rounds")) {
        roundIds.push("pending");
      }
    });
    page.on("response", async (res) => {
      if (
        res.request().method() === "POST" &&
        res.url().endsWith("/game-rounds")
      ) {
        const body = await res.json();
        roundIds[roundIds.length - 1] = body.id;
      }
    });

    await page.goto("/");
    await page.getByRole("button", { name: "start round" }).click();

    for (let i = 0; i < 10; i++) {
      await page.getByPlaceholder("type your answer…").fill("an answer");
      await page.getByRole("button", { name: "submit" }).click();
      const continueLabel = i < 9 ? "next term" : "see results";
      await page.getByRole("button", { name: continueLabel }).click();
    }

    await page.getByRole("button", { name: "play again" }).click();
    await expect(page.getByText("# define this term")).toBeVisible();

    expect(roundIds).toHaveLength(2);
    expect(roundIds[0]).not.toBe(roundIds[1]);
  });
});
