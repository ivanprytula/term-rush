import { defineConfig, devices } from "@playwright/test";

// Browser UI tests against a mocked backend (see ui/mocks.ts) — not a
// true end-to-end suite: the network boundary is faked, so these prove
// the frontend's own state machine, not that it matches the real API's
// contract. vite preview serves the production build against a fixed
// port so tests don't race a cold dev-server compile.
export default defineConfig({
  testDir: "./ui",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    baseURL: "http://localhost:4173",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: "npm run build && npm run preview -- --port 4173",
    url: "http://localhost:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
