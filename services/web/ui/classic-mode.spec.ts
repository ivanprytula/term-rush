import { test, expect } from "@playwright/test";
import { mockBackend } from "./mocks";

test.describe("Classic mode", () => {
  test("defaults to classic, shows the pre-game screen", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");

    await expect(page.getByRole("combobox", { name: "mode" })).toHaveValue(
      "classic",
    );
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
      await page.getByRole("button", { name: continueLabel }).click();
    }

    await expect(page.getByText("# round complete")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "play again" }),
    ).toBeVisible();
  });

  test("shows the term counter, not a countdown", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");
    await page.getByRole("button", { name: "start round" }).click();

    await expect(page.getByText("term 1/10")).toBeVisible();
    await expect(page.getByText(/⏱/)).not.toBeVisible();
  });

  test("uses Enter for new lines and Ctrl+Enter to submit", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");
    await page.getByRole("button", { name: "start round" }).click();

    await expect(page.getByText("Enter = new line")).toBeVisible();
    await expect(page.getByText(/Ctrl\/Cmd\+Enter.*submit/)).toBeVisible();

    const answer = page.getByPlaceholder("type your answer…");
    await answer.fill("first line");
    await answer.press("Enter");
    await expect(answer).toHaveValue("first line\n");

    await answer.press("Control+Enter");
    await expect(page.getByText(/\[ CORRECT \]/)).toBeVisible();
  });

  test("inserts a spoken transcript into the answer field", async ({ page }) => {
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
    await page.getByRole("button", { name: "start round" }).click();

    await page.getByRole("button", { name: "Start voice input" }).click();
    await expect(page.getByText("listening... speak your answer")).toBeVisible();
    await page.evaluate(() => {
      const recognition = (
        window as unknown as {
          __fakeRecognition: {
            onresult: ((event: unknown) => void) | null;
          };
        }
      ).__fakeRecognition;
      recognition.onresult?.({
        resultIndex: 0,
        results: [
          { 0: { transcript: "random access memory" }, isFinal: true },
        ],
        length: 1,
      });
    });

    await expect(page.getByPlaceholder("type your answer…")).toHaveValue(
      "random access memory",
    );
    await expect(
      page.getByRole("button", { name: "submit" }),
    ).toBeVisible();
  });

  test("starts voice input with the keyboard shortcut", async ({ page }) => {
    await page.addInitScript(() => {
      class FakeSpeechRecognition {
        continuous = false;
        interimResults = false;
        lang = "en-US";
        onend: (() => void) | null = null;
        onerror: ((event: { error: string }) => void) | null = null;
        onresult: ((event: unknown) => void) | null = null;
        onstart: (() => void) | null = null;

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
    await page.getByRole("button", { name: "start round" }).click();

    await expect(page.getByText("Ctrl/Cmd+Shift+M")).toBeVisible();
    await page.keyboard.press("Control+Shift+M");

    await expect(page.getByText("listening... speak your answer")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Stop voice input" }),
    ).toBeVisible();
  });

  test("keeps accumulated speech and stops continuous listening explicitly", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      class FakeSpeechRecognition {
        continuous = false;
        interimResults = false;
        lang = "en-US";
        startCount = 0;
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
          this.startCount += 1;
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
    await page.getByRole("button", { name: "start round" }).click();
    await page.getByRole("button", { name: "Start voice input" }).click();

    await page.evaluate(() => {
      const recognition = (
        window as unknown as {
          __fakeRecognition: {
            onresult: ((event: unknown) => void) | null;
            onend: (() => void) | null;
            startCount: number;
          };
        }
      ).__fakeRecognition;
      recognition.onresult?.({
        resultIndex: 0,
        results: [{ 0: { transcript: "random access" }, isFinal: true }],
        length: 1,
      });
      recognition.onresult?.({
        resultIndex: 1,
        results: [
          undefined,
          { 0: { transcript: "memory" }, isFinal: false },
        ],
        length: 2,
      });
      recognition.onend?.();
    });

    await expect(page.getByPlaceholder("type your answer…")).toHaveValue(
      "random access memory",
    );
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            (
              window as unknown as {
                __fakeRecognition: { startCount: number };
              }
            ).__fakeRecognition.startCount,
        ),
      )
      .toBe(2);

    await page.getByRole("button", { name: "Stop voice input" }).click();
    const startCountAfterStop = await page.evaluate(
      () =>
        (
          window as unknown as {
            __fakeRecognition: { startCount: number };
          }
        ).__fakeRecognition.startCount,
    );
    await page.waitForTimeout(200);
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            (
              window as unknown as {
                __fakeRecognition: { startCount: number };
              }
            ).__fakeRecognition.startCount,
        ),
      )
      .toBe(startCountAfterStop);
  });

  test("keeps typing available when voice input is unsupported", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      delete (window as Window & { SpeechRecognition?: unknown })
        .SpeechRecognition;
      delete (window as Window & { webkitSpeechRecognition?: unknown })
        .webkitSpeechRecognition;
    });
    await mockBackend(page);
    await page.goto("/");
    await page.getByRole("button", { name: "start round" }).click();

    await expect(
      page.getByText("voice input unavailable in this browser"),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Start voice input" }),
    ).toBeDisabled();
    await page.getByPlaceholder("type your answer…").fill("typed answer");
    await expect(page.getByPlaceholder("type your answer…")).toHaveValue(
      "typed answer",
    );
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
