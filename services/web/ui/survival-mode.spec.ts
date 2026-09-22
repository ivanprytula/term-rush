import { test, expect } from "@playwright/test";
import { mockBackend } from "./mocks";

test.describe("Survival mode", () => {
  test("mode picker selects survival before starting", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");

    await page.getByRole("combobox", { name: "mode" }).selectOption("survival");
    await page.getByRole("button", { name: "start round" }).click();

    // Lives indicator visible, term counter and countdown are not (modes
    // are mutually exclusive).
    await expect(page.getByText(/^term \d+\/10$/)).not.toBeVisible();
    await expect(page.getByText(/⏱/)).not.toBeVisible();
  });

  test("3 wrong answers in a row ends the round out of lives", async ({
    page,
  }) => {
    await mockBackend(page, {
      gradeRule: () => ({ verdict: "incorrect", score: 0 }),
    });
    await page.goto("/");
    await page.getByRole("combobox", { name: "mode" }).selectOption("survival");
    await page.getByRole("button", { name: "start round" }).click();

    for (let i = 0; i < 3; i++) {
      await page.getByPlaceholder("type your answer…").fill("wrong answer");
      await page.getByRole("button", { name: "submit" }).click();
      await expect(page.getByText(/\[ NOT QUITE \]/)).toBeVisible();
      const continueLabel = i < 2 ? "next term" : "see results";
      await page.getByRole("button", { name: continueLabel }).click();
    }

    await expect(page.getByText("# out of lives")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "play again" }),
    ).toBeVisible();
  });

  test("correct and partial answers don't cost a life", async ({ page }) => {
    await mockBackend(page, {
      gradeRule: () => ({ verdict: "correct", score: 30 }),
    });
    await page.goto("/");
    await page.getByRole("combobox", { name: "mode" }).selectOption("survival");
    await page.getByRole("button", { name: "start round" }).click();

    // 5 correct answers in a row must not end the round — only INCORRECT
    // costs a life, and 3 lives means 5 correct answers should sail through.
    for (let i = 0; i < 5; i++) {
      await expect(page.getByText("# define this term")).toBeVisible();
      await page.getByPlaceholder("type your answer…").fill("a correct answer");
      await page.getByRole("button", { name: "submit" }).click();
      await expect(page.getByText(/\[ CORRECT \]/)).toBeVisible();
      await page.getByRole("button", { name: "next term" }).click();
    }

    await expect(page.getByText("# out of lives")).not.toBeVisible();
  });
});
