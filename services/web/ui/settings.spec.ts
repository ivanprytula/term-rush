import { test, expect } from "@playwright/test";
import { mockBackend } from "./mocks";

test.describe("Client settings and HUD", () => {
    test("persists voice language and Sprint duration", async ({ page }) => {
        const backend = await mockBackend(page);
        await page.goto("/");

        await page.getByText("settings", { exact: true }).click();
        await page.getByRole("combobox", { name: "Voice language" }).selectOption(
            "en-GB",
        );
        await page.getByRole("combobox", { name: "Sprint duration" }).selectOption(
            "120",
        );

        await expect(
            page.getByRole("combobox", { name: "Voice language" }),
        ).toHaveValue("en-GB");
        await expect(
            page.getByRole("combobox", { name: "Sprint duration" }),
        ).toHaveValue("120");
        expect(
            await page.evaluate(() => localStorage.getItem("term-rush-voice-language")),
        ).toBe("en-GB");
        expect(
            await page.evaluate(() => localStorage.getItem("term-rush-sprint-duration")),
        ).toBe("120");

        await page.reload();
        await page.getByText("settings", { exact: true }).click();
        await expect(
            page.getByRole("combobox", { name: "Voice language" }),
        ).toHaveValue("en-GB");
        await expect(
            page.getByRole("combobox", { name: "Sprint duration" }),
        ).toHaveValue("120");

        await page.getByRole("combobox", { name: "mode" }).selectOption("sprint");
        await page.getByRole("button", { name: "start round" }).click();
        expect(backend.lastRoundRequest()).toMatchObject({
            mode: "sprint",
            duration_seconds: 120,
        });
        await expect(page.getByText(/⏱/)).toContainText("120s");
    });

    test("does not send Sprint duration for non-Sprint rounds", async ({ page }) => {
        const backend = await mockBackend(page);
        await page.goto("/");
        await page.getByRole("button", { name: "start round" }).click();

        expect(backend.lastRoundRequest()).toEqual({ mode: "classic" });
    });

    test("passes the selected voice language to recognition", async ({ page }) => {
        await page.addInitScript(() => {
            class FakeSpeechRecognition {
                continuous = false;
                interimResults = false;
                lang = "en-US";
                onend: (() => void) | null = null;
                onerror: ((event: { error: string }) => void) | null = null;
                onresult: ((event: unknown) => void) | null = null;
                onstart: (() => void) | null = null;

                constructor() {
                    Object.defineProperty(window, "__fakeRecognition", {
                        value: this,
                        configurable: true,
                    });
                }

                start() {
                    this.onstart?.();
                }

                stop() {
                    this.onend?.();
                }
            }

            Object.defineProperty(window, "SpeechRecognition", {
                value: FakeSpeechRecognition,
            });
        });
        await mockBackend(page);
        await page.goto("/");
        await page.getByText("settings", { exact: true }).click();
        await page.getByRole("combobox", { name: "Voice language" }).selectOption(
            "en-GB",
        );
        await page.getByRole("button", { name: "start round" }).click();
        await page.getByRole("button", { name: "Start voice input" }).click();

        await expect
            .poll(() =>
                page.evaluate(
                    () =>
                        (
                            window as unknown as {
                                __fakeRecognition: { lang: string };
                            }
                        ).__fakeRecognition.lang,
                ),
            )
            .toBe("en-GB");
    });

    test("shows server-derived score and resets streak after a partial", async ({
        page,
    }) => {
        let submissions = 0;
        await mockBackend(page, {
            gradeRule: () => {
                submissions += 1;
                return submissions === 1
                    ? { verdict: "correct", score: 30 }
                    : { verdict: "partial", score: 10 };
            },
        });
        await page.goto("/");
        await page.getByRole("button", { name: "start round" }).click();

        await expect(page.getByText("score 0 · streak 0")).toBeVisible();
        const answer = page.getByPlaceholder("type your answer…");
        await answer.fill("first answer");
        await page.getByRole("button", { name: "submit" }).click();
        await expect(page.getByText("score 30 · streak 1")).toBeVisible();
        await page.getByRole("button", { name: "next term" }).click();

        await answer.fill("second answer");
        await page.getByRole("button", { name: "submit" }).click();
        await expect(page.getByText("score 40 · streak 0")).toBeVisible();
    });
});
